"""E2E: 08:00 check-in buttons over the Bot API stub: keyboard sent, callback polled, keyboard cleared."""

from datetime import datetime

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.api import TelegramChat
from mentor.usecases import handle_update, morning_checkin
from tests.e2e.bot_api_stub import BotApiStub
from tests.fixed_clock import FixedClock


def test_no_button_round_trip(tmp_path, monkeypatch):
    stub = BotApiStub()
    monkeypatch.setenv("TELEGRAM_API_BASE", stub.base_url)
    store = FileStore(tmp_path)
    store.write_state({"last_brief_date": "2026-09-29"})
    chat, brain = TelegramChat("stub-token", str(stub.chat_id)), FakeBrain([])
    clock = FixedClock(datetime(2026, 9, 30, 8, 0))

    morning_checkin.morning(store, brain, chat, clock)
    markup = stub.calls[-1][1]["reply_markup"]["inline_keyboard"][0]
    assert [b["callback_data"] for b in markup] == ["yes", "no"]

    stub.enqueue_callback("no", message_id=1)
    stub.enqueue_callback("yes", message_id=1, chat_id=666)  # foreign chat: dropped
    updates = chat.poll(1)
    assert len(updates) == 1 and stub.calls[-1][1]["allowed_updates"] == ["message", "callback_query"]
    handle_update.run(store, brain, chat, clock, updates[0])

    methods = [c[0] for c in stub.calls[-3:]]
    assert methods == ["answerCallbackQuery", "editMessageReplyMarkup", "sendMessage"]
    assert store.read_state()["checkin"]["stage"] == "awaiting_updates"
    stub.stop()
