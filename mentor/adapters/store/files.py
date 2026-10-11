"""FileStore: JSON/Markdown persistence under DATA_DIR. Cross-process safe through the data lock."""

import json
import os
import shutil
from datetime import date, datetime
from pathlib import Path

from mentor.adapters.store.lock import locked
from mentor.domain.project import Project
from mentor.domain.tasks import Agenda


class FileStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        for sub in ("history", "projects", "days", "jobs"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)

    # settings and state
    def read_settings(self) -> dict:
        return self._read_json("settings.json", {})

    def read_state(self) -> dict:
        return self._read_json("state.json", {})

    def update_state(self, **changes) -> dict:
        with locked(self.data_dir):
            state = {**self.read_state(), **changes}
            self._write_json("state.json", state)
        return state

    # agenda
    def agenda(self) -> Agenda:
        return Agenda.from_dict(self._read_json("tasks.json", {}))

    def change_agenda(self, op: str, args: dict, by: str, apply):
        """Run `apply(agenda)` under the lock, save, log the event; returns what apply returned."""
        with locked(self.data_dir):
            agenda = self.agenda()
            result = apply(agenda)
            self._write_json("tasks.json", agenda.to_dict())
            event = {"at": datetime.now().isoformat(timespec="seconds"), "op": op, "args": args, "by": by}
            with open(self.data_dir / "events.jsonl", "a") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return result

    def events_since(self, since: str) -> list[dict]:
        path = self.data_dir / "events.jsonl"
        if not path.exists():
            return []
        events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        return [e for e in events if e["at"] >= since]

    # conversation memory
    def append_history(self, text: str, day: date | None = None) -> None:
        with locked(self.data_dir), open(self.history_path(day or date.today()), "a") as f:
            f.write(text + "\n")

    def history_path(self, day: date) -> Path:
        return self.data_dir / "history" / f"{day.isoformat()}.md"

    def read_history(self, day: date) -> str:
        return _read(self.history_path(day))

    def list_history_days(self) -> list[date]:
        return sorted(date.fromisoformat(p.stem) for p in (self.data_dir / "history").glob("????-??-??.md"))

    def read_context(self) -> str:
        return _read(self.data_dir / "context.md")

    def write_context(self, text: str) -> None:
        self._atomic_write(self.data_dir / "context.md", text)

    def read_day(self, day: date) -> str:
        return _read(self.data_dir / "days" / f"{day.isoformat()}.md")

    def write_day(self, day: date, text: str) -> None:
        self._atomic_write(self.data_dir / "days" / f"{day.isoformat()}.md", text)

    # projects
    def projects(self) -> list[Project]:
        base = self.data_dir / "projects"
        return [Project(name=p.name, path=str(p), repo_path=_read_repo_path(p))
                for p in sorted(base.iterdir()) if p.is_dir() and p.name != "_template"]

    def add_project(self, name: str, repo_path: str) -> None:
        dest = self.data_dir / "projects" / name
        shutil.copytree(self.data_dir / "projects" / "_template", dest)
        project_md = dest / "project.md"
        project_md.write_text(project_md.read_text().replace("<name>", name).replace("<path>", repo_path))

    # helpers
    def _read_json(self, name: str, default):
        path = self.data_dir / name
        return json.loads(path.read_text()) if path.exists() else default

    def _write_json(self, name: str, data) -> None:
        self._atomic_write(self.data_dir / name, json.dumps(data, indent=2, ensure_ascii=False))

    def _atomic_write(self, path: Path, text: str) -> None:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, path)


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _read_repo_path(project_dir: Path) -> str:
    project_md = project_dir / "project.md"
    for line in _read(project_md).splitlines():
        if line.startswith("repo:"):
            return line.removeprefix("repo:").strip()
    return ""
