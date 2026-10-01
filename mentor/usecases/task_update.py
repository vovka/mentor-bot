"""Chat action task_update: the user marks a task done, dropped, or back to todo (retry)."""

from mentor.adapters.store.lock import locked
from mentor.usecases import apply_plan

_ALLOWED = ("todo", "done", "dropped")


def run(store, chat, kick, args: dict) -> str:
    task_id, status = args.get("task_id", ""), args.get("status", "")
    if status not in _ALLOWED:
        return f"Task not changed: status must be one of {', '.join(_ALLOWED)}, got {status!r}."
    with locked(store.data_dir):
        all_tasks = store.read_tasks()
        task = next((t for t in all_tasks if t.id == task_id), None)
        if task is None:
            return f"Task not changed: no task with id {task_id!r}."
        task.status = status
        task.note = args.get("note", task.note)
        store.write_tasks(all_tasks)
    apply_plan.refresh(store, chat)
    kick()
    return f"Task {task.title}: {status}."
