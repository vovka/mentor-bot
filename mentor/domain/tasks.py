"""Task graph: pure parsing, validation, merging and rendering."""

import json
from dataclasses import asdict, dataclass, field, fields
from graphlib import CycleError, TopologicalSorter

KINDS = ("research", "writing", "coding", "system", "user")
STATUSES = ("todo", "running", "awaiting_approval", "awaiting_user", "done", "failed", "dropped")
RUNTIME = ("files", "approved", "provider", "proposal")


@dataclass
class Task:
    id: str
    title: str
    project: str = ""
    kind: str = "research"
    deps: list[str] = field(default_factory=list)
    due: str = ""
    status: str = "todo"
    note: str = ""
    files: list[str] = field(default_factory=list)
    approved: bool = False
    provider: str = ""
    proposal: str = ""


def parse(text: str) -> list[Task]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ValueError("missing 'tasks' list")
    names = {f.name for f in fields(Task)}
    tasks = [_build(item, names) for item in data["tasks"]]
    _validate(tasks)
    return tasks


def _build(item: dict, names: set[str]) -> Task:
    if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
        raise ValueError("every task needs a non-empty id and title")
    return Task(**{k: v for k, v in item.items() if k in names})


def _validate(tasks: list[Task]) -> None:
    ids = [t.id for t in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate task id")
    for t in tasks:
        if t.kind not in KINDS or t.status not in STATUSES:
            raise ValueError(f"task {t.id}: unknown kind or status")
        for dep in t.deps:
            if dep not in ids:
                raise ValueError(f"task {t.id}: unknown dep {dep}")
    try:
        tuple(TopologicalSorter({t.id: t.deps for t in tasks}).static_order())
    except CycleError as e:
        raise ValueError("dependency cycle") from e


def dump(tasks: list[Task]) -> str:
    return json.dumps({"tasks": [asdict(t) for t in tasks]}, indent=2, ensure_ascii=False)


def next_ready(tasks: list[Task]) -> Task | None:
    state = {t.id: t.status for t in tasks}
    for t in tasks:
        if t.status == "todo" and all(state[d] in ("done", "dropped") for d in t.deps):
            return t
    return None


def merge(old: list[Task], new: list[Task]) -> list[Task]:
    """Take `new`'s content; keep runtime fields and status from `old`."""
    olds = {t.id: t for t in old}
    for t in new:
        prev = olds.get(t.id)
        if prev is None:
            continue
        for name in RUNTIME:
            setattr(t, name, getattr(prev, name))
        if t.status not in ("done", "dropped"):
            t.status = prev.status
    new_ids = {t.id for t in new}
    flying = [t for t in old if t.status == "running" and t.id not in new_ids]
    return flying + new


def _line(t: Task, tail: str = "") -> str:
    return f"- {t.title}{tail}"


def render(tasks: list[Task]) -> str:
    if not tasks:
        return "No tasks yet."
    nxt = next_ready(tasks)
    by = lambda *s: [t for t in tasks if t.status in s]  # noqa: E731
    todo = [t for t in by("todo") if t is not nxt][:5]
    waiting = [_line(t, f" — {t.note}" if t.note else "") for t in by("awaiting_approval", "awaiting_user")]
    parts = [
        [f"**Next:** {_next(nxt)}"] if nxt else [],
        ["**In progress:**", *map(_line, by("running"))] if by("running") else [],
        ["**Waiting on you:**", *waiting] if waiting else [],
        ["**Failed:**", *map(_line, by("failed"))] if by("failed") else [],
        ["**Then:**", *map(_line, todo)] if todo else [],
    ]
    live = [t for t in tasks if t.status != "dropped"]
    done = f"Done: {len(by('done'))} of {len(live)}"
    return "\n\n".join(["\n".join(p) for p in parts if p] + [done])


def _next(t: Task) -> str:
    return t.title + (f" ({t.project})" if t.project else "") + (f" · due {t.due}" if t.due else "")
