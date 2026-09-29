from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Update:
    update_id: int
    chat_id: int
    text: str
    at: datetime
    message_id: int = 0


@dataclass(frozen=True)
class Message:
    role: str
    text: str
    at: datetime
