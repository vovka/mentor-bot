from datetime import datetime

from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.actions import BrainResult, BrainTask
from mentor.usecases import replan
from tests.fixed_clock import FixedClock


class _DocBrain:
    """Fake brain that returns a document instead of writing plan.md, per the read-only sandbox."""

    def __init__(self, document: str | None, reply: str):
        self._document = document
        self._reply = reply
        self.tasks: list[BrainTask] = []

    def run(self, task: BrainTask) -> BrainResult:
        self.tasks.append(task)
        return BrainResult(reply=self._reply, actions=[], raw={}, document=self._document)


def test_first_run_sends_and_pins_and_stores_id(tmp_path):
    store = FileStore(tmp_path)
    store.write_plan("# old plan\n")
    brain = _DocBrain("# new plan\n- [ ] item\n", "moved items around")
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29))

    summary = replan.run(store, brain, chat, clock, reason="weekly replan")

    assert summary == "moved items around"
    assert chat.outbox == ["# new plan\n- [ ] item\n"]
    assert chat.pinned == [1]
    assert store.read_state()["pinned_message_id"] == 1
    assert store.read_state()["last_replan"] == "2026-09-29"
    assert store.read_plan() == "# new plan\n- [ ] item\n"
    assert brain.tasks[0].write is False


def test_second_run_edits_the_same_pinned_message(tmp_path):
    store = FileStore(tmp_path)
    store.write_plan("# old plan\n")
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29))
    replan.run(store, _DocBrain("# plan v2\n", "first change"), chat, clock, reason="first")

    replan.run(store, _DocBrain("# plan v3\n", "second change"), chat, clock, reason="second")

    assert chat.outbox == ["# plan v2\n"]
    assert chat.edits == [(1, "# plan v3\n")]
    assert store.read_state()["pinned_message_id"] == 1


def test_pinned_text_never_exceeds_telegram_limit(tmp_path):
    store = FileStore(tmp_path)
    store.write_plan("# old plan\n")
    brain = _DocBrain("x" * 5000, "huge plan")
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29))

    replan.run(store, brain, chat, clock, reason="big")

    assert len(chat.outbox[0]) <= 4096


def test_no_document_leaves_plan_unchanged(tmp_path):
    store = FileStore(tmp_path)
    store.write_plan("# old plan\n")
    brain = _DocBrain(None, "nothing to change")
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29))

    summary = replan.run(store, brain, chat, clock, reason="noop")

    assert store.read_plan() == "# old plan\n"
    assert summary == "plan.md unchanged (brain returned no document). nothing to change"
