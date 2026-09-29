"""Config from environment, with a minimal .env loader for local runs."""

import os
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
    tz: str
    claude_code_oauth_token: str

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv(Path(".env"))
        return cls(
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            data_dir=Path(os.environ.get("DATA_DIR", "./data")),
            tz=os.environ.get("TZ", "Europe/Kyiv"),
            claude_code_oauth_token=os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""),
        )
