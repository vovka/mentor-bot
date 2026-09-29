"""Fold day-old history files into summary.md so raw days don't grow unbounded."""

from datetime import date, timedelta
from pathlib import Path

from mentor.adapters.store.lock import locked
from mentor.domain.actions import BrainTask
from mentor.domain.settings import BrainSettings

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "compact.md"


def run(store, brain, clock, keep_days: int = 14) -> str:
    old_days = _days_to_fold(store, clock, keep_days)
    if not old_days:
        return "nothing to compact"

    task = BrainTask(
        prompt=_build_prompt(store, old_days),
        cwd=str(store.data_dir / "history"),
        write=True,
        settings=BrainSettings(**store.read_settings()["heavy"]),
    )
    brain.run(task)

    with locked(store.data_dir):
        state = store.read_state()
        state["compacted_through"] = old_days[-1].isoformat()
        store.write_state(state)

    return f"folded {len(old_days)} day(s) through {old_days[-1].isoformat()}"


def _days_to_fold(store, clock, keep_days: int) -> list[date]:
    cutoff = clock.now().date() - timedelta(days=keep_days)
    since = store.read_state().get("compacted_through")
    since_date = date.fromisoformat(since) if since else None
    return [
        d
        for d in store.list_history_days()
        if d <= cutoff and (since_date is None or d > since_date)
    ]


def _build_prompt(store, old_days: list[date]) -> str:
    days_text = "\n\n".join(f"## {d.isoformat()}\n\n{store.read_history(d)}" for d in old_days)
    return _PROMPT_PATH.read_text().format_map({"summary": store.read_summary(), "days": days_text})
