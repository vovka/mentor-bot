import json
import subprocess

from mentor.adapters.brain.codex_cli import CodexBrain
from mentor.domain.actions import BrainTask
from mentor.domain.settings import BrainSettings

_SETTINGS = BrainSettings(provider="codex", model="gpt-5.5", effort="low")


def test_run_parses_structured_output(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        out_path = cmd[cmd.index("-o") + 1]
        with open(out_path, "w") as f:
            json.dump(
                {"reply": "hi", "document": None, "actions": [{"kind": "scout", "args": {}}]}, f
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    brain = CodexBrain("prompts/output_schema.json")
    task = BrainTask(prompt="hello", cwd=str(tmp_path), write=False, settings=_SETTINGS)
    result = brain.run(task)

    assert result.reply == "hi"
    assert result.actions[0].kind == "scout"
    cmd = captured["cmd"]
    assert "--ignore-user-config" in cmd
    assert "-s" in cmd and "read-only" in cmd
    assert "--output-schema" in cmd
    assert cmd[-2:] == ["--", "hello"]


def test_run_falls_back_on_non_json_output(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="not json", stderr="oops")

    monkeypatch.setattr(subprocess, "run", fake_run)

    brain = CodexBrain("prompts/output_schema.json")
    task = BrainTask(prompt="hello", cwd=str(tmp_path), write=False, settings=_SETTINGS)
    result = brain.run(task)

    assert result.reply == "not json"
    assert result.actions == []
    assert result.raw == {"stderr": "oops"}


def _capture(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(cmd=cmd, kwargs=kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="x", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


def test_write_mode_cmd(tmp_path, monkeypatch):
    captured = _capture(monkeypatch)
    task = BrainTask("p", str(tmp_path), True, _SETTINGS, extra_dirs=("/a", "/b"))
    CodexBrain("prompts/output_schema.json").run(task)

    cmd = captured["cmd"]
    assert cmd[cmd.index("-s") + 1] == "workspace-write"
    assert "sandbox_workspace_write.network_access=true" in cmd
    assert "web_search=live" in cmd
    assert [cmd[i + 1] for i, a in enumerate(cmd) if a == "--add-dir"] == ["/a", "/b"]
    assert "timeout" not in captured["kwargs"]


def test_read_only_cmd_has_no_write_flags(tmp_path, monkeypatch):
    captured = _capture(monkeypatch)
    CodexBrain("prompts/output_schema.json").run(
        BrainTask("p", str(tmp_path), False, _SETTINGS, extra_dirs=("/a",))
    )
    assert "--add-dir" not in captured["cmd"]
    assert "timeout" not in captured["kwargs"]


def test_write_mode_attaches_browser_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_CDP_URL", "http://127.0.0.1:9223")
    captured = _capture(monkeypatch)
    CodexBrain("prompts/output_schema.json").run(BrainTask("p", str(tmp_path), True, _SETTINGS))
    cmd = captured["cmd"]
    assert any(a.startswith("mcp_servers.browser.command=") for a in cmd)
    args = next(a for a in cmd if a.startswith("mcp_servers.browser.args="))
    assert '"--cdp-endpoint", "http://127.0.0.1:9223"' in args and "@playwright/mcp@" in args


def test_no_browser_mcp_without_env_or_in_read_mode(tmp_path, monkeypatch):
    captured = _capture(monkeypatch)
    monkeypatch.delenv("BROWSER_CDP_URL", raising=False)
    CodexBrain("prompts/output_schema.json").run(BrainTask("p", str(tmp_path), True, _SETTINGS))
    assert not any("mcp_servers" in a for a in captured["cmd"])
    monkeypatch.setenv("BROWSER_CDP_URL", "http://x")
    CodexBrain("prompts/output_schema.json").run(BrainTask("p", str(tmp_path), False, _SETTINGS))
    assert not any("mcp_servers" in a for a in captured["cmd"])
