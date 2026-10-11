import json
from datetime import date

from mentor.adapters.agent.agents import Agents
from mentor.adapters.agent.fake import FakeAgent
from mentor.adapters.store.files import FileStore
from mentor.adapters.store.jobs import JobBook
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.agent import AgentResult
from mentor.usecases import migrate, morning

TODAY = date(2026, 10, 12)


def test_morning_writes_memory_posts_and_resets_chat(tmp_path):
    store, book, chat = FileStore(tmp_path), JobBook(tmp_path), FakeChat()
    store.append_history("[18:00] you: finish the CV first", day=date(2026, 10, 11))
    store.change_agenda("task_add", {}, "chat", lambda g: g.add_task("Finish CV"))
    store.update_state(chat={"tier": "chat", "session": "old"})
    answer = {"day_summary": "Talked about CV.", "context": "User is job hunting.", "post": "Morning! 1. CV"}
    agent = FakeAgent(AgentResult("Sure:\n" + json.dumps(answer), "m"))
    post = morning.run(store, book, chat, Agents({"codex": agent}), str(tmp_path), wait=False, today=TODAY)
    request = agent.requests[0]
    assert post == "Morning! 1. CV" and chat.outbox[-1] == "Morning! 1. CV"
    assert request.role == "morning" and "finish the CV first" in request.prompt and "t1 Finish CV" in request.prompt
    assert '"op": "task_add"' in request.prompt
    assert store.read_day(date(2026, 10, 11)) == "Talked about CV." and store.read_context() == "User is job hunting."
    assert store.read_state()["chat"] == {} and "morning post" in store.read_history(TODAY)


def test_migrate_propose_and_apply(tmp_path):
    store, chat = FileStore(tmp_path), FakeChat()
    (tmp_path / "tasks.json").write_text('{"tasks": [{"id": "x", "title": "old", "deps": []}]}')
    answer = {"aims": [{"id": "a7", "title": "Get a job", "why": "income", "target": ""}],
              "tasks": [{"id": "t1", "title": "Send CV", "aim": "a7", "deadline": "2026-10-20", "notes": ""}],
              "dropped": "busywork"}
    agents = Agents({"codex": FakeAgent(AgentResult(json.dumps(answer), "m"))})
    text = migrate.run("propose", store, chat, agents, str(tmp_path))
    assert (tmp_path / "legacy" / "tasks-v2.json").exists() and not (tmp_path / "tasks.json").exists()
    assert "t1 Send CV (aim a1, due 2026-10-20)" in text and chat.documents[0][0] == "proposed-tasks.md"
    assert migrate.run("apply", store, chat, agents, str(tmp_path)) == "installed 1 aims and 1 tasks"
    assert store.agenda().task("t1").aim == "a1"
