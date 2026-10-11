from datetime import datetime

from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.conversation import Update
from mentor.domain.tasks import Task
from mentor.usecases import task_buttons


def _press(tmp_path, status, data, kind="research"):
    store, chat, kicks = FileStore(tmp_path), FakeChat(), []
    store.write_tasks([Task("a", "A", kind=kind, status=status)])
    update = Update(1, 1, "", datetime(2026, 10, 1), message_id=9, callback_data=data, callback_id="cb")
    result = task_buttons.on_button(store, chat, update, lambda: kicks.append(1))
    return result, store.read_tasks()[0], chat, kicks


def test_ok_approves_and_kicks(tmp_path):
    _, task, chat, kicks = _press(tmp_path, "awaiting_approval", "t:a:ok")
    assert (task.status, task.approved, kicks) == ("todo", True, [1])
    assert chat.answered == ["cb"] and chat.cleared == [9]


def test_alt_switches_to_other_provider(tmp_path):
    _, task, _, kicks = _press(tmp_path, "awaiting_approval", "t:a:alt")
    assert (task.status, task.approved, task.provider, kicks) == ("todo", True, "claude", [1])


def test_no_asks_what_instead_without_kick(tmp_path):
    _, task, chat, kicks = _press(tmp_path, "awaiting_approval", "t:a:no")
    assert task.status == "awaiting_user" and "Rejected" in task.note
    assert "What should I do instead?" in chat.outbox and kicks == []


def test_done_marks_done_and_kicks(tmp_path):
    _, task, _, kicks = _press(tmp_path, "awaiting_user", "t:a:done")
    assert task.status == "done" and kicks == [1]


def test_stale_press(tmp_path):
    result, task, chat, kicks = _press(tmp_path, "done", "t:a:ok")
    assert result == "stale" and chat.outbox == ["Already handled."] and kicks == []
