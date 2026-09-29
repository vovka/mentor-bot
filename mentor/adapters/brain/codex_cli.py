"""CodexBrain: runs `codex exec` as a subprocess, parses structured JSON output."""

import json
import subprocess
import tempfile
from pathlib import Path

from mentor.domain.actions import Action, BrainResult, BrainTask

_TIMEOUT = 180
_STDIN_THRESHOLD = 100 * 1024  # 100 KB


class CodexBrain:
    def __init__(self, schema_path: str | Path):
        self._schema_path = str(schema_path)

    def run(self, task: BrainTask) -> BrainResult:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            out_path = Path(tmp.name)
        try:
            return self._run(task, out_path)
        finally:
            out_path.unlink(missing_ok=True)

    def _run(self, task: BrainTask, out_path: Path) -> BrainResult:
        cmd = self._build_cmd(task, out_path)
        stdin_text = ""  # codex exec blocks on an open stdin, so always close it
        if len(task.prompt.encode()) > _STDIN_THRESHOLD:
            stdin_text = task.prompt
        else:
            cmd += ["--", task.prompt]
        result = subprocess.run(
            cmd, input=stdin_text, capture_output=True, text=True, timeout=_TIMEOUT
        )
        return self._parse(out_path, result)

    def _build_cmd(self, task: BrainTask, out_path: Path) -> list[str]:
        sandbox = "workspace-write" if task.write else "read-only"
        return [
            "codex",
            "exec",
            "-o",
            str(out_path),
            "-m",
            task.settings.model,
            "-c",
            f"model_reasoning_effort={task.settings.effort}",
            "-s",
            sandbox,
            "-C",
            task.cwd,
            "--skip-git-repo-check",
            "-c",
            "approval_policy=never",
            "--ignore-user-config",  # user config points at a local proxy + MCP servers that hang headless
            "--output-schema",
            self._schema_path,
        ]

    def _parse(self, out_path: Path, result: subprocess.CompletedProcess) -> BrainResult:
        try:
            data = json.loads(out_path.read_text())
            actions = [_action(a) for a in data["actions"]]
            return BrainResult(
                reply=data["reply"], actions=actions, raw=data, document=data.get("document")
            )
        except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
            reply = result.stdout.strip() or f"brain error: {result.stderr.strip()[-300:]}"
            return BrainResult(reply=reply, actions=[], raw={"stderr": result.stderr})


def _action(item: dict) -> Action:
    """Strict schemas force every arg key to be present; drop the nulls."""
    args = {k: v for k, v in item.get("args", {}).items() if v is not None}
    return Action(kind=item["kind"], args=args)
