"""Durable job queue in state.json["jobs"]: plan-changing work the single executor drains in order.

A job is {id, kind, args, attempts, message_id}; kinds: replan {reason}, reconcile {}.
`attempts` counts takes, so a job that crashed the executor twice gets dropped instead of looping.
"""

import html
import uuid

from mentor.adapters.store.lock import locked

LABELS = {"replan": "Replanning", "reconcile": "Reconciling the plan"}


def push(store, chat, kind: str, args: dict) -> str:
    """Append a job, post its `🕒 Queued (Nth)` message, return a human line for the reply."""
    job = {"id": uuid.uuid4().hex[:8], "kind": kind, "args": args, "attempts": 0, "message_id": None}
    with locked(store.data_dir):
        state = store.read_state()
        state["jobs"] = state.get("jobs", []) + [job]
        store.write_state(state)
        nth = _ordinal(len(state["jobs"]))
    message_id = chat.send_html(html.escape(f"🕒 Queued ({nth}): {LABELS[kind]}"))
    _update(store, job["id"], message_id=message_id)
    return f"{LABELS[kind]} queued ({nth} in line)."


def take(store) -> dict | None:
    """The oldest job with attempts += 1 (it stays queued until `done`), or None."""
    with locked(store.data_dir):
        state = store.read_state()
        jobs = state.get("jobs", [])
        if not jobs:
            return None
        jobs[0]["attempts"] += 1
        store.write_state(state)
        return jobs[0]


def done(store, job_id: str) -> None:
    with locked(store.data_dir):
        state = store.read_state()
        state["jobs"] = [j for j in state.get("jobs", []) if j["id"] != job_id]
        store.write_state(state)


def pending(store) -> list[dict]:
    return store.read_state().get("jobs", [])


def _update(store, job_id: str, **fields) -> None:
    """Set fields on a still-queued job; a no-op when the executor already finished it."""
    with locked(store.data_dir):
        state = store.read_state()
        for job in state.get("jobs", []):
            if job["id"] == job_id:
                job.update(fields)
        store.write_state(state)


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
