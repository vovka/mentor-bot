"""handle_message use case: build the prompt, run the brain, dispatch its actions."""

import importlib
from pathlib import Path

from mentor.domain.actions import BrainTask
from mentor.domain.settings import ALLOWED, BrainSettings
from mentor.usecases import add_project, change_settings, send_image
from mentor.usecases.busy import busy

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "mentor.md"


def _dispatch_replan(store, brain, chat, clock, args):
    replan = importlib.import_module("mentor.usecases.replan")
    return replan.run(store, brain, chat, clock, args.get("reason", ""))


def _dispatch_scout(store, brain, chat, clock, args):
    scout = importlib.import_module("mentor.usecases.scout")
    return scout.run(store, brain, args.get("project", ""), args.get("question", ""))


_DISPATCH = {
    "set_settings": lambda s, brain, chat, clock, args: change_settings.run(s.store, args),
    "add_project": lambda s, brain, chat, clock, args: add_project.run(s.store, args),
    "replan": lambda s, brain, chat, clock, args: _dispatch_replan(s.store, brain, chat, clock, args),
    "scout": lambda s, brain, chat, clock, args: _dispatch_scout(s.store, brain, chat, clock, args),
    "send_image": lambda s, brain, chat, clock, args: send_image.run(s.renderer, chat, args),
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


_HEAVY = {"replan", "scout"}


def run(store, brain, chat, clock, text: str, message_id: int = 0, renderer=None) -> str:
    store.append_history(f"user: {text}")
    with busy(chat, message_id):
        reply = _answer(_Services(store, renderer), brain, chat, clock, text, message_id)
        store.append_history(f"bot: {reply}")
        chat.send(reply)
    return reply


class _Services:
    def __init__(self, store, renderer):
        self.store, self.renderer = store, renderer


def _answer(services, brain, chat, clock, text: str, message_id: int) -> str:
    store = services.store
    result = brain.run(_build_task(store, clock, text))
    actions = [a for a in result.actions if a.kind in _DISPATCH]
    if message_id and any(a.kind in _HEAVY for a in actions):
        chat.react(message_id, "🤔")
    action_results = [_DISPATCH[a.kind](services, brain, chat, clock, a.args) for a in actions]
    reply = result.reply
    if action_results:
        reply += "\n\n" + "\n".join(action_results)
    return reply
