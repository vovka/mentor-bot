from datetime import datetime

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.actions import BrainResult
from mentor.usecases import morning_brief
from tests.fixed_clock import FixedClock


def test_sends_once_and_is_idempotent_same_day(tmp_path):
    store = FileStore(tmp_path)
    brain = FakeBrain([BrainResult(reply="good morning", actions=[], raw={})])
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29, 8, 0))

    first = morning_brief.run(store, brain, chat, clock)
    assert first == "good morning"
    assert chat.outbox == ["good morning"]

    second = morning_brief.run(store, brain, chat, clock)
    assert second == "already sent"
    assert chat.outbox == ["good morning"]


def test_dry_run_sends_nothing_and_does_not_mark_state(tmp_path):
    store = FileStore(tmp_path)
    brain = FakeBrain([BrainResult(reply="draft brief", actions=[], raw={})])
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29, 8, 0))

    result = morning_brief.run(store, brain, chat, clock, dry_run=True)

    assert result == "draft brief"
    assert chat.outbox == []
    assert store.read_state().get("last_brief_date") is None


def test_no_duplicate_when_another_process_sent_it_meanwhile(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    clock = FixedClock(datetime(2026, 9, 29, 8, 0))

    class RacingBrain:
        def run(self, task):
            store.write_state({"last_brief_date": "2026-09-29"})  # the other process finished first
            return BrainResult(reply="good morning", actions=[], raw={})

    assert morning_brief.run(store, RacingBrain(), chat, clock) == "already sent"
    assert chat.outbox == []
