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
