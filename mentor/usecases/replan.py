"""Rewrite the task graph via the brain, then keep plan.md and the pinned Telegram message in sync."""

from pathlib import Path

from mentor.domain import tasks
from mentor.domain.actions import BrainTask
from mentor.domain.settings import BrainSettings
from mentor.usecases import apply_plan

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "replan.md"

_NO_TASKS = "(none yet — convert the legacy plan below into tasks)"


def run(store, brain, chat, clock, reason: str) -> str:
    today = clock.now().date()
    task = BrainTask(
        prompt=_build_prompt(store, today, reason),
        cwd=str(store.data_dir),
        write=False,
        settings=BrainSettings(**store.read_settings()["heavy"]),
    )
    result = brain.run(task)

    marks = {"last_replan": today.isoformat()}
    if not result.document:
        apply_plan.sync_pinned(store, chat, **marks)
        return "plan unchanged (brain returned no document). " + result.reply
    error = apply_plan.run(store, chat, result.document, **marks)
    if error:
        apply_plan.sync_pinned(store, chat, **marks)
        return f"Plan not changed: {error}. {result.reply}"
    return result.reply


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
    return tasks.dump(current) if current else _NO_TASKS
