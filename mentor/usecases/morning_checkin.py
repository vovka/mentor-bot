"""08:00 and 09:00 jobs: ask whether yesterday got done, then queue a reconcile (it sends the brief).

The callers (jobs.py) run the executor right after, which drains the queued reconcile."""

from mentor.usecases import checkin_state, morning_brief, queue, reconcile

QUESTION = "No updates from yesterday. Does this mean yesterday's tasks weren't done?"
DEADLINE_NOTICE = "No updates by 9:00, treating yesterday's tasks as not done."


def morning(store, brain, chat, clock) -> str:
    today = clock.now().date().isoformat()
    state = store.read_state()
    if today in (state.get("last_brief_date"), (state.get("checkin") or {}).get("date")):
        return "already sent"
    last_brief = state.get("last_brief_date")
    if not last_brief:
        return morning_brief.run(store, brain, chat, clock)
    if _user_wrote(reconcile.history_since(store, last_brief)):
        return queue.push(store, chat, "reconcile", {})
    message_id = chat.send(QUESTION, buttons=[("Yes", "yes"), ("No", "no")])
    checkin_state.save(store, {"date": today, "stage": "asked", "message_id": message_id})
    return QUESTION


def deadline(store, brain, chat, clock) -> str:
    if not checkin_state.claim(store, {"asked", "awaiting_updates"}):
        return "no pending check-in"
    chat.send(DEADLINE_NOTICE)
    return queue.push(store, chat, "reconcile", {})


def _user_wrote(history: str) -> bool:
    return any(line.startswith("user: ") for line in history.splitlines())
