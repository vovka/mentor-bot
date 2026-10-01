"""TelegramChat: Bot API adapter over stdlib urllib (send/edit/pin/poll/react/typing/buttons)."""

import json
import mimetypes
import os
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone

from mentor.adapters.telegram.markdown import chunk
from mentor.domain.conversation import Update

_CALL_TIMEOUT = 10
_UPLOAD_TIMEOUT = 120
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

    def send(self, text: str, buttons: list[tuple[str, str]] | None = None) -> int:
        parts = chunk(text)
        msg_id = 0
        for i, part in enumerate(parts):
            params = {"chat_id": self._chat_id, "text": part}
            if buttons and i == len(parts) - 1:
                row = [{"text": label, "callback_data": data} for label, data in buttons]
                params["reply_markup"] = {"inline_keyboard": [row]}
            msg_id = self._call("sendMessage", params, _CALL_TIMEOUT)["result"]["message_id"]
        return msg_id

    def answer_callback(self, callback_id: str) -> None:
        self._call_quietly("answerCallbackQuery", {"callback_query_id": callback_id})

    def clear_buttons(self, message_id: int) -> None:
        params = {"chat_id": self._chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}}
        self._call_quietly("editMessageReplyMarkup", params)

    def send_photo(self, png: bytes, caption: str) -> int:
        return self._upload("sendPhoto", "photo", "diagram.png", png, caption, "image/png", _CALL_TIMEOUT * 3)

    def send_document(self, data: bytes, filename: str, caption: str = "") -> int:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return self._upload("sendDocument", "document", filename, data, caption, content_type, _UPLOAD_TIMEOUT)

    def _upload(self, method, file_field, filename, data, caption, content_type, timeout) -> int:
        fields = {"chat_id": self._chat_id, "caption": caption[:1024]}
        body, header = _multipart(fields, file_field, filename, data, content_type)
        req = urllib.request.Request(f"{self._base}/{method}", data=body, headers={"Content-Type": header})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())["result"]["message_id"]

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

    def react(self, message_id: int, emoji: str | None) -> None:
        reaction = [{"type": "emoji", "emoji": emoji}] if emoji else []
        self._call_quietly(
            "setMessageReaction",
            {"chat_id": self._chat_id, "message_id": message_id, "reaction": reaction},
        )

    def typing(self) -> None:
        self._call_quietly("sendChatAction", {"chat_id": self._chat_id, "action": "typing"})

    def _call_quietly(self, method: str, params: dict) -> None:
        """Indicators are best-effort: a failure must never break the reply."""
        try:
            self._call(method, params, _CALL_TIMEOUT)
        except (urllib.error.URLError, TimeoutError, KeyError):
            pass

    def poll(self, offset: int) -> list[Update]:
        result = self._call(
            "getUpdates",
            {"timeout": _POLL_WAIT, "offset": offset, "allowed_updates": ["message", "callback_query"]},
            _POLL_TIMEOUT,
        )
        return [u for item in result["result"] if (u := self._to_update(item)) is not None]

    def _to_update(self, item: dict) -> Update | None:
        if "callback_query" in item:
            return self._to_callback(item)
        message = item.get("message")
        if not message or str(message["chat"]["id"]) != self._chat_id:
            return None
        return Update(
            update_id=item["update_id"],
            chat_id=message["chat"]["id"],
            text=message.get("text", ""),
            at=datetime.fromtimestamp(message["date"], tz=timezone.utc),
            message_id=message["message_id"],
        )

    def _to_callback(self, item: dict) -> Update | None:
        query = item["callback_query"]
        message = query.get("message")
        if not message or str(message["chat"]["id"]) != self._chat_id:
            return None
        return Update(
            update_id=item["update_id"],
            chat_id=message["chat"]["id"],
            text="",
            at=datetime.fromtimestamp(message["date"], tz=timezone.utc),
            message_id=message["message_id"],
            callback_data=query.get("data", ""),
            callback_id=query["id"],
        )


def _multipart(
    fields: dict, file_field: str, filename: str, data: bytes, content_type: str = "image/png"
) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n".encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"
