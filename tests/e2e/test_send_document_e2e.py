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
