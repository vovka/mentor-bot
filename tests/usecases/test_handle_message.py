import sys
import types
from datetime import date, datetime, timezone

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.actions import Action, BrainResult
from mentor.usecases import handle_message
from tests.fixed_clock import FixedClock

_CLOCK = FixedClock(datetime(2026, 9, 29, tzinfo=timezone.utc))


def test_set_settings_action_updates_settings_and_confirms(tmp_path):
    store = FileStore(tmp_path)
    brain = FakeBrain(
        [
            BrainResult(
                reply="switching model",
                actions=[Action(kind="set_settings", args={"model": "gpt-6-astra"})],
                raw={},
            )
        ]
    )
    chat = FakeChat()

    reply = handle_message.run(store, brain, chat, _CLOCK, "use gpt-6-astra")

    assert store.read_settings()["model"] == "gpt-6-astra"
    assert "gpt-6-astra" in reply
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


def test_replan_action_calls_replan_run_with_reason(tmp_path, monkeypatch):
    store = FileStore(tmp_path)
    calls = []
    fake_replan = types.ModuleType("mentor.usecases.replan")

    def fake_run(store_, brain_, chat_, clock_, reason):
        calls.append(reason)
        return "plan updated"

    fake_replan.run = fake_run
    monkeypatch.setitem(sys.modules, "mentor.usecases.replan", fake_replan)

    brain = FakeBrain(
        [
            BrainResult(
                reply="on it",
                actions=[Action(kind="replan", args={"reason": "move demo to Friday"})],
                raw={},
            )
        ]
    )
    chat = FakeChat()

    reply = handle_message.run(store, brain, chat, _CLOCK, "move demo to Friday")

    assert calls == ["move demo to Friday"]
    assert "plan updated" in reply


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
