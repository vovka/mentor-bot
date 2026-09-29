"""Send the once-daily morning brief; idempotent per calendar day."""

from pathlib import Path

from mentor.adapters.store.lock import locked
from mentor.domain.actions import BrainTask
from mentor.domain.settings import BrainSettings

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "morning.md"


def run(store, brain, chat, clock, dry_run: bool = False) -> str:
    today = clock.now().date()
    if store.read_state().get("last_brief_date") == today.isoformat():
        return "already sent"

    reply = _ask_brain(store, brain, today)
    if dry_run:
        return reply

    chat.send(reply)
    with locked(store.data_dir):
        state = store.read_state()
        state["last_brief_date"] = today.isoformat()
        store.write_state(state)
    return reply


def _ask_brain(store, brain, today) -> str:
    raw = store.read_settings()
    task = BrainTask(
        prompt=_build_prompt(store, today),
        cwd=str(store.data_dir),
        write=False,
        settings=BrainSettings(raw["provider"], raw["model"], raw["effort"]),
    )
    return brain.run(task).reply


def _build_prompt(store, today) -> str:
    timelines = "\n\n".join(
        f"## {p.name}\n\n{store.read_timeline(p.name)}" for p in store.projects()
    )
    return _PROMPT_PATH.read_text().format_map(
        {
            "today": today.isoformat(),
            "weekday": today.strftime("%A"),
            "global_plan": store.read_plan(),
            "timelines": timelines,
        }
    )
