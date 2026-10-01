"""Apply a planner's tasks.json to the store, then refresh the plan.md view and the pinned message."""

from mentor.adapters.store.lock import locked
from mentor.domain import tasks

_PIN_LIMIT = 3800


def run(store, chat, document: str, **marks) -> str | None:
    """Merge `document` into tasks.json. Returns the error text (nothing changed) or None."""
    try:
        new = tasks.parse(document)
    except ValueError as e:
        return str(e)
    with locked(store.data_dir):
        store.write_tasks(tasks.merge(store.read_tasks(), new))
    refresh(store, chat, **marks)
    return None


def refresh(store, chat, **marks) -> None:
    """Re-render plan.md from tasks.json and sync the pin; call after every status change."""
    store.write_plan(tasks.render(store.read_tasks()))
    sync_pinned(store, chat, **marks)


def sync_pinned(store, chat, **marks) -> None:
    """Push plan.md into the pinned message; `marks` are extra state keys set in the same lock."""
    pinned = _render_pinned(store.read_plan())
    with locked(store.data_dir):
        state = store.read_state()
        _sync_pin(chat, state, pinned)
        state.update(marks)
        store.write_state(state)


def _render_pinned(plan_text: str) -> str:
    if len(plan_text) <= _PIN_LIMIT:
        return plan_text
    return plan_text[:_PIN_LIMIT] + "\n…see plan.md"


def _sync_pin(chat, state: dict, text: str) -> None:
    pinned_id = state.get("pinned_message_id")
    if pinned_id:
        chat.edit(pinned_id, text)
    else:
        pinned_id = chat.send(text)
        chat.pin(pinned_id)
        state["pinned_message_id"] = pinned_id
