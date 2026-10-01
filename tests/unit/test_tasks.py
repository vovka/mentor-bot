import json

import pytest

from mentor.domain.tasks import Task, dump, merge, next_ready, parse, render


def _text(*tasks):
    return json.dumps({"tasks": list(tasks)})


def test_parse_defaults_and_unknown_keys():
    [t] = parse(_text({"id": "a", "title": "A", "extra": 1}))
    assert t == Task("a", "A")


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "{}",
        _text({"title": "A"}),
        _text({"id": "a", "title": ""}),
        _text({"id": "a", "title": "A"}, {"id": "a", "title": "B"}),
        _text({"id": "a", "title": "A", "kind": "magic"}),
        _text({"id": "a", "title": "A", "status": "bogus"}),
        _text({"id": "a", "title": "A", "deps": ["zz"]}),
        _text({"id": "a", "title": "A", "deps": ["b"]}, {"id": "b", "title": "B", "deps": ["a"]}),
    ],
)
def test_parse_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse(text)


def test_dump_round_trips():
    tasks = [Task("a", "Zażółć"), Task("b", "B", deps=["a"], files=["x"], approved=True)]
    assert parse(dump(tasks)) == tasks


def test_next_ready_respects_deps():
    a, b = Task("a", "A"), Task("b", "B", deps=["a"])
    assert next_ready([b, a]) is a
    a.status = "done"
    assert next_ready([b, a]) is b
    a.status = "dropped"
    assert next_ready([b, a]) is b
    a.status = "running"
    assert next_ready([b, a]) is None


def test_merge_keeps_runtime_and_status():
    old = [Task("a", "Old", status="running", files=["f"], approved=True, provider="p", proposal="x")]
    [m] = merge(old, [Task("a", "New", due="d")])
    assert (m.title, m.due, m.status, m.files, m.approved, m.provider, m.proposal) == (
        "New", "d", "running", ["f"], True, "p", "x")


def test_merge_done_or_dropped_wins():
    old = [Task("a", "A", status="running"), Task("b", "B", status="todo")]
    new = [Task("a", "A", status="done"), Task("b", "B", status="dropped")]
    assert [t.status for t in merge(old, new)] == ["done", "dropped"]


def test_merge_keeps_absent_running_first_and_drops_rest():
    old = [Task("r", "R", status="running"), Task("t", "T"), Task("a", "A")]
    assert [t.id for t in merge(old, [Task("n", "N"), Task("a", "A")])] == ["r", "n", "a"]


def test_render_empty():
    assert render([]) == "No tasks yet."


def test_render_sections():
    tasks = [
        Task("a", "Alpha", project="p", due="Fri"),
        Task("r", "Run", status="running"),
        Task("w", "Wait", status="awaiting_user", note="reply"),
        Task("f", "Fail", status="failed"),
        Task("d", "Done", status="done"),
        Task("x", "Gone", status="dropped"),
        Task("b", "Beta"),
    ]
    assert render(tasks) == (
        "**Next:** Alpha (p) · due Fri\n\n**In progress:**\n- Run\n\n"
        "**Waiting on you:**\n- Wait — reply\n\n**Failed:**\n- Fail\n\n"
        "**Then:**\n- Beta\n\nDone: 1 of 6"
    )
