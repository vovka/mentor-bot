"""ClaudeAgent: one turn of `claude -p` (optionally --resume), stream-json events on stdout. The fallback provider."""

import json
from pathlib import Path

from mentor.adapters.agent import stream
from mentor.adapters.agent.mentor_mcp import mentor_server
from mentor.domain.agent import AgentResult, AgentRun

_JOB_TOOLS = "Bash,Read,Grep,Glob,Write,Edit,WebSearch,WebFetch,Task,Agent,TodoWrite,mcp__mentor"


class ClaudeAgent:
    def __init__(self, binary: str = "claude"):
        self.binary = binary

    def run(self, request: AgentRun) -> AgentResult:
        final: list[dict] = []

        def on_event(event: dict) -> None:
            if event.get("type") == "result":
                final.append(event)
            if request.on_step:
                for line in stream.claude_steps(event):
                    request.on_step(line)

        try:
            done = stream.run(self.command(request), request.prompt, on_event, cwd=request.cwd)
        except stream.Aborted as exc:
            return AgentResult("", request.session, error=str(exc))
        if not final:
            return AgentResult("", request.session, error=f"claude exited without a result: {done.stderr[-300:]}")
        return _parse(final[-1], request.session)

    def command(self, r: AgentRun) -> list[str]:
        command, args, cwd, env = mentor_server(r.role)
        mcp = {"mcpServers": {"mentor": {"command": command, "args": args, "cwd": cwd, "env": env}}}
        cmd = [self.binary, "-p", "--model", r.tier.model, "--effort", r.tier.effort,
               "--output-format", "stream-json", "--verbose", "--mcp-config", json.dumps(mcp)]
        if r.session:
            cmd += ["--resume", r.session]
        if not r.user_tools:
            # user settings (hooks, plugins) break haiku headless: "system.5.type: Input should be 'text'"
            cmd += ["--setting-sources", "", "--strict-mcp-config"]
        if not r.sandbox.writable:
            return cmd + ["--allowedTools", "mcp__mentor", "--permission-mode", "default"]
        return cmd + ["--settings", json.dumps(_sandbox_settings(r)), "--permission-mode", "acceptEdits",
                      "--allowedTools", _JOB_TOOLS, *[a for p in r.sandbox.writable for a in ("--add-dir", p)]]


def _sandbox_settings(r: AgentRun) -> dict:
    """OS sandbox for Bash; Read deny rules become its deny-read list, Edit allow rules its writable roots."""
    return {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True, "allowUnsandboxedCommands": False,
                        "network": {"allowedDomains": ["*"]}},
            "permissions": {"deny": [f"Read(/{_abs(p)}{_tree(p)})" for p in r.sandbox.deny_read],
                            "allow": [f"Edit(/{_abs(p)}/**)" for p in r.sandbox.writable]}}


def _abs(path: str) -> str:
    return str(Path(path).expanduser())


def _tree(path: str) -> str:
    return "/**" if Path(path).expanduser().is_dir() else ""


def _parse(result: dict, session: str) -> AgentResult:
    text = result.get("result") or ""
    session = result.get("session_id") or session
    if result.get("is_error"):
        return AgentResult("", session, error=text or result.get("subtype", "error"), limited="limit" in text.lower())
    return AgentResult(text, session)
