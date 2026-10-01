from datetime import datetime

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.actions import Action, BrainResult
from mentor.domain.tasks import Task
from mentor.usecases import work
from tests.fixed_clock import FixedClock

_CLOCK = FixedClock(datetime(2026, 10, 1, 10, 0))


def _result(outcome, reply="report", **args):
    full = {"outcome": outcome, **args}
    return BrainResult(reply=reply, actions=[Action("task_result", full)], raw={})


def _setup(tmp_path, *tasks, results=()):
    store = FileStore(tmp_path)
    store.write_tasks(list(tasks))
    return store, FakeBrain(list(results)), FakeChat()


def _status(store):
    return {t.id: t.status for t in store.read_tasks()}


def test_done_sends_report_and_file_then_picks_next(tmp_path):
    store, brain, chat = _setup(tmp_path, Task("a", "Research"), Task("b", "Write", kind="writing", deps=["a"]),
                                results=[_result("done", "found it", files=["notes.md"]), _result("done")])
    (tmp_path / "work" / "a").mkdir(parents=True)
    (tmp_path / "work" / "a" / "notes.md").write_text("notes")
    work.run(store, brain, chat, _CLOCK)
    assert _status(store) == {"a": "done", "b": "done"}
    assert (tmp_path / "work" / "a" / "report.md").read_text() == "found it"
    assert chat.documents == [("notes.md", "", 5)]
    assert str(tmp_path / "work" / "a" / "report.md") in brain.tasks[1].prompt
    assert brain.tasks[0].write and brain.tasks[0].cwd == str(tmp_path / "work" / "a")
    assert "Work loop finished" in chat.outbox[-2] and chat.pinned


def test_file_outside_work_dir_is_not_sent(tmp_path):
    (tmp_path / "secret.txt").write_text("x")
    store, brain, chat = _setup(tmp_path, Task("a", "A"), results=[_result("done", files=["../../secret.txt"])])
    work.run(store, brain, chat, _CLOCK)
    assert chat.documents == []


def test_user_task_parked_and_independent_task_still_runs(tmp_path):
    store, brain, chat = _setup(tmp_path, Task("u", "Submit form", kind="user", note="use the draft"),
                                Task("r", "Research"), results=[_result("done")])
    work.run(store, brain, chat, _CLOCK)
    assert _status(store) == {"u": "awaiting_user", "r": "done"}
    assert chat.outbox[0] == "Your turn: Submit form\n\nuse the draft"
    assert chat.buttons[1] == [("Done", "t:u:done")]
    assert store.read_state()["work"] == {"date": "2026-10-01", "runs": 1}


def test_needs_approval_stores_proposal_and_sends_buttons(tmp_path):
    store, brain, chat = _setup(tmp_path, Task("s", "Set up VM", kind="system"),
                                results=[_result("needs_approval", proposal="incus launch")])
    work.run(store, brain, chat, _CLOCK)
    (task,) = store.read_tasks()
    assert task.status == "awaiting_approval" and task.proposal == "incus launch"
    assert chat.buttons[1] == [("Approve", "t:s:ok"), ("Approve · codex", "t:s:alt"), ("Reject", "t:s:no")]


def test_needs_user_sends_action_with_done_button(tmp_path):
    results = [_result("needs_user", user_action="Click submit")]
    store, brain, chat = _setup(tmp_path, Task("a", "Apply"), results=results)
    work.run(store, brain, chat, _CLOCK)
    assert _status(store) == {"a": "awaiting_user"}
    assert "Click submit" in chat.outbox[1] and [("Done", "t:a:done")] in chat.buttons.values()


def test_failed_blocks_dependants(tmp_path):
    store, brain, chat = _setup(tmp_path, Task("a", "A"), Task("b", "B", deps=["a"]), results=[_result("failed")])
    work.run(store, brain, chat, _CLOCK)
    assert _status(store) == {"a": "failed", "b": "todo"} and len(brain.tasks) == 1


