import io
import json

from mentor.adapters.store.files import FileStore
from mentor.adapters.store.jobs import JobBook
from mentor.mcp import server, tools


def _session(tool_list, *messages):
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    stdout = io.StringIO()
    server.serve(tool_list, stdin, stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def _call(i, name, **args):
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}


def test_chat_role_round_trip(tmp_path):
    store = FileStore(tmp_path)
    book = JobBook(tmp_path)
    chat_tools = tools.build("chat", store, book)
    replies = _session(
        chat_tools,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        _call(3, "task_add", title="Write post", deadline="2026-10-16"),
        _call(4, "task_set_status", id="t1", status="paused"),
        _call(5, "task_add", title="Bad", deadline="Friday"),
        _call(6, "job_start", title="research", brief="do it"),
        _call(7, "tasks_list"),
    )
    assert [r["id"] for r in replies] == [1, 2, 3, 4, 5, 6, 7]
    names = {t["name"] for t in replies[1]["result"]["tools"]}
    assert {"task_add", "job_start", "recall", "send_image"} <= names
    text = [r["result"]["content"][0]["text"] for r in replies[2:]]
    assert text[0] == "added t1 [active] Write post due 2026-10-16"
    assert text[1].startswith("now t1 [paused]")
    assert replies[4]["result"]["isError"] and "Invalid isoformat" in text[2]
    assert text[3] == "job 1 started: research" and book.read("1")["status"] == "queued"
    assert "t1 Write post (paused" in text[4]
    assert [e["op"] for e in store.events_since("2000")] == ["task_add", "task_set_status"]


def test_job_role_is_read_only(tmp_path):
    names = {t.name for t in tools.build("job", FileStore(tmp_path), JobBook(tmp_path))}
    assert names == {"tasks_list", "projects_list"}
