import json

from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain import tasks
from mentor.domain.tasks import Task
from mentor.usecases import apply_plan


def _doc(**extra) -> str:
    return json.dumps({"tasks": [{"id": "a-1", "title": "A", **extra}]})


def test_valid_document_writes_tasks_renders_plan_and_pins(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    assert apply_plan.run(store, chat, _doc(), mark="x") is None
    assert [t.id for t in store.read_tasks()] == ["a-1"]
    assert store.read_plan() == tasks.render(store.read_tasks())
    assert chat.outbox == [store.read_plan()] and chat.pinned == [1]
    assert store.read_state()["mark"] == "x"


def test_invalid_document_returns_error_and_changes_nothing(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    store.write_plan("# old\n")
    assert "invalid JSON" in apply_plan.run(store, chat, "nope")
    assert store.read_tasks() == [] and store.read_plan() == "# old\n" and chat.outbox == []


def test_merge_keeps_running_status(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    store.write_tasks([Task(id="a-1", title="old", status="running")])
    assert apply_plan.run(store, chat, _doc(status="todo")) is None
    (task,) = store.read_tasks()
    assert task.title == "A" and task.status == "running"
