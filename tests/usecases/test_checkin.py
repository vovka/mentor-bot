import json
from datetime import datetime

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.actions import BrainResult
from mentor.domain import tasks
from mentor.domain.conversation import Update
from mentor.usecases import handle_update, morning_checkin, work
from tests.fixed_clock import FixedClock

_DOC = json.dumps({"tasks": [{"id": "a-1", "title": "do A today"}]})
_BRIEF = BrainResult(reply="good morning", actions=[], raw={})
_PROPOSAL = BrainResult(reply="moved A to today", actions=[], raw={}, document=_DOC)
_NOTHING = BrainResult(reply="all done", actions=[], raw={}, document=None)


def _setup(tmp_path, results, history="bot: yesterday's brief\n"):
    store = FileStore(tmp_path)
    store.write_plan("# old plan\n")
    store.write_state({"last_brief_date": "2026-09-29", "pinned_message_id": 99})
    (tmp_path / "history" / "2026-09-29.md").write_text(history)
    return store, FakeBrain(results), FakeChat(), FixedClock(datetime(2026, 9, 30, 8, 0))


def _press(env, data, message_id, update_id):
    store, brain, chat, clock = env
    update = Update(update_id, 1, "", datetime.now(), message_id, callback_data=data, callback_id=f"cb{update_id}")
    handle_update.run(store, brain, chat, clock, update, kick=lambda: work.drain_jobs(store, brain, chat, clock))


def _drained(job, store, brain, chat, clock):
    """Run a check-in job, then any queued job the executor would pick up."""
    result = job(store, brain, chat, clock)
    work.drain_jobs(store, brain, chat, clock)
    return result


def _checkin(store):
    return store.read_state().get("checkin")


def test_no_updates_asks_with_yes_no_buttons(tmp_path):
    store, brain, chat, clock = _setup(tmp_path, [])
    _drained(morning_checkin.morning, store, brain, chat, clock)
    assert chat.outbox == [morning_checkin.QUESTION]
    assert chat.buttons[1] == [("Yes", "yes"), ("No", "no")]
    assert _checkin(store) == {"date": "2026-09-30", "stage": "asked", "message_id": 1}
    assert morning_checkin.morning(store, brain, chat, clock) == "already sent"


def test_yes_proposes_without_touching_plan(tmp_path):
    env = _setup(tmp_path, [_PROPOSAL])
    store, brain, chat, clock = env
    _drained(morning_checkin.morning, store, brain, chat, clock)
    _press(env, "yes", 1, 1)
    assert chat.outbox[-1] == "moved A to today"
    assert chat.buttons[3] == [("Approve", "approve"), ("Reject", "reject")]
    assert chat.answered == ["cb1"] and chat.cleared == [1]
    assert store.read_plan() == "# old plan\n"
    assert _checkin(store)["stage"] == "proposed"
    assert brain.tasks[0].settings.model == "gpt-5.6-sol" and brain.tasks[0].settings.effort == "medium"


def test_approve_writes_plan_edits_pin_sends_brief(tmp_path):
    env = _setup(tmp_path, [_PROPOSAL, _BRIEF])
    store, brain, chat, clock = env
    _drained(morning_checkin.morning, store, brain, chat, clock)
    _press(env, "yes", 1, 1)
    _press(env, "approve", 3, 2)  # 2 is the reconcile progress message
    assert [t.title for t in store.read_tasks()] == ["do A today"]
    assert store.read_plan() == tasks.render(store.read_tasks())
    assert chat.edits == [(99, store.read_plan())]
    assert chat.outbox[-1] == "good morning"
    assert _checkin(store) is None and store.read_state()["last_brief_date"] == "2026-09-30"


def test_reject_leaves_plan_and_asks_what_to_change(tmp_path):
    env = _setup(tmp_path, [_PROPOSAL])
    store, brain, chat, clock = env
    _drained(morning_checkin.morning, store, brain, chat, clock)
    _press(env, "yes", 1, 1)
    _press(env, "reject", 3, 2)
    assert store.read_plan() == "# old plan\n"
    assert chat.outbox[-1] == "What should I change instead?"
    assert _checkin(store) is None


def test_no_then_message_reconciles(tmp_path):
    env = _setup(tmp_path, [BrainResult(reply="noted", actions=[], raw={}), _PROPOSAL])
    store, brain, chat, clock = env
    _drained(morning_checkin.morning, store, brain, chat, clock)
    _press(env, "no", 1, 1)
    assert chat.outbox[-1] == "OK, send me your updates by 09:00."
    kick = lambda: work.drain_jobs(store, brain, chat, clock)  # noqa: E731
    handle_update.run(store, brain, chat, clock, Update(2, 1, "did A, not B", datetime.now()), kick=kick)
    assert chat.outbox[-2:] == ["noted", "moved A to today"]
    assert _checkin(store)["stage"] == "proposed"