def test_brain_error_counts_as_failed(tmp_path):
    error = BrainResult(reply="brain error: timeout", actions=[], raw={})
    store, brain, chat = _setup(tmp_path, Task("a", "A"), results=[error])
    work.run(store, brain, chat, _CLOCK)
    assert _status(store) == {"a": "failed"} and "brain error: timeout" in chat.outbox[0]


def test_budget_stops_loop(tmp_path):
    store, brain, chat = _setup(tmp_path, Task("a", "A"), Task("b", "B"), results=[_result("done")])
    store.write_state({"work": {"date": "2026-10-01", "runs": 11}})
    assert "daily budget used" in work.run(store, brain, chat, _CLOCK)
    assert _status(store) == {"a": "done", "b": "todo"}


def test_nothing_ready_sends_nothing_and_resets_stale_running(tmp_path):
    store, brain, chat = _setup(tmp_path, Task("a", "A", status="running"), results=[_result("done")])
    work.run(store, brain, chat, _CLOCK)
    assert _status(store) == {"a": "done"}
    store, brain, chat = _setup(tmp_path / "x", Task("a", "A", status="done"))
    assert work.run(store, brain, chat, _CLOCK) == "nothing ready" and chat.outbox == []


def test_tiers_and_provider_override(tmp_path):
    store, brain, chat = _setup(tmp_path, Task("c", "Code", kind="coding"), Task("r", "Read"),
                                Task("o", "Other", provider="claude"), results=[_result("done")] * 3)
    work.run(store, brain, chat, _CLOCK)
    raw = store.read_settings()
    assert brain.tasks[0].settings.provider == "claude" and brain.tasks[0].timeout == 1800
    assert brain.tasks[1].settings.model == raw["heavy"]["model"]
    assert brain.tasks[2].settings.provider == "claude"


def test_approved_proposal_is_in_prompt(tmp_path):
    store, brain, chat = _setup(tmp_path, Task("s", "VM", kind="system", approved=True, proposal="incus launch"),
                                results=[_result("done")])
    work.run(store, brain, chat, _CLOCK)
    assert "incus launch" in brain.tasks[0].prompt


def test_needs_user_hands_over_files_and_drafts(tmp_path):
    from mentor.adapters.mail.fake import FakeMail

    draft = {"to": "a@b.c", "subject": "Hi", "body": "text"}
    store, brain, chat = _setup(tmp_path, Task("a", "Apply"), results=[
        _result("needs_user", "prepared", files=["answers.md"], user_action="Submit the form", drafts=[draft])])
    (tmp_path / "work" / "a").mkdir(parents=True)
    (tmp_path / "work" / "a" / "answers.md").write_text("answers")
    mail = FakeMail()
    work.run(store, brain, chat, _CLOCK, mail)
    assert mail.drafts == [("a@b.c", "Hi", "text")] and chat.documents == [("answers.md", "", 7)]
    assert any("Submit the form" in m for m in chat.outbox) and _status(store) == {"a": "awaiting_user"}


def test_draft_text_is_sent_when_mail_is_not_configured(tmp_path):
    draft = {"to": "a@b.c", "subject": "Hi", "body": "the body"}
    store, brain, chat = _setup(tmp_path, Task("a", "Mail"), results=[_result("done", drafts=[draft])])
    work.run(store, brain, chat, _CLOCK)
    assert any("the body" in m and "a@b.c" in m for m in chat.outbox)


def test_new_proposal_clears_the_old_approval(tmp_path):
    store, brain, chat = _setup(tmp_path, Task("a", "Setup", approved=True, proposal="old"),
                                results=[_result("needs_approval", proposal="new")])
    work.run(store, brain, chat, _CLOCK)
    task = store.read_tasks()[0]
    assert (task.approved, task.proposal, task.status) == (False, "new", "awaiting_approval")
