"""CodexBrain: runs `codex exec` as a subprocess, parses structured JSON output."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from mentor.adapters.brain import stream
from mentor.domain.actions import Action, BrainResult, BrainTask

_STDIN_THRESHOLD = 100 * 1024  # 100 KB
PLAYWRIGHT_MCP = "@playwright/mcp@0.0.83"


def browser_mcp_command(cdp_url: str) -> tuple[str, list[str]]:
    """npx command + args for the Playwright MCP server attached to a running Chrome."""
    return shutil.which("npx") or "npx", ["-y", PLAYWRIGHT_MCP, "--cdp-endpoint", cdp_url]


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
        try:
            if task.on_step:
                result = stream.run(cmd, stdin_text, lambda e: _report(e, task.on_step))
            else:
                result = subprocess.run(cmd, input=stdin_text, capture_output=True, text=True)
        except stream.Aborted as exc:
            return BrainResult(reply=f"brain error: {exc}", actions=[], raw={})
        return self._parse(out_path, result)

    def _build_cmd(self, task: BrainTask, out_path: Path) -> list[str]:
        sandbox = "workspace-write" if task.write else "read-only"
        cmd = [
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
            *(["--json"] if task.on_step else []),  # JSONL events on stdout; -o still gets the answer
        ]
        return cmd + _write_flags(task) if task.write else cmd

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


def _report(event: dict, on_step) -> None:
    for line in stream.codex_steps(event):
        on_step(line)


def _write_flags(task: BrainTask) -> list[str]:
    flags = ["-c", "sandbox_workspace_write.network_access=true", "-c", "web_search=live"]
    for d in task.extra_dirs:
        flags += ["--add-dir", d]
    if cdp_url := os.environ.get("BROWSER_CDP_URL"):
        command, args = browser_mcp_command(cdp_url)
        flags += ["-c", f"mcp_servers.browser.command={json.dumps(command)}"]
        flags += ["-c", f"mcp_servers.browser.args={json.dumps(args)}"]
        # approval_policy=never would otherwise auto-deny every MCP tool call
        flags += ["-c", 'mcp_servers.browser.default_tools_approval_mode="approve"']
    return flags


def _action(item: dict) -> Action:
    """Strict schemas force every arg key to be present; drop the nulls."""
    args = {k: v for k, v in item.get("args", {}).items() if v is not None}
    return Action(kind=item["kind"], args=args)
