"""TelegramChat: Bot API adapter over stdlib urllib (send/edit/pin/poll)."""

import json
import os
import urllib.request
from datetime import datetime, timezone

from mentor.adapters.telegram.markdown import chunk
from mentor.domain.conversation import Update

_CALL_TIMEOUT = 10
_POLL_TIMEOUT = 40
_POLL_WAIT = 30


class TelegramChat:
    def __init__(self, token: str, chat_id: str):
        base = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org")
        self._base = f"{base}/bot{token}"
        self._chat_id = str(chat_id)

    def _call(self, method: str, params: dict, timeout: float) -> dict:
        req = urllib.request.Request(
            f"{self._base}/{method}",
            data=json.dumps(params).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    def send(self, text: str) -> int:
        msg_id = 0
        for part in chunk(text):
            result = self._call(
                "sendMessage", {"chat_id": self._chat_id, "text": part}, _CALL_TIMEOUT
            )
            msg_id = result["result"]["message_id"]
        return msg_id

    def edit(self, id: int, text: str) -> None:
        self._call(
            "editMessageText",
            {"chat_id": self._chat_id, "message_id": id, "text": text},
            _CALL_TIMEOUT,
        )

    def pin(self, id: int) -> None:
        self._call(
            "pinChatMessage",
            {"chat_id": self._chat_id, "message_id": id, "disable_notification": True},
            _CALL_TIMEOUT,
        )

    def poll(self, offset: int) -> list[Update]:
        result = self._call(
            "getUpdates", {"timeout": _POLL_WAIT, "offset": offset}, _POLL_TIMEOUT
        )
        return [u for item in result["result"] if (u := self._to_update(item)) is not None]

    def _to_update(self, item: dict) -> Update | None:
        message = item.get("message")
        if not message or str(message["chat"]["id"]) != self._chat_id:
            return None
        return Update(
            update_id=item["update_id"],
            chat_id=message["chat"]["id"],
            text=message.get("text", ""),
            at=datetime.fromtimestamp(message["date"], tz=timezone.utc),
        )
