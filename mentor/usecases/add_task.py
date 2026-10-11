"""Chat action add_task: ad-hoc work from the user goes to the top of the task graph and runs next."""

import re

from mentor.adapters.store.lock import locked
from mentor.domain import tasks
from mentor.usecases import apply_plan


def run(store, chat, kick, args: dict, reply_to: int | None = None) -> str:
    title = (args.get("title") or "").strip()
    if not title:
        return "Task not added: it needs a title."
    kind = args.get("kind") if args.get("kind") in tasks.KINDS else "research"  # a model-routing hint only
    with locked(store.data_dir):
        all_tasks = store.read_tasks()
        task = tasks.Task(_new_id(title, {t.id for t in all_tasks}), title, project=args.get("project") or "",
                          kind=kind, note=args.get("note") or "", reply_to=reply_to or 0)
        store.write_tasks([task, *all_tasks])
    apply_plan.refresh(store, chat)
    kick()
    return f"Queued as the next task: {title}."


def _new_id(title: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "task"
    n, candidate = 1, base
    while candidate in taken:
        n += 1
        candidate = f"{base}-{n}"
    return candidate
