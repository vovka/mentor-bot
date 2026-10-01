"""Run a brain CLI that prints one JSON event per stdout line; map events to short progress lines.

Shapes verified against codex-cli `exec --json` and claude `-p --output-format stream-json --verbose`
(samples in tests/fixtures/). Unknown events map to nothing; a bad line never breaks the run.
"""

import json
import os
import re
import signal
import subprocess
import threading
from pathlib import Path


def run(cmd: list[str], stdin_text: str, timeout: float, on_event, **popen_kw) -> subprocess.CompletedProcess:
    """Like subprocess.run(capture_output, text, timeout) but feeds each stdout event to `on_event`."""
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True, **popen_kw)
    timed_out = threading.Event()
    timer = threading.Timer(timeout, lambda: (timed_out.set(), _kill(proc)))
    timer.start()
    stderr: list[str] = []
    threads = [threading.Thread(target=_write, args=(proc.stdin, stdin_text), daemon=True),
               threading.Thread(target=lambda: stderr.append(proc.stderr.read()), daemon=True)]
    for t in threads:
        t.start()
    for line in proc.stdout:
        try:
            on_event(json.loads(line))
        except Exception:  # a non-JSON line or an unexpected shape: skip it
            pass
    proc.wait()
    timer.cancel()
    threads[1].join()
    if timed_out.is_set():
        raise subprocess.TimeoutExpired(cmd, timeout)
    return subprocess.CompletedProcess(cmd, proc.returncode, "", "".join(stderr))


def _write(pipe, text: str) -> None:
    try:
        pipe.write(text)
        pipe.close()
    except OSError:  # the CLI exited before reading its input
        pass


def _kill(proc) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # the whole group: shell commands keep stdout open otherwise
    except ProcessLookupError:
        pass


def short(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def codex_steps(event: dict) -> list[str]:
    """`{"type":"item.completed","item":{"type":...}}` → lines; everything else → []."""
    if event.get("type") != "item.completed":
        return []
    item = event["item"]
    kind = item.get("type")
    if kind == "command_execution":
        command = re.sub(r"^\S*bash -lc ", "", item.get("command", "")).strip("'\"")
        return [f"ran `{short(command)}`"]
    if kind == "file_change":
        return [f"edited {short(', '.join(Path(c['path']).name for c in item.get('changes', [])))}"]
    if kind == "web_search":
        return [f"searched: {short(item.get('query', ''))}"]
    if kind == "mcp_tool_call":
        return [f"{item.get('server', 'mcp')}: {short(item.get('tool', ''))}"]
    return []


_CLAUDE_TOOLS = {
    "Bash": lambda i: f"ran `{short(i.get('command', ''))}`",
    "Write": lambda i: f"edited {Path(i.get('file_path', '')).name}",
    "Edit": lambda i: f"edited {Path(i.get('file_path', '')).name}",
    "Read": lambda i: f"read {Path(i.get('file_path', '')).name}",
    "Grep": lambda i: f"searched files: {short(i.get('pattern', ''))}",
    "Glob": lambda i: f"searched files: {short(i.get('pattern', ''))}",
    "WebSearch": lambda i: f"searched: {short(i.get('query', ''))}",
    "WebFetch": lambda i: f"fetched {short(i.get('url', ''))}",
}


def claude_steps(event: dict) -> list[str]:
    """tool_use blocks of `{"type":"assistant","message":{"content":[...]}}` → lines."""
    if event.get("type") != "assistant":
        return []
    lines = []
    for block in event["message"].get("content", []):
        if block.get("type") != "tool_use":
            continue
        name, args = block.get("name", ""), block.get("input", {})
        if name.startswith("mcp__browser__"):
            lines.append(f"browser: {name.removeprefix('mcp__browser__')}")
        elif name in _CLAUDE_TOOLS:
            lines.append(_CLAUDE_TOOLS[name](args))
    return lines
