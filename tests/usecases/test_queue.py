import json
import os
import signal
from datetime import datetime

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.actions import Action, BrainResult
from mentor.domain.conversation import Update
from mentor.domain.tasks import Task
from mentor.usecases import add_task, handle_update, queue, work
from tests.fixed_clock import FixedClock

_CLOCK = FixedClock(datetime(2026, 10, 1, 10, 0))
_DONE = BrainResult(reply="report", actions=[Action("task_result", {"outcome": "done"})], raw={})


def _replanned(*ids):
    doc = json.dumps({"tasks": [{"id": i, "title": i.upper()} for i in ids]})
    return BrainResult(reply="replanned", actions=[], raw={}, document=doc)


def test_push_reports_position_and_posts_queued_message(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    assert queue.push(store, chat, "replan", {"reason": "x"}) == "Replanning queued (1st in line)."
    assert queue.push(store, chat, "replan", {"reason": "y"}) == "Replanning queued (2nd in line)."
    assert chat.html_sent == ["🕒 Queued (1st): Replanning", "🕒 Queued (2nd): Replanning"]
    assert [j["message_id"] for j in queue.pending(store)] == [1, 2]


def test_take_increments_attempts_and_keeps_the_job_until_done(tmp_path):
    store = FileStore(tmp_path)
    queue.push(store, FakeChat(), "replan", {"reason": "x"})
    job = queue.take(store)
    assert job["attempts"] == 1 and queue.take(store)["attempts"] == 2
    queue.done(store, job["id"])
    assert queue.take(store) is None


def test_executor_runs_queued_replan_first_in_the_queued_message(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    store.write_tasks([Task("a", "A")])
    queue.push(store, chat, "replan", {"reason": "move A"})
    brain = FakeBrain([_replanned("a", "b"), _DONE, _DONE])
    work.run(store, brain, chat, _CLOCK)
    assert not brain.tasks[0].write and "move A" in brain.tasks[0].prompt
    assert {t.id: t.status for t in store.read_tasks()} == {"a": "done", "b": "done"}
    on_queued = [text for mid, text in chat.html_edits if mid == 1]
    assert on_queued[0].startswith("⏳ Replanning") and on_queued[-1].startswith("✅ Done: Replanning")
    assert "replanned" in chat.outbox and queue.pending(store) == []


def test_job_taken_twice_is_dropped_with_a_message(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    queue.push(store, chat, "replan", {"reason": "x"})
    queue.take(store), queue.take(store)
    work.run(store, FakeBrain([]), chat, _CLOCK)
    assert chat.outbox == ["Gave up on replanning after 2 attempts."] and queue.pending(store) == []


def test_jobs_do_not_consume_daily_runs(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    store.write_tasks([Task("a", "A")])
    (tmp_path / "settings.json").write_text(json.dumps({**store.read_settings(), "work": {"daily_runs": 1}}))
    queue.push(store, chat, "replan", {"reason": "x"})
    work.run(store, FakeBrain([_replanned("a"), _DONE]), chat, _CLOCK)
    assert store.read_tasks()[0].status == "done"
    assert store.read_state()["work"]["runs"] == 1


def test_add_task_goes_first_and_runs_next(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    store.write_tasks([Task("a", "A")])
    add_task.run(store, chat, lambda: None, {"title": "A", "note": "", "kind": "coding", "project": None})
    assert [t.id for t in store.read_tasks()] == ["a-2", "a"]
    brain = FakeBrain([_DONE, _DONE])
    work.run(store, brain, chat, _CLOCK)
    assert "/a-2" in brain.tasks[0].cwd


def test_job_is_stored_with_its_queued_message_id(tmp_path):
    store, seen = FileStore(tmp_path), []

    class Chat(FakeChat):
        def send_html(self, text, reply_to=None):
            seen.append(queue.pending(store))  # the job is appended only after its message exists
            return super().send_html(text, reply_to)

    queue.push(store, Chat(), "replan", {"reason": "x"})
    assert seen == [[]] and queue.pending(store)[0]["message_id"] == 1


def test_cancel_sends_sigusr1_to_our_executor(tmp_path, monkeypatch):
    store, chat, killed = FileStore(tmp_path), FakeChat(), []
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(handle_update, "_is_executor", lambda pid: True)
    store.write_state({"executor_pid": 4242})
    store.write_tasks([Task("a", "Fix the form", status="running")])
    handle_update.run(store, FakeBrain([]), chat, _CLOCK, Update(1, 1, "/cancel", datetime.now()))
    assert killed == [(4242, signal.SIGUSR1)] and chat.outbox == ["Cancelling: Fix the form"]
    store.write_state({**store.read_state(), "executor_pid": None})
    handle_update.run(store, FakeBrain([]), chat, _CLOCK, Update(2, 1, "/cancel", datetime.now()))
    assert chat.outbox[-1] == "Nothing is running." and len(killed) == 1


def test_cancel_ignores_a_pid_that_is_not_our_executor(tmp_path, monkeypatch):
    store, chat, killed = FileStore(tmp_path), FakeChat(), []
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append((pid, sig)))
    store.write_state({"executor_pid": os.getpid()})  # alive, but pytest, not `mentor job work`
    handle_update.run(store, FakeBrain([]), chat, _CLOCK, Update(1, 1, "/cancel", datetime.now()))
    assert killed == [] and chat.outbox == ["Nothing is running."]
    assert store.read_state()["executor_pid"] is None
