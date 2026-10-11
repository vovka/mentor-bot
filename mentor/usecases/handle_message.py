"""handle_message use case: build the prompt, run the brain, dispatch its actions."""

import importlib
from pathlib import Path

from mentor.domain.actions import BrainTask
from mentor.domain.settings import ALLOWED, BrainSettings
from mentor.usecases import add_project, add_task, change_settings, queue, send_files, send_image, task_update
from mentor.usecases.busy import busy

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "mentor.md"


def _dispatch_replan(services, chat, args):
    job, nth = queue.enqueue(services.store, "replan", {"reason": args.get("reason") or ""}, services.message_id)

    def announce_and_kick():  # after the chat answer, so "🕒 Queued" and any progress land below it
        queue.announce(services.store, chat, job, nth)
        services.kick()

    services.after.append(announce_and_kick)
    return queue.reply_line("replan", nth)


def _dispatch_work(services):
    services.kick()
    return "Working on the next task."


def _dispatch_scout(services, brain, chat, args):
    scout = importlib.import_module("mentor.usecases.scout")
    return scout.run(services.store, brain, chat, args.get("project", ""), args.get("question", ""), services.message_id)


_DISPATCH = {
    "set_settings": lambda s, brain, chat, clock, args: change_settings.run(s.store, args),
    "add_project": lambda s, brain, chat, clock, args: add_project.run(s.store, args),
    "replan": lambda s, brain, chat, clock, args: _dispatch_replan(s, chat, args),
    "add_task": lambda s, brain, chat, clock, args: add_task.run(s.store, chat, s.kick, args, s.message_id),
    "scout": lambda s, brain, chat, clock, args: _dispatch_scout(s, brain, chat, args),
    "send_image": lambda s, brain, chat, clock, args: send_image.run(s.renderer, chat, args),
    "work": lambda s, brain, chat, clock, args: _dispatch_work(s),
    "task_update": lambda s, brain, chat, clock, args: task_update.run(s.store, chat, s.kick, args),
    "send_files": lambda s, brain, chat, clock, args: send_files.run(s.store, chat, args),
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


_HEAVY = {"scout"}


def run(store, brain, chat, clock, text: str, message_id: int = 0, renderer=None, kick=lambda: None) -> str:
    store.append_history(f"user: {text}")
    with busy(chat, message_id):
        services = _Services(store, renderer, kick, message_id)
        reply = _answer(services, brain, chat, clock, text, message_id)
        store.append_history(f"bot: {reply}")
        try:
            chat.send(reply, reply_to=message_id or None)
        finally:
            _run_after(services)
    return reply


def _run_after(services) -> None:
    for action in services.after:
        try:
            action()
        except Exception as error:  # one failing follow-up must not stop the others
            print(f"handle_message: follow-up failed: {error}")


class _Services:
    def __init__(self, store, renderer, kick, message_id=0):
        self.store, self.renderer, self.kick = store, renderer, kick
        self.after: list = []  # run once the chat answer is sent
        self.message_id = message_id or None  # the user's message: replies and queued work quote it


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
