"""Wires adapters from Config into a Container the CLI hands to use cases."""

from dataclasses import dataclass

from mentor.adapters.agent.agents import Agents
from mentor.adapters.agent.claude import ClaudeAgent
from mentor.adapters.agent.codex import CodexAgent
from mentor.adapters.render.kroki import KrokiRenderer
from mentor.adapters.store.files import FileStore
from mentor.adapters.store.jobs import JobBook
from mentor.adapters.telegram.api import TelegramChat
from mentor.app.config import Config


@dataclass
class Container:
    store: FileStore
    book: JobBook
    agents: Agents
    chat: object
    renderer: object


def build(config: Config) -> Container:
    return Container(
        store=FileStore(config.data_dir),
        book=JobBook(config.data_dir),
        agents=Agents({"codex": CodexAgent(config.codex_bin), "claude": ClaudeAgent(config.claude_bin)}),
        chat=TelegramChat(config.telegram_bot_token, config.telegram_chat_id),
        renderer=KrokiRenderer(config.kroki_url),
    )
