import sys
import types
from datetime import date, datetime, timezone

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.actions import Action, BrainResult
from mentor.domain.tasks import Task
from mentor.usecases import handle_message
from tests.fixed_clock import FixedClock

_CLOCK = FixedClock(datetime(2026, 9, 29, tzinfo=timezone.utc))


def test_set_settings_action_updates_settings_and_confirms(tmp_path):
    store = FileStore(tmp_path)
    brain = FakeBrain(
        [
            BrainResult(
                reply="switching model",
                actions=[Action(kind="set_settings", args={"model": "gpt-5.6-sol"})],
                raw={},
            )
        ]
    )
    chat = FakeChat()

    reply = handle_message.run(store, brain, chat, _CLOCK, "use gpt-5.6-sol")

    assert store.read_settings()["model"] == "gpt-5.6-sol"
    assert "gpt-5.6-sol" in reply
    assert chat.outbox == [reply]


def test_set_settings_bad_model_leaves_settings_unchanged(tmp_path):
    store = FileStore(tmp_path)
    original = store.read_settings()
    brain = FakeBrain(
        [
            BrainResult(
                reply="ok",
                actions=[Action(kind="set_settings", args={"model": "gpt-9000"})],
                raw={},
            )
        ]
    )
    chat = FakeChat()

    reply = handle_message.run(store, brain, chat, _CLOCK, "use gpt-9000")

    assert store.read_settings() == original
    assert "gpt-9000" in reply
    assert "allowed" in reply


def test_replan_action_queues_a_job_and_kicks(tmp_path):
    store, kicks, chat = FileStore(tmp_path), [], FakeChat()
    action = Action(kind="replan", args={"reason": "move demo to Friday"})
    brain = FakeBrain([BrainResult(reply="on it", actions=[action], raw={})])
    reply = handle_message.run(store, brain, chat, _CLOCK, "move demo to Friday", kick=lambda: kicks.append(1))
    jobs = store.read_state()["jobs"]
    assert [(j["kind"], j["args"]) for j in jobs] == [("replan", {"reason": "move demo to Friday"})]
    assert "Replanning queued (1st in line)." in reply and kicks == [1] and len(brain.tasks) == 1
    assert chat.html_sent == ["🕒 Queued (1st): Replanning"] and jobs[0]["message_id"] == 2
    assert chat.outbox == [reply]  # the answer (id 1) goes out before the queued message (id 2)


def test_add_task_action_inserts_at_top_and_kicks(tmp_path):
    store, kicks = FileStore(tmp_path), []
    store.write_tasks([Task("old", "Old")])
    args = {"title": "Investigate the forms", "note": "use the browser", "kind": "bogus", "project": None}
    brain = FakeBrain([BrainResult(reply="queued", actions=[Action("add_task", args)], raw={})])
    reply = handle_message.run(store, brain, FakeChat(), _CLOCK, "investigate", kick=lambda: kicks.append(1))
    first = store.read_tasks()[0]
    assert (first.id, first.status, first.kind, first.note) == ("investigate-the-forms", "todo", "research", "use the browser")
    assert "Queued as the next task" in reply and kicks == [1]


def test_history_records_user_and_bot_lines(tmp_path):
    store = FileStore(tmp_path)
    brain = FakeBrain([BrainResult(reply="hello", actions=[], raw={})])
    chat = FakeChat()

    handle_message.run(store, brain, chat, _CLOCK, "hi there")

    history = store.read_history(date.today())
    assert "user: hi there" in history
    assert "bot: hello" in history


def test_indicators_react_then_type_then_clear(tmp_path):
    store = FileStore(tmp_path)
    brain = FakeBrain([BrainResult(reply="hi", actions=[], raw={})])
    chat = FakeChat()

    handle_message.run(store, brain, chat, _CLOCK, "hello", message_id=42)

    assert chat.reactions == [(42, "👀"), (42, None)]
    assert chat.typing_calls >= 1


def test_heavy_action_switches_reaction_to_thinking(tmp_path, monkeypatch):
    store = FileStore(tmp_path)
    fake_scout = types.ModuleType("mentor.usecases.scout")
    fake_scout.run = lambda *a: "scouted"
    monkeypatch.setitem(sys.modules, "mentor.usecases.scout", fake_scout)
    brain = FakeBrain(
        [BrainResult(reply="looking", actions=[Action(kind="scout", args={"project": "x"})], raw={})]
    )
    chat = FakeChat()

    handle_message.run(store, brain, chat, _CLOCK, "what's in x?", message_id=7)

    assert chat.reactions == [(7, "👀"), (7, "🤔"), (7, None)]


def test_work_action_kicks_worker(tmp_path):
    kicks = []
    brain = FakeBrain([BrainResult(reply="on it", actions=[Action(kind="work", args={})], raw={})])
    reply = handle_message.run(FileStore(tmp_path), brain, FakeChat(), _CLOCK, "go", kick=lambda: kicks.append(1))
    assert "Working on the next task." in reply and kicks == [1]


def test_task_update_action(tmp_path):
    from mentor.domain.tasks import Task

    store, kicks = FileStore(tmp_path), []
    store.write_tasks([Task("a", "A")])
    actions = [
        Action(kind="task_update", args={"task_id": "a", "status": "done", "note": "sent"}),
        Action(kind="task_update", args={"task_id": "a", "status": "running"}),
        Action(kind="task_update", args={"task_id": "zz", "status": "done"}),
    ]
    brain = FakeBrain([BrainResult(reply="ok", actions=actions, raw={})])
    reply = handle_message.run(store, brain, FakeChat(), _CLOCK, "did A", kick=lambda: kicks.append(1))
    (task,) = store.read_tasks()
    assert (task.status, task.note, kicks) == ("done", "sent", [1])
    assert "must be one of" in reply and "no task with id 'zz'" in reply


def test_reply_quotes_the_users_message_and_queued_job_replies_too(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    brain = FakeBrain([BrainResult(reply="on it", actions=[Action("replan", {"reason": "x"})], raw={})])
    handle_message.run(store, brain, chat, _CLOCK, "replan please", message_id=42)
    assert chat.replies == {1: 42, 2: 42}  # 1 = queued message, 2 = the answer
    assert store.read_state()["jobs"][0]["reply_to"] == 42


def test_add_task_stores_the_requesting_message(tmp_path):
    store = FileStore(tmp_path)
    brain = FakeBrain([BrainResult(reply="ok", actions=[Action("add_task", {"title": "Look"})], raw={})])
    handle_message.run(store, brain, FakeChat(), _CLOCK, "look into it", message_id=42)
    assert store.read_tasks()[0].reply_to == 42
