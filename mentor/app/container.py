"""Wires adapters from Config into a Container the CLI hands to use cases."""

from dataclasses import dataclass

from mentor.adapters.brain.claude_cli import ClaudeBrain
from mentor.adapters.brain.codex_cli import CodexBrain
from mentor.adapters.clock import SystemClock
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.api import TelegramChat
from mentor.app.config import Config
from mentor.domain.settings import BrainSettings
from mentor.ports.brain import Brain
from mentor.ports.chat import Chat
from mentor.ports.clock import Clock
from mentor.ports.store import Store

_SCHEMA_PATH = "prompts/output_schema.json"


@dataclass
class Container:
    store: Store
    brain: Brain
    chat: Chat
    clock: Clock


def brain_for(settings: BrainSettings) -> Brain:
    if settings.provider == "codex":
        return CodexBrain(_SCHEMA_PATH)
    if settings.provider == "claude":
        return ClaudeBrain(_SCHEMA_PATH)
    raise ValueError(f"unknown provider {settings.provider!r}")


def build(config: Config) -> Container:
    store = FileStore(config.data_dir)
    current = store.read_settings()
    settings = BrainSettings(**{k: current[k] for k in ("provider", "model", "effort")})
    return Container(
        store=store,
        brain=brain_for(settings),
        chat=TelegramChat(config.telegram_bot_token, config.telegram_chat_id),
        clock=SystemClock(config.tz),
    )
