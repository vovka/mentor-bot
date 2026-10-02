import json
from datetime import datetime

from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.actions import BrainResult, BrainTask
from mentor.domain import tasks
from mentor.usecases import replan
from tests.fixed_clock import FixedClock


def _doc(*titles: str) -> str:
    return json.dumps({"tasks": [{"id": f"p-{i}", "title": t} for i, t in enumerate(titles)]})


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
    brain = _DocBrain(_doc("item"), "moved items around")
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29))

    summary = replan.run(store, brain, chat, clock, reason="weekly replan")

    assert summary == "moved items around"
    assert chat.outbox == [tasks.render(store.read_tasks())]
    assert chat.pinned == [2]  # 1 is the progress message
    assert store.read_state()["pinned_message_id"] == 2
    assert chat.html_sent[0].startswith("⏳ Replanning") and chat.html_edits[-1][1].startswith("✅ Done: Replanning")
    assert store.read_state()["last_replan"] == "2026-09-29"
    assert store.read_plan() == tasks.render(store.read_tasks())
    assert [t.title for t in store.read_tasks()] == ["item"]
    assert brain.tasks[0].write is False


def test_second_run_edits_the_same_pinned_message(tmp_path):
    store = FileStore(tmp_path)
    store.write_plan("# old plan\n")
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29))
    replan.run(store, _DocBrain(_doc("v2"), "first change"), chat, clock, reason="first")

    replan.run(store, _DocBrain(_doc("v3"), "second change"), chat, clock, reason="second")

    assert len(chat.outbox) == 1
    assert chat.edits == [(2, tasks.render(store.read_tasks()))]
    assert store.read_state()["pinned_message_id"] == 2


def test_pinned_text_never_exceeds_telegram_limit(tmp_path):
    store = FileStore(tmp_path)
    store.write_plan("# old plan\n")
    brain = _DocBrain(_doc(*["x" * 100] * 60), "huge plan")
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
    assert summary == "plan unchanged (brain returned no document). nothing to change"


def test_invalid_document_changes_nothing_and_reports_error(tmp_path):
    store = FileStore(tmp_path)
    store.write_plan("# old plan\n")
    chat = FakeChat()
    clock = FixedClock(datetime(2026, 9, 29))

    summary = replan.run(store, _DocBrain("not json", "tried"), chat, clock, reason="bad")

    assert summary.startswith("Plan not changed: invalid JSON") and summary.endswith("tried")
    assert store.read_plan() == "# old plan\n" and store.read_tasks() == []
    assert store.read_state()["last_replan"] == "2026-09-29"


def test_ops_document_patches_existing_tasks(tmp_path):
    store = FileStore(tmp_path)
    store.write_tasks([tasks.Task("p-0", "keep"), tasks.Task("p-1", "move me")])
    ops = json.dumps({"ops": [{"op": "set", "id": "p-1", "due": "2026-10-05"}]})
    brain = _DocBrain(ops, "set a due date")
    summary = replan.run(store, brain, FakeChat(), FixedClock(datetime(2026, 9, 29)), reason="due")
    assert summary == "set a due date"
    assert [(t.id, t.due) for t in store.read_tasks()] == [("p-0", ""), ("p-1", "2026-10-05")]
    assert "p-1 | todo | research |  |  | deps= | move me" in brain.tasks[0].prompt
    assert brain.tasks[0].settings.model == "gpt-5.6-sol" and brain.tasks[0].settings.effort == "medium"
