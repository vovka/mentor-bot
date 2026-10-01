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
    from mentor.app.kick import kick
    from mentor.usecases import compact, morning_brief, morning_checkin, replan

    c = _build_container()
    if name == "morning" and dry_run:
        return morning_brief.run(c.store, c.brain, c.chat, c.clock, dry_run=True)
    if name == "morning":
        result = morning_checkin.morning(c.store, c.brain, c.chat, c.clock)
        kick()
        return result
    if name == "deadline":
        return morning_checkin.deadline(c.store, c.brain, c.chat, c.clock)
    if name == "replan":
        result = replan.run(c.store, c.brain, c.chat, c.clock, reason="scheduled")
        kick()
        return result
    if name == "work":
        return _work(c)
    if name == "compact":
        return compact.run(c.store, c.brain, c.clock)
    raise ValueError(f"unknown job: {name}")


def _work(c: _Container) -> str:
    from mentor.adapters.store.lock import try_locked
    from mentor.usecases import work

    with try_locked(c.store.data_dir / ".work.lock") as acquired:
        return work.run(c.store, c.brain, c.chat, c.clock, c.mail) if acquired else "work loop already running"
