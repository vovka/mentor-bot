"""Durable job queue in state.json["jobs"]: plan-changing work the single executor drains in order.

A job is {id, kind, args, attempts, message_id, reply_to}; kind: replan {reason} (reconcile
only proposes ops, so it runs directly, not here).
`attempts` counts takes, so a job that crashed the executor twice gets dropped instead of looping.
"""

import html
import uuid

from mentor.adapters.store.lock import locked

LABELS = {"replan": "Replanning"}


def enqueue(store, kind: str, args: dict, reply_to: int | None = None) -> tuple[dict, str]:
    """Append the job (no message yet) and return it with its ordinal in line, read under the lock."""
    job = {"id": uuid.uuid4().hex[:8], "kind": kind, "args": args, "attempts": 0, "message_id": None,
           "reply_to": reply_to}
    with locked(store.data_dir):
        state = store.read_state()
        state["jobs"] = state.get("jobs", []) + [job]
        store.write_state(state)
    return job, _ordinal(len(state["jobs"]))


def reply_line(kind: str, nth: str) -> str:
    return f"{LABELS[kind]} queued ({nth} in line)."


def announce(store, chat, job: dict, nth: str) -> None:
    """Post `🕒 Queued (Nth)` (a reply to the job's reply_to) and attach its id to the job, unless the
    executor already took the job: then its progress message is the status and nothing is posted."""
    if not _untaken(store, job):
        return
    message_id = chat.send_html(html.escape(f"🕒 Queued ({nth}): {LABELS[job['kind']]}"), job["reply_to"])
    with locked(store.data_dir):
        state = store.read_state()
        mine = next((j for j in state.get("jobs", []) if j["id"] == job["id"]), None)
        if mine and mine["attempts"] == 0 and mine["message_id"] is None:
            mine["message_id"] = message_id
            store.write_state(state)


def push(store, chat, kind: str, args: dict, reply_to: int | None = None) -> str:
    job, nth = enqueue(store, kind, args, reply_to)
    announce(store, chat, job, nth)
    return reply_line(kind, nth)


def _untaken(store, job: dict) -> bool:
    return any(j["id"] == job["id"] and j["attempts"] == 0 for j in pending(store))


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
