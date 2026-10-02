"""Patch ops from the planner: add / set / move on the current task graph."""

from dataclasses import fields, replace

from mentor.domain import tasks
from mentor.domain.tasks import RUNTIME, Task

_SETTABLE = ("title", "project", "kind", "deps", "due", "note")
_PLANNER_STATUS = ("todo", "done", "dropped")
_BUSY = ("running", "awaiting_approval", "awaiting_user")


def apply_ops(current: list[Task], ops: list) -> tuple[list[Task], list[str]]:
    """Apply `ops` to a copy of `current`. Returns (tasks, skipped lines); ValueError rejects the whole patch."""
    result, skipped = [replace(t, deps=list(t.deps), files=list(t.files)) for t in current], []
    for op in ops:
        if not isinstance(op, dict):
            raise ValueError("every op must be an object")
        line = _OPS.get(op.get("op"), _unknown)(result, op)
        line and skipped.append(line)
    tasks._validate(result)
    return result, skipped


def _unknown(result: list[Task], op: dict) -> str:
    raise ValueError(f"unknown op {op.get('op')!r}")


def _find(result: list[Task], task_id) -> Task | None:
    return next((t for t in result if t.id == task_id), None)


def _position(result: list[Task], after) -> int | None:
    """Insert index after task `after`; None `after` means the very top; unknown id gives None."""
    if after is None:
        return 0
    anchor = _find(result, after)
    return result.index(anchor) + 1 if anchor else None


def _add(result: list[Task], op: dict) -> str | None:
    spec = op.get("task")
    names = {f.name for f in fields(Task)}
    task = tasks._build(spec, names)
    for name in RUNTIME:
        setattr(task, name, getattr(Task("x", "x"), name))
    task.status = task.status if task.status in _PLANNER_STATUS else "todo"
    at = _position(result, op.get("after"))
    if at is None:
        return f"add {task.id}: unknown after {op['after']}"
    result.insert(at, task)
    return None


def _set(result: list[Task], op: dict) -> str | None:
    task = _find(result, op.get("id"))
    if task is None:
        return f"set {op.get('id')}: unknown task"
    for name in _SETTABLE:
        if name in op:
            setattr(task, name, op[name])
    return _set_status(task, op["status"]) if "status" in op else None


def _set_status(task: Task, status) -> str | None:
    if task.status in _BUSY:
        return f"set {task.id}: status kept at {task.status} (wanted {status})"
    if status not in _PLANNER_STATUS:
        return f"set {task.id}: status {status!r} is system-managed"
    task.status = status
    return None


def _move(result: list[Task], op: dict) -> str | None:
    task = _find(result, op.get("id"))
    if task is None:
        return f"move {op.get('id')}: unknown task"
    after = op.get("after")
    if after == task.id or (after is not None and _find(result, after) is None):
        return f"move {task.id}: unknown after {after}"
    result.remove(task)
    result.insert(_position(result, after), task)
    return None


_OPS = {"add": _add, "set": _set, "move": _move}
