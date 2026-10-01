"""Rewrite the global plan via the brain, then keep the pinned Telegram message in sync."""

from pathlib import Path

from mentor.adapters.store.lock import locked
from mentor.domain.actions import BrainTask
from mentor.domain.settings import BrainSettings

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "replan.md"
_PIN_LIMIT = 3800


def run(store, brain, chat, clock, reason: str) -> str:
    today = clock.now().date()
    task = BrainTask(
        prompt=_build_prompt(store, today, reason),
        cwd=str(store.data_dir),
        write=False,
        settings=BrainSettings(**store.read_settings()["heavy"]),
    )
    result = brain.run(task)

    summary = result.reply
    if result.document:
        store.write_plan(result.document)
    else:
        summary = "plan.md unchanged (brain returned no document). " + summary

    sync_pinned(store, chat, last_replan=today.isoformat())
    return summary


def sync_pinned(store, chat, **marks) -> None:
    """Push plan.md into the pinned message; `marks` are extra state keys set in the same lock."""
    pinned = _render_pinned(store.read_plan())
    with locked(store.data_dir):
        state = store.read_state()
        _sync_pin(chat, state, pinned)
        state.update(marks)
        store.write_state(state)


def _build_prompt(store, today, reason: str) -> str:
    projects = "\n\n".join(_project_section(p, store) for p in store.projects())
    return _PROMPT_PATH.read_text().format_map(
        {
            "today": today.isoformat(),
            "reason": reason,
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
