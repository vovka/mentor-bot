"""CLI agent adapters: event parsing on real samples, command shapes, and runs over fake CLI scripts."""

import json
from pathlib import Path

from mentor.adapters.agent import stream
from mentor.adapters.agent.agents import Agents
from mentor.adapters.agent.claude import ClaudeAgent
from mentor.adapters.agent.codex import CodexAgent, parse
from mentor.domain.agent import AgentRun, Sandbox
from mentor.domain.settings import Tier

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_LIMIT = {"type": "turn.failed", "error": {"message": "You've hit your usage limit. Try again at 8:05 PM."}}


def _events(name):
    events = []
    for line in (_FIXTURES / name).read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def _run(tmp_path, provider="codex", **kw):
    return AgentRun("hi", Tier(provider, "m", "low"), str(tmp_path), role="chat", **kw)


def _fake_cli(tmp_path, name, body) -> str:
    script = tmp_path / "bin" / name
    script.parent.mkdir(exist_ok=True)
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)
    return str(script)


def test_step_lines_from_real_samples():
    assert [l for e in _events("codex_events.jsonl") for l in stream.codex_steps(e)] == ["edited a.txt", "ran `ls`"]
    assert [l for e in _events("claude_events.jsonl") for l in stream.claude_steps(e)] == ["edited a.txt", "ran `ls`"]


def test_codex_parse_session_text_and_limit():
    ok = parse(_events("codex_events.jsonl"), "", "")
    assert ok.ok and ok.session == "01a0f990-feac-7db1-af92-9cba66614e76" and "Created `a.txt`" in ok.text
    limited = parse([{"type": "thread.started", "thread_id": "s1"}, {"type": "turn.started"}, _LIMIT], "", "")
    assert limited.limited and limited.session == "s1" and not limited.ok
    retried = parse([{"type": "error", "message": "reconnecting"}, {"type": "turn.completed"}], "", "s0")
    assert retried.ok and retried.session == "s0"
    assert "without finishing: boom" in parse([], "boom", "").error


def test_codex_command_chat_vs_job(tmp_path):
    agent = CodexAgent()
    chat = agent.command(_run(tmp_path, session="abc"))
    assert chat[:4] == ["codex", "exec", "resume", "abc"] and "--ignore-user-config" in chat
    assert chat[chat.index("apps") - 1] == "--disable"  # account apps would bury the mentor tools
    assert 'sandbox_mode="read-only"' in chat and chat[-2:] == ["--", "hi"]
    job = agent.command(_run(tmp_path, user_tools=True, sandbox=Sandbox(("/w",), ("/s/.env",))))
    profile = next(c for c in job if c.startswith("permissions.mentor.filesystem="))
    assert '"/w"="write"' in profile and '"/s/.env"="deny"' in profile and "--ignore-user-config" not in job
    assert "mcp_servers.node_repl.enabled=false" in job and 'default_permissions="mentor"' in job


def test_claude_command_chat_vs_job(tmp_path):
    chat = ClaudeAgent().command(_run(tmp_path, "claude", session="s"))
    assert chat[chat.index("--resume") + 1] == "s" and chat[chat.index("--allowedTools") + 1] == "mcp__mentor"
    assert chat[chat.index("--setting-sources") + 1] == ""
    job = ClaudeAgent().command(_run(tmp_path, "claude", user_tools=True, sandbox=Sandbox(("/w",), ("/s/.env",))))
    settings = json.loads(job[job.index("--settings") + 1])
    assert settings["permissions"]["deny"] == ["Read(//s/.env)"] and settings["sandbox"]["enabled"]
    assert "--setting-sources" not in job


def test_codex_run_over_fake_cli(tmp_path):
    body = f'echo "$@" | grep -q -- --json || exit 3\ncat {_FIXTURES / "codex_events.jsonl"}'
    steps = []
    result = CodexAgent(_fake_cli(tmp_path, "codex", body)).run(_run(tmp_path, on_step=steps.append))
    assert result.ok and steps == ["edited a.txt", "ran `ls`"]


def test_claude_run_over_fake_cli(tmp_path):
    body = f'cat > /dev/null\ncat {_FIXTURES / "claude_events.jsonl"}'
    result = ClaudeAgent(_fake_cli(tmp_path, "claude", body)).run(_run(tmp_path, "claude"))
    assert result.ok and result.text.startswith("I don't have access")


def test_stall_kills_the_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "_STALL", 0.5)
    result = CodexAgent(_fake_cli(tmp_path, "codex", "sleep 30 & sleep 30")).run(_run(tmp_path))
    assert result.error.startswith("stalled")


def test_agents_dispatch_by_provider(tmp_path):
    assert "unknown provider" in Agents({}).run(_run(tmp_path)).error
