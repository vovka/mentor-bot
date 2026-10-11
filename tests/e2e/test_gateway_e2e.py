"""Real TelegramChat against the Bot API stub, real store and job folders, fake agents."""

import threading
import time
from datetime import date

from mentor.adapters.agent.agents import Agents
from mentor.adapters.agent.fake import FakeAgent
from mentor.adapters.render.fake import FakeRenderer
from mentor.adapters.store.files import FileStore
from mentor.adapters.store.jobs import JobBook
from mentor.adapters.telegram.api import TelegramChat
from mentor.app import cli
from mentor.app.container import Container
from mentor.domain.agent import AgentResult
from mentor.usecases import jobs
from tests.e2e.bot_api_stub import BotApiStub


def _wait(predicate, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_message_reply_and_job_report(tmp_path, monkeypatch):
    stub = BotApiStub()
    monkeypatch.setenv("TELEGRAM_API_BASE", stub.base_url)
    store, book = FileStore(tmp_path), JobBook(tmp_path)

    class SlowAgent(FakeAgent):
        def run(self, request):
            time.sleep(0.3)
            return super().run(request)

    codex = SlowAgent(AgentResult("Started job 1.", "s1"), AgentResult("Job 1 is done: 3 options.", "s1"),
                      AgentResult("ok", "s1"), AgentResult("ok", "s1"))
    container = Container(store, book, Agents({"codex": codex}), TelegramChat("t", "1"), FakeRenderer())
    monkeypatch.setattr(cli, "spawn_job", lambda job_id: book.update(job_id, status="done") and 999999)
    stop = threading.Event()
    server = threading.Thread(target=cli.serve, args=(container, stop))
    server.start()
    try:
        stub.enqueue("research X for me")
        assert _wait(lambda: any(m == "sendMessage" and p["text"] == "Started job 1." for m, p in stub.calls))
        jobs.start(book, "Research X", "brief")
        assert _wait(lambda: any(m == "sendMessage" and "3 options" in p["text"] for m, p in stub.calls))
        stub.enqueue("one")
        assert _wait(lambda: len(codex.requests) == 3)
        stub.enqueue("two")
        stub.enqueue("three")
        assert _wait(lambda: len(codex.requests) == 4)
    finally:
        stop.set()
        server.join(timeout=10)
        stub.stop()
    first_reply = next(p for m, p in stub.calls if m == "sendMessage")
    assert first_reply["reply_parameters"]["message_id"] == 1
    assert codex.requests[1].prompt.split("] ", 1)[1].startswith("[job 1 finished] Research X")
    assert "you: two" in codex.requests[3].prompt and "you: three" in codex.requests[3].prompt  # batched
    history = store.read_history(date.today())
    assert "you: research X for me" in history and "mentor: Started job 1." in history
    assert store.read_state()["last_update_id"] == 4 and book.read("1")["announced"]
