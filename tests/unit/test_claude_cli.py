import json
import subprocess

from mentor.adapters.brain.claude_cli import ClaudeBrain
from mentor.domain.actions import BrainTask
from mentor.domain.settings import BrainSettings

_SETTINGS = BrainSettings(provider="claude", model="sonnet", effort="low")


def _task(tmp_path):
    return BrainTask(prompt="hello", cwd=str(tmp_path), write=False, settings=_SETTINGS)


def test_run_parses_structured_output_and_argv(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        payload = {
            "reply": "hi",
            "document": None,
            "actions": [{"kind": "scout", "args": {"project": "tusk", "reason": None}}],
        }
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"structured_output": payload}), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = ClaudeBrain("prompts/output_schema.json").run(_task(tmp_path))

    cmd = captured["cmd"]
    assert "--json-schema" in cmd
    assert "--allowedTools" in cmd
    assert "--permission-prompts" in cmd
    assert "--bare" not in cmd
    assert captured["kwargs"]["input"] == "hello"
    assert result.reply == "hi"
    assert result.actions[0].kind == "scout"
    assert result.actions[0].args == {"project": "tusk"}  # null args stripped


def test_run_falls_back_to_result_string(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        payload = {"reply": "hi from result", "document": None, "actions": []}
        data = {"result": json.dumps(payload)}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(data), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = ClaudeBrain("prompts/output_schema.json").run(_task(tmp_path))

    assert result.reply == "hi from result"
    assert result.actions == []


def test_run_errors_on_non_json_stdout(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="not json", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = ClaudeBrain("prompts/output_schema.json").run(_task(tmp_path))

    assert result.reply == "brain error: boom"
    assert result.actions == []
    assert result.raw == {"stderr": "boom"}


def _capture(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(cmd=cmd, kwargs=kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="x", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


def _after(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_write_mode_cmd(tmp_path, monkeypatch):
    captured = _capture(monkeypatch)
    task = BrainTask("p", str(tmp_path), True, _SETTINGS, timeout=900, extra_dirs=("/a", "/b"))
    ClaudeBrain("prompts/output_schema.json").run(task)

    cmd = captured["cmd"]
    assert _after(cmd, "--allowedTools") == "Read,Grep,Glob,Write,Edit,Bash,WebSearch,WebFetch"
    assert _after(cmd, "--permission-mode") == "acceptEdits"
    assert _after(cmd, "--permission-prompts") == "none"
    assert [cmd[i + 1] for i, a in enumerate(cmd) if a == "--add-dir"] == [str(tmp_path), "/a", "/b"]
    assert captured["kwargs"]["timeout"] == 900


def test_read_only_cmd_unchanged(tmp_path, monkeypatch):
    captured = _capture(monkeypatch)
    ClaudeBrain("prompts/output_schema.json").run(_task(tmp_path))
    cmd = captured["cmd"]
    assert _after(cmd, "--allowedTools") == "Read,Grep"
    assert _after(cmd, "--permission-mode") == "default"
    assert captured["kwargs"]["timeout"] == 300


def test_timeout_returns_error_result(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr(subprocess, "run", fake_run)
    task = BrainTask("p", str(tmp_path), False, _SETTINGS, timeout=5)
    result = ClaudeBrain("prompts/output_schema.json").run(task)
    assert result.reply == "brain error: timed out after 5s"
    assert result.actions == []


def test_write_mode_attaches_browser_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_CDP_URL", "http://127.0.0.1:9223")
    captured = _capture(monkeypatch)
    ClaudeBrain("prompts/output_schema.json").run(BrainTask("p", str(tmp_path), True, _SETTINGS))
    cmd = captured["cmd"]
    assert _after(cmd, "--allowedTools").endswith(",mcp__browser")
    server = json.loads(_after(cmd, "--mcp-config"))["mcpServers"]["browser"]
    assert server["args"][-2:] == ["--cdp-endpoint", "http://127.0.0.1:9223"]
    assert "--strict-mcp-config" in cmd


def test_no_browser_mcp_without_env_or_in_read_mode(tmp_path, monkeypatch):
    captured = _capture(monkeypatch)
    monkeypatch.delenv("BROWSER_CDP_URL", raising=False)
    ClaudeBrain("prompts/output_schema.json").run(BrainTask("p", str(tmp_path), True, _SETTINGS))
    assert "--mcp-config" not in captured["cmd"]
    monkeypatch.setenv("BROWSER_CDP_URL", "http://x")
    ClaudeBrain("prompts/output_schema.json").run(_task(tmp_path))
    assert "--mcp-config" not in captured["cmd"]
