from datetime import datetime, timezone

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.actions import BrainResult
from mentor.domain.conversation import Update
from mentor.usecases import handle_update
from tests.fixed_clock import FixedClock


def test_replayed_update_id_is_deduped(tmp_path):
    store = FileStore(tmp_path)
    brain = FakeBrain([BrainResult(reply="hi", actions=[], raw={})])
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29, tzinfo=timezone.utc))
    update = Update(update_id=5, chat_id=1, text="hello", at=datetime.now(timezone.utc))

    handle_update.run(store, brain, chat, clock, update)
    assert chat.outbox == ["hi"]

    handle_update.run(store, brain, chat, clock, update)
    assert chat.outbox == ["hi"]


def test_blank_text_is_skipped_but_last_update_id_advances(tmp_path):
    store = FileStore(tmp_path)
    brain = FakeBrain([])  # would raise IndexError if handle_message were called
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29, tzinfo=timezone.utc))
    update = Update(update_id=9, chat_id=1, text="   \n\t", at=datetime.now(timezone.utc))

    handle_update.run(store, brain, chat, clock, update)

    assert chat.outbox == []
    assert store.read_state()["last_update_id"] == 9


def test_cancel_and_stale_buttons_reply_to_their_message(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    clock = FixedClock(datetime(2026, 9, 29, tzinfo=timezone.utc))
    at = datetime.now(timezone.utc)
    handle_update.run(store, FakeBrain([]), chat, clock, Update(1, 1, "/cancel", at, message_id=30))
    for n, data in ((2, "t:gone:ok"), (3, "yes")):
        update = Update(n, 1, "", at, message_id=40 + n, callback_data=data, callback_id=str(n))
        handle_update.run(store, FakeBrain([]), chat, clock, update)
    assert chat.outbox == ["Nothing is running.", "Already handled.", "Already handled."]
    assert chat.replies == {1: 30, 2: 42, 3: 43}
