"""ClaudeBrain: runs `claude -p` as a subprocess, parses structured JSON output."""

import json
import os
import subprocess
from pathlib import Path

from mentor.domain.actions import Action, BrainResult, BrainTask

_TIMEOUT = 300


class ClaudeBrain:
    def __init__(self, schema_path: str | Path):
        self._schema = Path(schema_path).read_text()

    def run(self, task: BrainTask) -> BrainResult:
        result = subprocess.run(
            self._build_cmd(task),
            input=task.prompt,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            cwd=task.cwd,
            env=os.environ,
        )
        return self._parse(result)

    def _build_cmd(self, task: BrainTask) -> list[str]:
        return [
            "claude",
            "-p",
            "--model",
            task.settings.model,
            "--effort",
            task.settings.effort,
            "--output-format",
            "json",
            "--json-schema",
            self._schema,
            "--allowedTools",
            "Read,Grep",
            "--permission-mode",
            "default",
            "--permission-prompts",
            "none",
            "--add-dir",
            task.cwd,
        ]

    def _parse(self, result: subprocess.CompletedProcess) -> BrainResult:
        try:
            data = json.loads(result.stdout)
            payload = data.get("structured_output")
            if payload is None:
                payload = json.loads(data["result"])
            actions = [_action(a) for a in payload["actions"]]
            return BrainResult(
                reply=payload["reply"],
                actions=actions,
                raw=data,
                document=payload.get("document"),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return BrainResult(
                reply=f"brain error: {result.stderr.strip()[-300:]}",
                actions=[],
                raw={"stderr": result.stderr},
            )


def _action(item: dict) -> Action:
    """Strict schemas force every arg key to be present; drop the nulls."""
    args = {k: v for k, v in item.get("args", {}).items() if v is not None}
    return Action(kind=item["kind"], args=args)