def test_deadline_reconciles_when_pending_else_noop(tmp_path):
    store, brain, chat, clock = _setup(tmp_path, [_PROPOSAL])
    assert morning_checkin.deadline(store, brain, chat, clock) == "no pending check-in"
    _drained(morning_checkin.morning, store, brain, chat, clock)
    _drained(morning_checkin.deadline, store, brain, chat, clock)
    assert chat.outbox[-2:] == [morning_checkin.DEADLINE_NOTICE, "moved A to today"]
    assert morning_checkin.deadline(store, brain, chat, clock) == "no pending check-in"


def test_stale_button_is_already_handled(tmp_path):
    env = _setup(tmp_path, [_PROPOSAL])
    store, brain, chat, clock = env
    _drained(morning_checkin.morning, store, brain, chat, clock)
    _press(env, "yes", 1, 1)
    _press(env, "no", 1, 2)
    _press(env, "approve", 7, 3)
    assert chat.outbox[-2:] == ["Already handled.", "Already handled."]
    assert _checkin(store)["stage"] == "proposed" and store.read_plan() == "# old plan\n"


def test_updates_with_empty_proposal_send_plain_brief(tmp_path):
    store, brain, chat, clock = _setup(tmp_path, [_NOTHING, _BRIEF], history="user: done A\nbot: great\n")
    _drained(morning_checkin.morning, store, brain, chat, clock)
    assert chat.outbox == ["good morning"]
    assert _checkin(store) is None


def test_invalid_proposal_is_dropped_with_error_then_brief(tmp_path):
    bad = BrainResult(reply="moved A", actions=[], raw={}, document="{nope")
    store, brain, chat, clock = _setup(tmp_path, [bad, _BRIEF], history="user: done A\n")
    _drained(morning_checkin.morning, store, brain, chat, clock)
    assert chat.outbox[-2].startswith("Plan proposal discarded: invalid JSON")
    assert chat.outbox[-1] == "good morning"
    assert _checkin(store) is None and store.read_tasks() == []


def test_ops_proposal_is_applied_on_approve_to_current_tasks(tmp_path):
    ops = json.dumps({"ops": [{"op": "set", "id": "a-1", "due": "2026-09-30"}]})
    proposal = BrainResult(reply="A due today", actions=[], raw={}, document=ops)
    env = _setup(tmp_path, [proposal, _BRIEF])
    store, brain, chat, clock = env
    store.write_tasks([tasks.Task("a-1", "A")])
    _drained(morning_checkin.morning, store, brain, chat, clock)
    _press(env, "yes", 1, 1)
    assert _checkin(store)["document"] == ops and store.read_tasks()[0].due == ""
    store.write_tasks([*store.read_tasks(), tasks.Task("b-1", "B")])
    _press(env, "approve", 3, 2)  # 2 is the reconcile progress message
    assert [(t.id, t.due) for t in store.read_tasks()] == [("a-1", "2026-09-30"), ("b-1", "")]


def test_ops_proposal_failing_the_dry_run_is_discarded(tmp_path):
    ops = json.dumps({"ops": [{"op": "set", "id": "a-1", "deps": ["ghost"]}]})
    bad = BrainResult(reply="x", actions=[], raw={}, document=ops)
    store, brain, chat, clock = _setup(tmp_path, [bad, _BRIEF], history="user: done A\n")
    store.write_tasks([tasks.Task("a-1", "A")])
    _drained(morning_checkin.morning, store, brain, chat, clock)
    assert "Plan proposal discarded: task a-1: unknown dep ghost" in chat.outbox
    assert _checkin(store) is None


def test_checkin_reconcile_runs_inline_not_queued(tmp_path):
    store, brain, chat, clock = _setup(tmp_path, [_NOTHING, _BRIEF], history="user: done A\n")
    morning_checkin.morning(store, brain, chat, clock)
    assert store.read_state().get("jobs", []) == [] and len(brain.tasks) == 2
    assert store.read_state()["last_brief_date"] == "2026-09-30"


class _Crashing(FakeBrain):
    def run(self, task):
        if not self.tasks:
            self.tasks.append(task)
            raise RuntimeError("boom")
        return super().run(task)


def test_reconcile_crash_clears_checkin_and_sends_brief_once(tmp_path):
    env = _setup(tmp_path, [])
    store, _, chat, clock = env
    brain = _Crashing([_BRIEF])
    morning_checkin.morning(store, brain, chat, clock)
    _press((store, brain, chat, clock), "yes", 1, 1)
    assert "Plan proposal discarded: reconcile failed: boom" in chat.outbox
    assert chat.outbox.count("good morning") == 1 and _checkin(store) is None
