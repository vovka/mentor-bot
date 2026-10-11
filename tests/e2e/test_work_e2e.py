"""E2E: the work loop and its task buttons over the Bot API stub."""

from datetime import datetime

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.api import TelegramChat
from mentor.domain.actions import Action, BrainResult
from mentor.domain.tasks import Task
from mentor.usecases import handle_update, work
from tests.e2e.bot_api_stub import BotApiStub
from tests.fixed_clock import FixedClock

_CLOCK = FixedClock(datetime(2026, 10, 1, 10, 0))


def _result(outcome, **args):
    return BrainResult(reply=f"{outcome} report", actions=[Action("task_result", {"outcome": outcome, **args})], raw={})


def _env(tmp_path, monkeypatch, tasks, results):
    stub = BotApiStub()
    monkeypatch.setenv("TELEGRAM_API_BASE", stub.base_url)
    store = FileStore(tmp_path)
    store.write_tasks(tasks)
    return stub, store, TelegramChat("stub-token", str(stub.chat_id)), FakeBrain(results)


def _press(stub, store, brain, chat, data):
    """Press the button carrying `data`; the kick runs the worker inline."""
    message_id = next(i for i, (m, p) in enumerate(_sent(stub), 1) if data in str(p.get("reply_markup")))
    stub.enqueue_callback(data, message_id=message_id)
    for update in chat.poll(1):
        handle_update.run(store, brain, chat, _CLOCK, update, kick=lambda: work.run(store, brain, chat, _CLOCK))


def _sent(stub):
    return [c for c in stub.calls if c[0] in ("sendMessage", "sendPhoto", "sendDocument")]


def test_ready_task_done_with_file(tmp_path, monkeypatch):
    stub, store, chat, brain = _env(tmp_path, monkeypatch, [Task("a", "Draft")], [_result("done", files=["d.md"], send=["d.md"])])
    (tmp_path / "work" / "a").mkdir(parents=True)
    (tmp_path / "work" / "a" / "d.md").write_text("draft")
    work.run(store, brain, chat, _CLOCK)
    assert "sendDocument" in [c[0] for c in stub.calls] and store.read_tasks()[0].status == "done"
    stub.stop()


def test_risky_task_approved_then_done(tmp_path, monkeypatch):
    results = [_result("needs_approval", proposal="install incus"), _result("done")]
    stub, store, chat, brain = _env(tmp_path, monkeypatch, [Task("s", "VM", kind="system")], results)
    work.run(store, brain, chat, _CLOCK)
    _press(stub, store, brain, chat, "t:s:ok")
    assert "install incus" in brain.tasks[1].prompt and store.read_tasks()[0].status == "done"
    stub.stop()


def test_user_task_done_press_runs_next(tmp_path, monkeypatch):
    tasks = [Task("u", "Submit", kind="user"), Task("n", "Follow up", deps=["u"])]
    stub, store, chat, brain = _env(tmp_path, monkeypatch, tasks, [_result("done")])
    work.run(store, brain, chat, _CLOCK)
    _press(stub, store, brain, chat, "t:u:done")
    assert [t.status for t in store.read_tasks()] == ["done", "done"] and len(brain.tasks) == 1
    stub.stop()


def test_progress_message_is_html_and_edited_in_place(tmp_path, monkeypatch):
    stub, store, chat, brain = _env(tmp_path, monkeypatch, [Task("a", "Draft <x>")], [_result("done")])
    work.run(store, brain, chat, _CLOCK)
    first = next(p for m, p in stub.calls if m == "sendMessage")
    final = [p for m, p in stub.calls if m == "editMessageText" and p.get("parse_mode") == "HTML"][-1]
    assert first["parse_mode"] == "HTML" and first["text"].startswith("⏳ Draft &lt;x&gt;")
    assert final["message_id"] == 1 and final["text"].startswith("✅ Done: Draft &lt;x&gt;")
    stub.stop()
