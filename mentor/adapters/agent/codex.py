"""CodexAgent: one turn of `codex exec` (or `codex exec resume`), JSONL events on stdout."""

import json

from mentor.adapters.agent import stream
from mentor.adapters.agent.mentor_mcp import mentor_server
from mentor.domain.agent import AgentResult, AgentRun

LIMIT_TEXT = "hit your usage limit"  # every Codex usage-limit message contains this (codex-cli 0.153)
_UNSAFE_MCP = ("node_repl",)  # runs arbitrary code outside the sandbox


class CodexAgent:
    def __init__(self, binary: str = "codex"):
        self.binary = binary

    def run(self, request: AgentRun) -> AgentResult:
        events: list[dict] = []

        def on_event(event: dict) -> None:
            events.append(event)
            if request.on_step:
                for line in stream.codex_steps(event):
                    request.on_step(line)

        try:
            done = stream.run(self.command(request), "", on_event, cwd=request.cwd)
        except stream.Aborted as exc:
            return AgentResult("", request.session, error=str(exc))
        return parse(events, done.stderr, request.session)

    def command(self, r: AgentRun) -> list[str]:
        head = [self.binary, "exec"] + (["resume", r.session] if r.session else [])
        flags = ["--json", "--skip-git-repo-check", "-m", r.tier.model,
                 "-c", f"model_reasoning_effort={json.dumps(r.tier.effort)}", "-c", 'approval_policy="never"',
                 "-c", "web_search=\"live\"", *_mcp_flags(r.role)]
        if r.user_tools:
            flags += [part for name in _UNSAFE_MCP for part in ("-c", f"mcp_servers.{name}.enabled=false")]
        else:
            flags.append("--ignore-user-config")  # chat: no user MCPs/plugins, ~4 s per turn instead of ~17 s
        flags += _sandbox_flags(r)
        return head + flags + ["--", r.prompt]


def parse(events: list[dict], stderr: str, session: str) -> AgentResult:
    text, failed, errors, completed = "", "", [], False
    for event in events:
        kind = event.get("type")
        if kind == "thread.started":
            session = event.get("thread_id", session)
        elif kind == "item.completed" and event["item"].get("type") == "agent_message":
            text = event["item"].get("text", "")
        elif kind == "turn.failed":
            failed = (event.get("error") or {}).get("message", "turn failed")
        elif kind == "error":  # also emitted for retried hiccups; fatal only without turn.completed
            errors.append(event.get("message", "error"))
        elif kind == "turn.completed":
            completed = True
    error = failed or ("" if completed else (errors[-1] if errors else
                                             f"codex exited without finishing: {stderr.strip()[-300:]}"))
    return AgentResult(text, session, error=error, limited=LIMIT_TEXT in " ".join([failed, *errors]))


def _mcp_flags(role: str) -> list[str]:
    command, args, cwd, env = mentor_server(role)
    prefix = "mcp_servers.mentor."
    flags = [f"{prefix}command={json.dumps(command)}", f"{prefix}args={json.dumps(args)}",
             f"{prefix}cwd={json.dumps(cwd)}", f'{prefix}default_tools_approval_mode="approve"',
             f"{prefix}env={_toml_table(env)}", f"{prefix}tool_timeout_sec=120"]
    return [part for flag in flags for part in ("-c", flag)]


def _sandbox_flags(r: AgentRun) -> list[str]:
    if not r.sandbox.writable:
        return ["-c", 'sandbox_mode="read-only"']
    paths = {":root": "read", ":tmpdir": "write", **{p: "write" for p in r.sandbox.writable},
             **{p: "deny" for p in r.sandbox.deny_read}}
    return ["-c", f"permissions.mentor.filesystem={_toml_table(paths)}", "-c", 'default_permissions="mentor"',
            "-c", "sandbox_workspace_write.network_access=true"]


def _toml_table(mapping: dict) -> str:
    return "{" + ", ".join(f"{json.dumps(k)}={json.dumps(v)}" for k, v in mapping.items()) + "}"
