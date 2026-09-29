"""handle_message use case: build the prompt, run the brain, dispatch its actions."""

import importlib
from pathlib import Path

from mentor.domain.actions import BrainTask
from mentor.domain.settings import ALLOWED, BrainSettings
from mentor.usecases import add_project, change_settings

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "mentor.md"


def _dispatch_replan(store, brain, chat, clock, args):
    replan = importlib.import_module("mentor.usecases.replan")
    return replan.run(store, brain, chat, clock, args.get("reason", ""))


def _dispatch_scout(store, brain, chat, clock, args):
    scout = importlib.import_module("mentor.usecases.scout")
    return scout.run(store, brain, args.get("project", ""), args.get("question", ""))


_DISPATCH = {
    "set_settings": lambda store, brain, chat, clock, args: change_settings.run(store, args),
    "add_project": lambda store, brain, chat, clock, args: add_project.run(store, args),
    "replan": _dispatch_replan,
    "scout": _dispatch_scout,
}


def _build_task(store, clock, text: str) -> BrainTask:
    settings = store.read_settings()
    allowed = "\n".join(f"{p}: {', '.join(models)}" for p, models in ALLOWED.items())
    prompt = _PROMPT_PATH.read_text().format_map(
        {
            "projects": "\n".join(f"- {p.name}: {p.repo_path}" for p in store.projects())
            or "(none)",
            "provider": settings["provider"],
            "model": settings["model"],
            "effort": settings["effort"],
            "allowed": allowed,
            "today": clock.now().date().isoformat(),
            "summary": store.read_summary() or "(none)",
            "history": store.read_recent_history(2) or "(none)",
            "plan": store.read_plan() or "(none)",
            "message": text,
        }
    )
    brain_settings = BrainSettings(**{k: settings[k] for k in ("provider", "model", "effort")})
    return BrainTask(prompt=prompt, cwd=str(store.data_dir), write=False, settings=brain_settings)


def run(store, brain, chat, clock, text: str) -> str:
    store.append_history(f"user: {text}")

    task = _build_task(store, clock, text)
    result = brain.run(task)

    action_results = [
        _DISPATCH[a.kind](store, brain, chat, clock, a.args)
        for a in result.actions
        if a.kind in _DISPATCH
    ]
    reply = result.reply
    if action_results:
        reply += "\n\n" + "\n".join(action_results)

    store.append_history(f"bot: {reply}")
    chat.send(reply)
    return reply
