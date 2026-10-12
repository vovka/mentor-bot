"""Config from environment, with a minimal .env loader for local runs."""

import os
import time
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    data_dir: Path
    kroki_url: str
    codex_bin: str
    claude_bin: str

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv(Path(".env"))
        time.tzset()  # TZ may come from .env; local times (history, morning) follow it
        data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
        os.environ["DATA_DIR"] = str(data_dir)  # child processes (MCP server, job runner) get the same folder
        return cls(
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            data_dir=data_dir,
            kroki_url=os.environ.get("KROKI_URL", "https://kroki.io"),
            codex_bin=os.environ.get("CODEX_BIN", "codex"),
            claude_bin=os.environ.get("CLAUDE_BIN", "claude"),
        )
