"""E2E: TelegramChat.send_document uploads multipart to the stub's sendDocument."""

from mentor.adapters.telegram.api import TelegramChat
from tests.e2e.bot_api_stub import BotApiStub


def test_send_document_hits_send_document(monkeypatch):
    stub = BotApiStub()
    monkeypatch.setenv("TELEGRAM_API_BASE", stub.base_url)

    msg_id = TelegramChat("stub-token", str(stub.chat_id)).send_document(b"hello", "notes.md", "cap")

    assert msg_id == 1
    method, payload = stub.calls[-1]
    assert method == "sendDocument" and payload["_bytes"] > 5
    stub.stop()


def test_edit_tolerates_an_unchanged_message(monkeypatch):
    import io
    import urllib.error

    def not_modified(*args, **kwargs):
        body = io.BytesIO(b'{"ok":false,"description":"Bad Request: message is not modified"}')
        raise urllib.error.HTTPError("u", 400, "Bad Request", {}, body)

    chat = TelegramChat("token", "1")
    monkeypatch.setattr(chat, "_call", not_modified)
    chat.edit(17, "same text")
