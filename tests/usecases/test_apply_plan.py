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


def _ops(*ops) -> str:
    return json.dumps({"ops": list(ops)})


def test_ops_patch_leaves_other_tasks_and_reports_skips(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    store.write_tasks([Task(id="a-1", title="A"), Task(id="b-1", title="B", status="running")])
    doc = _ops({"op": "set", "id": "a-1", "note": "n"}, {"op": "set", "id": "zz", "note": "x"})
    assert apply_plan.run(store, chat, doc) is None
    a, b = store.read_tasks()
    assert a.note == "n" and b.status == "running"
    assert chat.outbox[0] == "Plan patch notes:\nset zz: unknown task"


def test_invalid_ops_change_nothing(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    store.write_tasks([Task(id="a-1", title="A")])
    error = apply_plan.run(store, chat, _ops({"op": "set", "id": "a-1", "deps": ["a-1"]}))
    assert "cycle" in error and store.read_tasks()[0].deps == []


def test_full_document_still_rewrites(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    store.write_tasks([Task(id="a-1", title="old"), Task(id="b-1", title="B")])
    assert apply_plan.run(store, chat, _doc()) is None
    assert [t.id for t in store.read_tasks()] == ["a-1"]


def test_ops_apply_on_top_of_a_change_made_after_the_brain_started(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    store.write_tasks([Task(id="a-1", title="A")])
    doc = _ops({"op": "add", "task": {"id": "n-1", "title": "N"}, "after": "a-1"})
    store.write_tasks([*store.read_tasks(), Task(id="late", title="added meanwhile")])
    apply_plan.run(store, chat, doc)
    assert [t.id for t in store.read_tasks()] == ["a-1", "n-1", "late"]
