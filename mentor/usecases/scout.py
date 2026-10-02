"""Answer a question about one project by reading its own repo, read-only."""

from pathlib import Path

from mentor.domain.actions import BrainTask
from mentor.domain.settings import BrainSettings
from mentor.usecases import progress

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "scout.md"


def run(store, brain, chat, project: str, question: str, reply_to: int | None = None) -> str:
    match = next((p for p in store.projects() if p.name == project), None)
    if match is None:
        return f"unknown project: {project}"

    raw = store.read_settings()
    task = BrainTask(
        prompt=_PROMPT_PATH.read_text().format_map({"project": match.name, "question": question}),
        cwd=match.repo_path,
        write=False,
        settings=BrainSettings(raw["provider"], raw["model"], raw["effort"]),
    )
    return progress.tracked(chat, brain, task, f"Scouting {match.name}", "scout", reply_to=reply_to).reply
