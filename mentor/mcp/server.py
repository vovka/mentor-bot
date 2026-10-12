"""Minimal MCP stdio server: newline-delimited JSON-RPC with initialize, tools/list and tools/call."""

import json
import sys
import traceback

_PROTOCOL = "2025-06-18"


def serve(tools, stdin=sys.stdin, stdout=sys.stdout) -> None:
    by_name = {t.name: t for t in tools}
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in message:  # a notification such as notifications/initialized
            continue
        reply = {"jsonrpc": "2.0", "id": message["id"]}
        reply.update(_handle(by_name, message.get("method"), message.get("params") or {}))
        stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        stdout.flush()


def _handle(tools: dict, method: str, params: dict) -> dict:
    if method == "initialize":
        return {"result": {"protocolVersion": params.get("protocolVersion", _PROTOCOL),
                           "capabilities": {"tools": {}}, "serverInfo": {"name": "mentor", "version": "3"}}}
    if method == "tools/list":
        return {"result": {"tools": [{"name": t.name, "description": t.description, "inputSchema": t.schema}
                                     for t in tools.values()]}}
    if method == "tools/call":
        return {"result": _call(tools, params.get("name"), params.get("arguments") or {})}
    if method == "ping":
        return {"result": {}}
    return {"error": {"code": -32601, "message": f"unknown method {method}"}}


def _call(tools: dict, name: str, args: dict) -> dict:
    tool = tools.get(name)
    if tool is None:
        return _text(f"unknown tool {name}", error=True)
    try:
        return _text(tool.handler(args))
    except (ValueError, KeyError) as exc:  # validation: tell the agent what to fix
        return _text(f"error: {exc}", error=True)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return _text("internal error, see the server log", error=True)


def _text(text: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": error}
