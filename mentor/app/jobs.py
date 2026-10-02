"""Entry point for `mentor job <name>`: builds a container and dispatches to a use case.

Call site: `mentor job morning|deadline|replan|compact|work [--dry-run]` in mentor/app/cli.py calls
`from mentor.app import jobs; jobs.run(name, dry_run)`.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class _Container:
    store: Any
    brain: Any
    chat: Any
    clock: Any
    mail: Any = None


def _build_container() -> _Container:
    from mentor.app.config import Config

    try:
        from mentor.app.container import build

        c = build(Config.from_env())
        return _Container(store=c.store, brain=c.brain, chat=c.chat, clock=c.clock, mail=c.mail)
    except (ImportError, AttributeError):
        return _fallback_container()


def _fallback_container() -> _Container:
    from mentor.adapters.brain.router import RoutingBrain
    from mentor.adapters.clock import SystemClock
    from mentor.adapters.store.files import FileStore
    from mentor.adapters.telegram.api import TelegramChat
    from mentor.app.config import Config

    config = Config.from_env()
    return _Container(
        store=FileStore(config.data_dir),
        brain=RoutingBrain(),
        chat=TelegramChat(config.telegram_bot_token, config.telegram_chat_id),
        clock=SystemClock(config.tz),
    )


def run(name: str, dry_run: bool = False) -> str:
    from mentor.usecases import compact, morning_brief, morning_checkin, queue

    c = _build_container()
    if name == "morning" and dry_run:
        return morning_brief.run(c.store, c.brain, c.chat, c.clock, dry_run=True)
    if name == "morning":
        return _then_work(c, morning_checkin.morning(c.store, c.brain, c.chat, c.clock))
    if name == "deadline":
        return _then_work(c, morning_checkin.deadline(c.store, c.brain, c.chat, c.clock))
    if name == "replan":
        return _then_work(c, queue.push(c.store, c.chat, "replan", {"reason": "scheduled"}))
    if name == "work":
        return _work(c)
    if name == "compact":
        return compact.run(c.store, c.brain, c.clock)
    raise ValueError(f"unknown job: {name}")


def _then_work(c: _Container, result: str) -> str:
    return f"{result}\n{_work(c)}"


def _work(c: _Container) -> str:
    """The single executor: waits for .work.lock, so a kicked run queues behind the running one."""
    import os
    import threading

    from mentor.adapters.store.lock import locked
    from mentor.app.kick import kick
    from mentor.usecases import work

    if threading.current_thread() is not threading.main_thread():  # in-process scheduler: keep serve alive
        kick()
        return "work loop kicked"
    with locked(c.store.data_dir, ".work.lock"):
        _set_executor_pid(c.store, os.getpid())
        _on_sigterm_cancel()
        try:
            return work.run(c.store, c.brain, c.chat, c.clock, c.mail)
        finally:
            _set_executor_pid(c.store, None)


def _set_executor_pid(store, pid) -> None:
    from mentor.adapters.store.lock import locked

    with locked(store.data_dir):
        state = store.read_state()
        state["executor_pid"] = pid
        store.write_state(state)


def _on_sigterm_cancel() -> None:
    """/cancel: SIGTERM kills the running brain CLI; that job or task fails normally and the loop goes on."""
    import signal
    import threading

    from mentor.adapters.brain import stream

    # off the main thread: the handler may interrupt it while it holds stream's lock
    signal.signal(signal.SIGTERM, lambda signum, frame: threading.Thread(target=stream.cancel).start())
