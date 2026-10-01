"""Wires adapters from Config into a Container the CLI hands to use cases."""

from dataclasses import dataclass

from mentor.adapters.brain.router import RoutingBrain
from mentor.adapters.clock import SystemClock
from mentor.adapters.mail.imap import ImapDrafts
from mentor.adapters.render.kroki import KrokiRenderer
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.api import TelegramChat
from mentor.app.config import Config
from mentor.ports.brain import Brain
from mentor.ports.chat import Chat
from mentor.ports.clock import Clock
from mentor.ports.mail import Mail
from mentor.ports.renderer import Renderer
from mentor.ports.store import Store


@dataclass
class Container:
    store: Store
    brain: Brain
    chat: Chat
    clock: Clock
    renderer: Renderer
    mail: Mail | None = None


def build(config: Config) -> Container:
    store = FileStore(config.data_dir)
    return Container(
        store=store,
        brain=RoutingBrain(),
        chat=TelegramChat(config.telegram_bot_token, config.telegram_chat_id),
        clock=SystemClock(config.tz),
        renderer=KrokiRenderer(config.kroki_url),
        mail=ImapDrafts(config.gmail_user, config.gmail_app_password) if config.gmail_app_password else None,
    )
