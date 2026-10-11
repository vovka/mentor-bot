"""Chat action send_files: send a task's deliverables on request (all of them, or the named ones)."""

from pathlib import Path

from mentor.usecases import work_brain
from mentor.usecases.work_result import send_file


def run(store, chat, args: dict) -> str:
    task = next((t for t in store.read_tasks() if t.id == args.get("task_id")), None)
    if task is None:
        return f"No task with id {args.get('task_id')!r}."
    wanted = set(args.get("files") or [])
    names = [f for f in task.files if not wanted or Path(f).name in wanted or f in wanted]
    wdir, repo = work_brain.dir_of(store, task), work_brain.repo_of(store, task)
    sent = [n for n in names if send_file(chat, n, wdir, repo)]
    return f"Sent {len(sent)} file(s) from {task.title}." if sent else f"No matching files for {task.title}."
