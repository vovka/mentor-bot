"""Aims and tasks: the user's agenda. Pure data and validated operations, no I/O."""

from dataclasses import asdict, dataclass, field, fields
from datetime import date

STATUSES = ("active", "paused", "disabled", "done", "removed")
AIM_STATUSES = ("active", "paused", "done")


@dataclass
class Aim:
    id: str
    title: str
    why: str = ""
    target: str = ""  # ISO date or empty
    status: str = "active"


@dataclass
class Task:
    id: str
    title: str
    aim: str = ""
    status: str = "active"
    deadline: str = ""  # ISO date or empty
    notes: str = ""
    priority: int | None = None  # 1 = top; set by reorder only


@dataclass
class Agenda:
    aims: list[Aim] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "Agenda":
        return cls([Aim(**_known(Aim, a)) for a in raw.get("aims", [])],
                   [Task(**_known(Task, t)) for t in raw.get("tasks", [])])

    def to_dict(self) -> dict:
        return {"aims": [asdict(a) for a in self.aims], "tasks": [asdict(t) for t in self.tasks]}

    def task(self, task_id: str) -> Task:
        return _find(self.tasks, task_id, "task")

    def aim(self, aim_id: str) -> Aim:
        return _find(self.aims, aim_id, "aim")

    def add_task(self, title: str, aim: str = "", deadline: str = "", notes: str = "") -> Task:
        task = Task(_next_id(self.tasks, "t"), _title(title), notes=notes)
        self._set_task(task, aim=aim, deadline=deadline)
        self.tasks.append(task)
        return task

    def update_task(self, task_id: str, **changes) -> Task:
        task = self.task(task_id)
        self._set_task(task, **changes)
        return task

    def add_aim(self, title: str, why: str = "", target: str = "") -> Aim:
        aim = Aim(_next_id(self.aims, "a"), _title(title), why, _date(target))
        self.aims.append(aim)
        return aim

    def update_aim(self, aim_id: str, **changes) -> Aim:
        aim = self.aim(aim_id)
        for key, value in changes.items():
            if key == "status" and value not in AIM_STATUSES:
                raise ValueError(f"aim status must be one of {AIM_STATUSES}")
            if key not in ("title", "why", "target", "status"):
                raise ValueError(f"unknown aim field {key!r}")
            setattr(aim, key, _date(value) if key == "target" else _title(value) if key == "title" else value)
        return aim

    def reorder(self, ids: list[str]) -> None:
        """`ids` top first; every other task loses its rank."""
        ranked = [self.task(i) for i in ids]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate task ids in order")
        for task in self.tasks:
            task.priority = None
        for rank, task in enumerate(ranked, 1):
            task.priority = rank

    def open_tasks(self) -> list[Task]:
        """Active and paused tasks, ranked first."""
        live = [t for t in self.tasks if t.status in ("active", "paused")]
        return sorted(live, key=lambda t: (t.priority is None, t.priority or 0, _num(t.id)))

    def _set_task(self, task: Task, **changes) -> None:
        for key, value in changes.items():
            if key not in ("title", "aim", "status", "deadline", "notes"):
                raise ValueError(f"unknown task field {key!r}")
            if key == "aim" and value:
                self.aim(value)
            if key == "status" and value not in STATUSES:
                raise ValueError(f"status must be one of {STATUSES}")
            setattr(task, key, _date(value) if key == "deadline" else _title(value) if key == "title" else value)


def render(agenda: Agenda) -> str:
    """Compact Markdown for prompts and chat."""
    lines = ["Aims:"] + [f"- {a.id} [{a.status}] {a.title}" + (f" (target {a.target})" if a.target else "")
                         + (f" — {a.why}" if a.why else "") for a in agenda.aims]
    lines.append("Open tasks (priority order):")
    for t in agenda.open_tasks():
        extras = [x for x in (t.status if t.status != "active" else "", t.aim and f"aim {t.aim}",
                              t.deadline and f"due {t.deadline}") if x]
        rank = f"#{t.priority} " if t.priority else ""
        lines.append(f"- {rank}{t.id} {t.title}" + (f" ({', '.join(extras)})" if extras else ""))
    return "\n".join(lines)


def _find(items, item_id: str, kind: str):
    for item in items:
        if item.id == item_id:
            return item
    raise ValueError(f"no {kind} {item_id!r}")


def _next_id(items, prefix: str) -> str:
    return f"{prefix}{max((_num(i.id) for i in items), default=0) + 1}"


def _num(item_id: str) -> int:
    digits = item_id[1:]
    return int(digits) if digits.isdigit() else 0


def _title(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("title must not be empty")
    return value


def _date(value: str) -> str:
    if value:
        date.fromisoformat(value)  # raises ValueError on a bad date
    return value or ""


def _known(cls, raw: dict) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in raw.items() if k in names}
