import json
import os

from mentor.adapters.agent.agents import Agents
from mentor.adapters.agent.fake import FakeAgent
from mentor.adapters.store.files import FileStore
from mentor.adapters.store.jobs import JobBook
from mentor.adapters.telegram.fake import FakeChat
from mentor.domain.agent import AgentResult
from mentor.usecases import job_announce, job_run, jobs
from mentor.usecases import job_progress
from mentor.usecases.job_progress import JobProgress


def _setup(tmp_path, *codex_results, claude=None):
    store, book = FileStore(tmp_path), JobBook(tmp_path)
    agents = Agents({"codex": FakeAgent(*codex_results), "claude": claude or FakeAgent()})
    jobs.start(book, "Research X", "Find three options for X")
    return store, book, agents


def test_job_runs_sandboxed_and_reports_its_last_message(tmp_path):
    store, book, agents = _setup(tmp_path, AgentResult("Found 3 options.", "j1"))
    job = job_run.run("1", store, book, agents, deny_read=["/home/u/.ssh"])
    request = agents.by_provider["codex"].requests[0]
    assert job["status"] == "done" and job["provider"] == "codex/gpt-6-astra"
    assert request.role == "job" and request.user_tools and request.sandbox.deny_read == ("/home/u/.ssh",)
    assert str(book.dir("1").resolve()) in request.sandbox.writable and "Find three options" in request.prompt
    assert book.result("1")["summary"] == "Found 3 options."


def test_usage_limit_reruns_on_claude(tmp_path):
    claude = FakeAgent(AgentResult("done on opus", "c"))
    store, book, agents = _setup(tmp_path, AgentResult("", error="hit your usage limit", limited=True), claude=claude)
    job = job_run.run("1", store, book, agents, deny_read=[])
    assert job["status"] == "done" and job["provider"] == "claude/opus" and claude.requests[0].tier.model == "opus"


def test_agent_written_result_wins_and_files_are_sent(tmp_path):
    store, book, agents = _setup(tmp_path, AgentResult("text", "j"))
    (book.dir("1") / "out" / "report.md").write_text("# report")
    (book.dir("1") / "out" / ".env").write_text("SECRET=1")
    report = {"status": "done", "summary": "Wrote the report.", "assumptions": ["EU only"],
              "artifacts": ["out/report.md", "out/.env", "/etc/passwd"], "your_move": ["read it"]}
    (book.dir("1") / "result.json").write_text(json.dumps(report))
    job_run.run("1", store, book, agents, deny_read=[])
    chat = FakeChat()
    [line] = job_announce.pending(book, chat, [])
    assert line.startswith("[job 1 finished] Research X\nWrote the report.") and "- EU only" in line
    assert [d[0] for d in chat.documents] == ["report.md"] and "(sent to chat: out/report.md)" in line
    assert job_announce.pending(book, chat, []) == []


def test_cancel_keeps_cancelled_and_reaper_fails_orphans(tmp_path):
    store, book, agents = _setup(tmp_path, AgentResult("late", "j"))
    assert jobs.cancel(book, "1") == "job 1 cancelled"
    assert job_run.run("1", store, book, agents, deny_read=[])["status"] == "cancelled"
    jobs.start(book, "two", "b")
    book.update("2", status="running", pid=os.getpid())  # this test process is not a job runner
    jobs.reap_dead(book)
    assert book.read("2")["status"] == "failed" and "unexpectedly" in book.result("2")["summary"]


def test_launch_queued_spawns_once(tmp_path):
    _, book, _ = _setup(tmp_path)
    spawned = []
    jobs.launch_queued(book, lambda job_id: spawned.append(job_id) or 4242)
    jobs.launch_queued(book, lambda job_id: spawned.append(job_id) or 4242)
    assert spawned == ["1"] and book.read("1")["pid"] == 4242


def test_reply_carries_live_status_until_the_job_closes(tmp_path):
    store, book, agents = _setup(tmp_path)
    jobs.start(book, "Other", "brief")
    chat = FakeChat()
    job_progress.attach(book, chat, [book.read("1"), book.read("2")], "Started jobs 1 and 2.", 41)
    progress = JobProgress(book, chat)
    book.update("1", status="running")
    (book.dir("1") / "steps.log").write_text("ran `ls`\nsearched: x\nedited README.md\nran `pytest`\n")
    progress.refresh()
    message, text = chat.edits[-1]
    assert message == 41 and text.startswith("Started jobs 1 and 2.\n\n⏳ job 1 running")
    assert "· `searched: x`\n· `edited README.md`\n· `ran pytest`\n\n⏳ job 2 queued" in text
    progress.refresh()
    assert len(chat.edits) == 1  # unchanged and within the interval: no edit
    book.update("1", status="done")
    book.update("2", status="cancelled")
    progress.refresh()
    assert "✅ job 1 done" in chat.edits[-1][1] and "🛑 job 2 cancelled" in chat.edits[-1][1]
    progress.refresh()
    assert len(chat.edits) == 2 and chat.outbox == [] and book.read("2")["status_closed"]


def test_too_long_reply_gets_a_separate_status_message(tmp_path):
    store, book, agents = _setup(tmp_path)
    chat = FakeChat()
    job_progress.attach(book, chat, [book.read("1")], "x" * 5000, 41)
    assert chat.outbox == ["job 1"] and book.read("1")["status_msg"] == 1 and book.read("1")["status_base"] == ""
