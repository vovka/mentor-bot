"""Reconcile: the heavy brain moves undone tasks forward; the proposal waits for Approve/Reject."""

from datetime import date
from pathlib import Path

from mentor.domain.actions import BrainTask
from mentor.domain.settings import tier
from mentor.usecases import apply_plan, checkin_state, morning_brief
from mentor.usecases.replan import PLAN_TIMEOUT, current_tasks

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "reconcile.md"
BUTTONS = [("Approve", "approve"), ("Reject", "reject")]


def run(store, brain, chat, clock) -> str:
    today = clock.now().date()
    task = BrainTask(
        prompt=_build_prompt(store, today),
        cwd=str(store.data_dir),
        write=False,
        settings=tier(store.read_settings(), "plan"),
        timeout=PLAN_TIMEOUT,
    )
    result = brain.run(task)
    error = _invalid(store, result.document)
    if error or not result.document:
        checkin_state.save(store, None)
        if error:
            chat.send(f"Plan proposal discarded: {error}")
        return morning_brief.run(store, brain, chat, clock)
    message_id = chat.send(result.reply, buttons=BUTTONS)
    checkin_state.save(store, {
        "date": today.isoformat(), "stage": "proposed", "message_id": message_id,
        "proposal": result.reply, "document": result.document,
    })
    return result.reply


def _invalid(store, document: str | None) -> str | None:
    """Dry-run the proposal against the current tasks; Approve applies it to whatever is current then."""
    try:
        document and apply_plan.apply(store.read_tasks(), document)
    except ValueError as e:
        return str(e)
    return None


def history_since(store, since: str | None) -> str:
    """Chat days on or after `since` (ISO date); day granularity since history lines carry no time."""
    start = date.fromisoformat(since) if since else date.min
    return "\n".join(store.read_history(d) for d in store.list_history_days() if d >= start)


def _build_prompt(store, today) -> str:
    timelines = "\n\n".join(
        f"## {p.name}\n\n{store.read_timeline(p.name)}" for p in store.projects()
    )
    return _PROMPT_PATH.read_text().format_map(
        {
            "today": today.isoformat(),
            "tasks": current_tasks(store),
            "global_plan": store.read_plan(),
            "timelines": timelines,
            "history": history_since(store, store.read_state().get("last_brief_date")) or "(none)",
        }
    )
