from mentor.adapters.agent.fake import FakeAgent
from mentor.adapters.agent.agents import Agents
from mentor.adapters.store.files import FileStore
from mentor.domain.agent import AgentResult
from mentor.usecases.chat_turn import ChatTurn

LIMIT = AgentResult("", "s1", error="You've hit your usage limit.", limited=True)


def _turn(tmp_path, codex, claude=None):
    store = FileStore(tmp_path)
    return store, ChatTurn(store, Agents({"codex": codex, "claude": claude or FakeAgent()}), str(tmp_path))


def test_new_session_is_seeded_then_resumed(tmp_path):
    codex = FakeAgent(AgentResult("hello", "s1"), AgentResult("again", "s1"))
    store, turn = _turn(tmp_path, codex)
    store.write_context("User is job hunting.")
    store.change_agenda("task_add", {}, "user", lambda g: g.add_task("Send CV"))
    assert turn.run(["[10:00] you: hi"]) == "hello"
    first = codex.requests[0]
    assert not first.session and "User is job hunting." in first.prompt and "t1 Send CV" in first.prompt
    assert first.tier.model == "gpt-5.6-luna" and first.role == "chat"
    assert turn.run(["[10:01] you: and?"]) == "again"
    assert codex.requests[1].session == "s1" and codex.requests[1].prompt == "[10:01] you: and?\n(Reply in English.)"


def test_usage_limit_moves_the_day_to_the_fallback(tmp_path):
    codex = FakeAgent(LIMIT)
    claude = FakeAgent(AgentResult("from haiku", "c1"), AgentResult("still haiku", "c1"))
    store, turn = _turn(tmp_path, codex, claude)
    store.append_history("[09:00] you: earlier line")
    store.append_history("[10:00] you: hi")
    assert turn.run(["[10:00] you: hi"]) == "from haiku"
    assert claude.requests[0].tier.model == "haiku" and "earlier line" in claude.requests[0].prompt
    assert store.read_state()["chat"] == {"tier": "chat_fallback", "session": "c1"}
    assert turn.run(["[10:05] you: x"]) == "still haiku" and len(codex.requests) == 1


def test_broken_session_restarts_from_transcript(tmp_path):
    codex = FakeAgent(AgentResult("", "old", error="no such session"), AgentResult("fresh", "s2"))
    store, turn = _turn(tmp_path, codex)
    store.update_state(chat={"tier": "chat", "session": "old"})
    assert turn.run(["[10:00] you: hi"]) == "fresh"
    assert codex.requests[1].session == "" and store.read_state()["chat"]["session"] == "s2"


def test_failure_is_reported_not_raised(tmp_path):
    store, turn = _turn(tmp_path, FakeAgent(AgentResult("", "", error="boom")))
    assert turn.run(["x"]).startswith("⚠️ chat agent failed: boom")
    assert store.read_state()["chat"]["session"] == ""


def test_language_hint_follows_the_latest_user_line():
    from mentor.usecases.chat_turn import language_hint
    assert language_hint(["[1] you: Привіт", "[2] you: add a task"]) == "\n(Reply in English.)"
    assert language_hint(["[1] you: додай задачу"]) == "\n(Reply in Ukrainian. Never Russian.)"
    assert "Never Russian" in language_hint(["[job 1 finished] x"])
