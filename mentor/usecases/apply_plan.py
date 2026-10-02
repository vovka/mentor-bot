"""Apply a planner's tasks.json to the store, then refresh the plan.md view and the pinned message."""

import json

from mentor.adapters.store.lock import locked
from mentor.domain import task_ops, tasks

_PIN_LIMIT = 3800


def run(store, chat, document: str, **marks) -> str | None:
    """Apply `document` (ops patch, or the full tasks list) to tasks.json. Returns the error text or None."""
    try:
        with locked(store.data_dir):
            new, skipped = apply(store.read_tasks(), document)
            store.write_tasks(new)
    except ValueError as e:
        return str(e)
    skipped and chat.send("Plan patch notes:\n" + "\n".join(skipped))
    refresh(store, chat, **marks)
    return None


def apply(current: list[tasks.Task], document: str) -> tuple[list[tasks.Task], list[str]]:
    """The tasks after `document` and the lines of ops that were skipped; ValueError if it is invalid."""
    data = _loads(document)
    if "ops" not in data:
        return tasks.merge(current, tasks.parse(document)), []
    if not isinstance(data["ops"], list):
        raise ValueError("'ops' must be a list")
    return task_ops.apply_ops(current, data["ops"])


def _loads(document: str) -> dict:
    try:
        data = json.loads(document)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    return data if isinstance(data, dict) else {}


def refresh(store, chat, **marks) -> None:
    """Re-render plan.md from tasks.json and sync the pin in one locked step; the caller must not hold the lock."""
    with locked(store.data_dir):
        store.write_plan(tasks.render(store.read_tasks()))
        _sync_pinned(store, chat, marks)


def sync_pinned(store, chat, **marks) -> None:
    """Push plan.md into the pinned message; `marks` are extra state keys set in the same lock."""
    with locked(store.data_dir):
        _sync_pinned(store, chat, marks)


def _sync_pinned(store, chat, marks: dict) -> None:
    state = store.read_state()
    _sync_pin(chat, state, _render_pinned(store.read_plan()))
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
