"""Brain streaming: event → line parsers on real CLI samples, and both adapters over a fake CLI script."""

import json
import os
import threading
from pathlib import Path

from mentor.adapters.brain import stream
from mentor.adapters.brain.claude_cli import ClaudeBrain
from mentor.adapters.brain.codex_cli import CodexBrain
from mentor.domain.actions import BrainTask
from mentor.domain.settings import BrainSettings

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _events(name):
    events = []
    for line in (_FIXTURES / name).read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def test_codex_events_to_lines():
    lines = [line for e in _events("codex_events.jsonl") for line in stream.codex_steps(e)]
    assert lines == ["edited a.txt", "ran `ls`"]
    assert stream.codex_steps({"type": "item.completed", "item": {"type": "web_search", "query": "x"}}) == ["searched: x"]
    mcp = {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "browser", "tool": "browser_navigate"}}
    assert stream.codex_steps(mcp) == ["browser: browser_navigate"]


def test_claude_events_to_lines():
    lines = [line for e in _events("claude_events.jsonl") for line in stream.claude_steps(e)]
    assert lines == ["edited a.txt", "ran `ls`"]
    blocks = [{"type": "tool_use", "name": "mcp__browser__browser_click", "input": {}},
              {"type": "tool_use", "name": "WebFetch", "input": {"url": "https://x.y"}},
              {"type": "tool_use", "name": "Bash", "input": {"command": "x" * 200}}]
    lines = stream.claude_steps({"type": "assistant", "message": {"content": blocks}})
    assert lines[:2] == ["browser: browser_click", "fetched https://x.y"] and len(lines[2]) == 86


def _fake_cli(tmp_path, monkeypatch, name, body):
    script = tmp_path / "bin" / name
    script.parent.mkdir(exist_ok=True)
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{script.parent}{os.pathsep}{os.environ['PATH']}")


def _task(tmp_path, provider, steps):
    settings = BrainSettings(provider=provider, model="m", effort="low")
    return BrainTask("hi", str(tmp_path), True, settings, on_step=steps.append)


def test_codex_streams_steps_and_reads_the_answer_file(tmp_path, monkeypatch):
    answer = '{"reply": "ok", "document": null, "actions": []}'
    body = (f'while [ "$1" != "-o" ]; do shift; done; echo \'{answer}\' > "$2"\n'
            f'echo "$@" | grep -q -- --json || exit 3\ncat {_FIXTURES / "codex_events.jsonl"}')
    _fake_cli(tmp_path, monkeypatch, "codex", body)
    steps = []
    result = CodexBrain("prompts/output_schema.json").run(_task(tmp_path, "codex", steps))
    assert result.reply == "ok" and steps == ["edited a.txt", "ran `ls`"]


def test_claude_streams_steps_and_parses_the_result_event(tmp_path, monkeypatch):
    body = f'echo "$@" | grep -q -- "stream-json --verbose" || exit 3\ncat {_FIXTURES / "claude_events.jsonl"}'
    _fake_cli(tmp_path, monkeypatch, "claude", body)
    steps = []
    result = ClaudeBrain("prompts/output_schema.json").run(_task(tmp_path, "claude", steps))
    assert result.reply == "made a.txt" and result.actions[0].args == {"outcome": "done"}
    assert steps == ["edited a.txt", "ran `ls`"]


def test_stall_kills_the_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "_STALL", 0.5)
    _fake_cli(tmp_path, monkeypatch, "claude", "sleep 30 & sleep 30")
    result = ClaudeBrain("prompts/output_schema.json").run(_task(tmp_path, "claude", []))
    assert result.reply == "brain error: stalled (no output for 60 min)"


def test_output_resets_the_stall_timer(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "_STALL", 1.5)
    body = f'sleep 1\necho x\nsleep 1\ncat {_FIXTURES / "claude_events.jsonl"}'
    _fake_cli(tmp_path, monkeypatch, "claude", body)
    result = ClaudeBrain("prompts/output_schema.json").run(_task(tmp_path, "claude", []))
    assert result.reply == "made a.txt"


def test_cancel_kills_the_running_cli(tmp_path, monkeypatch):
    _fake_cli(tmp_path, monkeypatch, "codex", "sleep 30 & sleep 30")
    threading.Timer(0.5, stream.cancel).start()
    result = CodexBrain("prompts/output_schema.json").run(_task(tmp_path, "codex", []))
    assert result.reply == "brain error: cancelled"


def test_cancel_with_nothing_running_is_a_noop():
    stream.cancel()
