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
