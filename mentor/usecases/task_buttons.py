"""Task buttons `t:<task id>:<verb>`: approve / approve on the other provider / reject / done."""

from mentor.adapters.store.lock import locked
from mentor.usecases import apply_plan
from mentor.usecases.work_brain import other_provider

_NEEDS = {"ok": "awaiting_approval", "alt": "awaiting_approval", "no": "awaiting_approval", "done": "awaiting_user"}
_ASK_INSTEAD = "What should I do instead?"


def on_button(store, chat, update, kick) -> str:
    chat.answer_callback(update.callback_id)
    chat.clear_buttons(update.message_id)
    _, task_id, verb = update.callback_data.split(":", 2)
    if not _claim(store, task_id, verb):
        chat.send("Already handled.", reply_to=update.message_id)
        return "stale"
    if verb == "no":
        chat.send(_ASK_INSTEAD, reply_to=update.message_id)
    apply_plan.refresh(store, chat)
    if verb != "no":
        kick()
    return verb


def _claim(store, task_id: str, verb: str) -> bool:
    """Compare-and-set: apply `verb` only if the task is still in the status the button was sent for."""
    with locked(store.data_dir):
        all_tasks = store.read_tasks()
        task = next((t for t in all_tasks if t.id == task_id), None)
        if task is None or _NEEDS.get(verb) != task.status:
            return False
        _apply(store, task, verb)
        store.write_tasks(all_tasks)
        return True


def _apply(store, task, verb: str) -> None:
    if verb == "no":
        task.status, task.note = "awaiting_user", "Rejected — say what to do instead"
    elif verb == "done":
        task.status = "done"
    else:
        if verb == "alt":
            task.provider = other_provider(store.read_settings(), task) or task.provider
        task.status, task.approved = "todo", True
