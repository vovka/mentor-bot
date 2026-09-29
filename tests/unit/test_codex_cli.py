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
