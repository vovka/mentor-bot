"""Durable job queue in state.json["jobs"]: plan-changing work the single executor drains in order.

A job is {id, kind, args, attempts, message_id, reply_to}; kind: replan {reason} (reconcile
only proposes ops, so it runs directly, not here).
`attempts` counts takes, so a job that crashed the executor twice gets dropped instead of looping.
"""

import html
import uuid

from mentor.adapters.store.lock import locked

LABELS = {"replan": "Replanning"}


def push(store, chat, kind: str, args: dict, reply_to: int | None = None) -> str:
    """Post the `🕒 Queued (Nth)` message (a reply to `reply_to`), then append the job carrying its id.

    The message goes first so the executor never takes a job without it; Nth is read before, so
    it may be off by one when two pushes race."""
    nth = _ordinal(len(pending(store)) + 1)
    message_id = chat.send_html(html.escape(f"🕒 Queued ({nth}): {LABELS[kind]}"), reply_to)
    job = {"id": uuid.uuid4().hex[:8], "kind": kind, "args": args, "attempts": 0, "message_id": message_id,
           "reply_to": reply_to}
    with locked(store.data_dir):
        state = store.read_state()
        state["jobs"] = state.get("jobs", []) + [job]
        store.write_state(state)
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


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
