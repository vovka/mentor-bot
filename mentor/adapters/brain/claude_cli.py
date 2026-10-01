"""ClaudeBrain: runs `claude -p` as a subprocess, parses structured JSON output."""

import json
import os
import subprocess
from pathlib import Path

from mentor.adapters.brain import stream
from mentor.adapters.brain.codex_cli import browser_mcp_command
from mentor.domain.actions import Action, BrainResult, BrainTask

_TIMEOUT = 300
_READ = ("Read,Grep", "default")
_WRITE = ("Read,Grep,Glob,Write,Edit,Bash,WebSearch,WebFetch", "acceptEdits")


class ClaudeBrain:
    def __init__(self, schema_path: str | Path):
        self._schema = Path(schema_path).read_text()

    def run(self, task: BrainTask) -> BrainResult:
        timeout = task.timeout or _TIMEOUT
        try:
            if task.on_step:
                result = _stream(self._build_cmd(task), task, timeout)
            else:
                result = subprocess.run(
                    self._build_cmd(task),
                    input=task.prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=task.cwd,
                    env=os.environ,
                )
        except subprocess.TimeoutExpired:
            return BrainResult(reply=f"brain error: timed out after {timeout}s", actions=[], raw={})
        return self._parse(result)

    def _build_cmd(self, task: BrainTask) -> list[str]:
        tools, mode = _WRITE if task.write else _READ
        mcp = _browser_flags() if task.write else []
        if mcp:
            tools += ",mcp__browser"
        return [
            "claude",
            "-p",
            "--model",
            task.settings.model,
            "--effort",
            task.settings.effort,
            "--output-format",
            *(["stream-json", "--verbose"] if task.on_step else ["json"]),
            "--json-schema",
            self._schema,
            "--allowedTools",
            tools,
            "--permission-mode",
            mode,
            "--permission-prompts",
            "none",
            "--add-dir",
            task.cwd,
            *(a for d in task.extra_dirs for a in ("--add-dir", d)),
            *mcp,
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


def _stream(cmd: list[str], task: BrainTask, timeout: int) -> subprocess.CompletedProcess:
    """stream-json: tool calls become steps; the closing `result` event is the json-mode output."""
    final: list[dict] = []

    def on_event(event: dict) -> None:
        if event.get("type") == "result":
            final.append(event)
        for line in stream.claude_steps(event):
            task.on_step(line)

    done = stream.run(cmd, task.prompt, timeout, on_event, cwd=task.cwd, env=os.environ)
    stdout = json.dumps(final[-1]) if final else ""
    return subprocess.CompletedProcess(cmd, done.returncode, stdout, done.stderr)


def _browser_flags() -> list[str]:
    if not (cdp_url := os.environ.get("BROWSER_CDP_URL")):
        return []
    command, args = browser_mcp_command(cdp_url)
    config = {"mcpServers": {"browser": {"command": command, "args": args}}}
    return ["--mcp-config", json.dumps(config), "--strict-mcp-config"]


def _action(item: dict) -> Action:
    """Strict schemas force every arg key to be present; drop the nulls."""
    args = {k: v for k, v in item.get("args", {}).items() if v is not None}
    return Action(kind=item["kind"], args=args)
