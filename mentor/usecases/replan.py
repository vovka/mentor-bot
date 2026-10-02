"""Rewrite the task graph via the brain, then keep plan.md and the pinned Telegram message in sync."""

from pathlib import Path

from mentor.domain import tasks
from mentor.domain.actions import BrainTask
from mentor.domain.settings import tier
from mentor.usecases import apply_plan, progress

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "replan.md"

_NO_TASKS = "(none yet — convert the legacy plan below into tasks)"


def run(store, brain, chat, clock, reason: str, message_id: int | None = None,
        reply_to: int | None = None) -> str:
    today = clock.now().date()
    task = BrainTask(
        prompt=_build_prompt(store, today, reason),
        cwd=str(store.data_dir),
        write=False,
        settings=tier(store.read_settings(), "plan"),
    )
    result = progress.tracked(chat, brain, task, "Replanning", "replan", message_id, reply_to)

    marks = {"last_replan": today.isoformat()}
    if not result.document:
        apply_plan.sync_pinned(store, chat, **marks)
        return _no_document(result.reply)
    error = apply_plan.run(store, chat, result.document, **marks)
    if error:
        apply_plan.sync_pinned(store, chat, **marks)
        return f"Plan not changed: {error}. {result.reply}"
    return result.reply


def _no_document(reply: str) -> str:
    if reply.startswith(progress.CANCELLED):
        return "Replan cancelled; plan unchanged."
    if reply.startswith("brain error"):
        return f"Replan failed: {reply.removeprefix('brain error:').strip()}; plan unchanged."
    return "plan unchanged (brain returned no document). " + reply


def _build_prompt(store, today, reason: str) -> str:
    projects = "\n\n".join(_project_section(p, store) for p in store.projects())
    return _PROMPT_PATH.read_text().format_map(
        {
            "today": today.isoformat(),
            "reason": reason,
            "tasks": current_tasks(store),
            "global_plan": store.read_plan(),
            "summary": store.read_summary(),
            "history": store.read_recent_history(2),
            "projects": projects,
        }
    )


def _project_section(project, store) -> str:
    project_md = (Path(project.path) / "project.md").read_text()
    timeline = store.read_timeline(project.name)
    plan = store.read_plan(project.name)
    return f"## {project.name}\n\n{project_md}\n\n{timeline}\n\n{plan}"


def current_tasks(store) -> str:
    current = store.read_tasks()
    return tasks.brief(current) if current else _NO_TASKS
