import json

import pytest

from mentor.domain import tasks
from mentor.domain.task_ops import apply_ops
from mentor.domain.tasks import Task


def _base():
    return [Task("a", "A"), Task("b", "B", status="running"), Task("c", "C", deps=["a"])]


def _ids(result):
    return [t.id for t in result]


def test_add_after_and_top():
    new, skipped = apply_ops(_base(), [
        {"op": "add", "task": {"id": "x", "title": "X", "approved": True, "status": "running"}, "after": "a"},
        {"op": "add", "task": {"id": "y", "title": "Y"}, "after": None},
    ])
    assert _ids(new) == ["y", "a", "x", "b", "c"] and skipped == []
    x = new[2]
    assert x.status == "todo" and x.approved is False


def test_set_fields_and_status_and_input_untouched():
    base = _base()
    new, skipped = apply_ops(base, [{"op": "set", "id": "a", "due": "2026-10-15", "deps": [], "status": "done"}])
    assert new[0].due == "2026-10-15" and new[0].status == "done" and skipped == []
    assert base[0].due == "" and base[0].status == "todo"


def test_set_status_on_running_task_kept_and_reported():
    new, skipped = apply_ops(_base(), [{"op": "set", "id": "b", "status": "dropped", "note": "n"}])
    assert new[1].status == "running" and new[1].note == "n"
    assert skipped == ["set b: status kept at running (wanted dropped)"]


def test_system_status_not_settable():
    new, skipped = apply_ops(_base(), [{"op": "set", "id": "a", "status": "failed"}])
    assert new[0].status == "todo" and "system-managed" in skipped[0]


def test_move():
    new, _ = apply_ops(_base(), [{"op": "move", "id": "c", "after": None}, {"op": "move", "id": "a", "after": "b"}])
    assert _ids(new) == ["c", "b", "a"]


def test_unknown_ids_are_skipped_and_reported():
    new, skipped = apply_ops(_base(), [
        {"op": "set", "id": "zz", "note": "x"}, {"op": "move", "id": "a", "after": "zz"},
        {"op": "move", "id": "zz", "after": None}, {"op": "add", "task": {"id": "n", "title": "N"}, "after": "zz"},
    ])
    assert _ids(new) == ["a", "b", "c"] and len(skipped) == 4


@pytest.mark.parametrize("ops, text", [
    ([{"op": "set", "id": "a", "deps": ["c"]}], "cycle"),
    ([{"op": "set", "id": "a", "deps": ["nope"]}], "unknown dep"),
    ([{"op": "set", "id": "a", "kind": "magic"}], "unknown kind"),
    ([{"op": "add", "task": {"id": "a", "title": "dup"}, "after": None}], "duplicate"),
    ([{"op": "fly"}], "unknown op"),
    ([{"op": "add", "task": {"title": "no id"}, "after": None}], "non-empty id"),
])
def test_invalid_patch_raises(ops, text):
    with pytest.raises(ValueError, match=text):
        apply_ops(_base(), ops)


def test_brief_shape():
    ts = [Task("a", "A", project="p", kind="coding", due="2026-10-01", note="n"), Task("b", "B", deps=["a"]),
          Task("c", "C", status="done"), Task("d", "D", status="dropped")]
    assert tasks.brief(ts) == (
        "a | todo | coding | p | 2026-10-01 | deps= | A — n\n"
        "b | todo | research |  |  | deps=a | B\n"
        "done/dropped: c, d"
    )


@pytest.mark.parametrize("op", [
    {"op": "set", "id": "a", "deps": None},
    {"op": "set", "id": "a", "deps": "b"},
    {"op": "set", "id": "a", "deps": [1]},
    {"op": "set", "id": "a", "title": None},
    {"op": "set", "id": "a", "kind": ["coding"]},
    {"op": "set", "id": "a", "due": 5},
    {"op": "add", "task": {"id": 7, "title": "X"}},
    {"op": "add", "task": {"id": "x", "title": ["X"]}},
    {"op": "add", "task": None},
    {"op": "add", "task": ["x"]},
    {"op": ["add"]},
    "add",
])
def test_malformed_values_raise_value_error(op):
    with pytest.raises(ValueError):
        apply_ops(_base(), [op])


@pytest.mark.parametrize("item", [
    {"id": "a", "title": "A", "deps": None},
    {"id": "a", "title": "A", "status": None},
    {"id": ["a"], "title": "A"},
    {"id": "a", "title": "A", "note": {}},
    "a",
])
def test_parse_rejects_wrong_types(item):
    with pytest.raises(ValueError):
        tasks.parse(json.dumps({"tasks": [item]}))
