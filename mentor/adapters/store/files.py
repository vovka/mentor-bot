"""FileStore: Markdown/JSON persistence under DATA_DIR."""

import json
import os
import shutil
from datetime import date
from pathlib import Path

from mentor.domain.project import Project
from mentor.domain.settings import BrainSettings
from mentor.domain import tasks as task_graph
from mentor.domain.tasks import Task

DEFAULT_SETTINGS = {
    "provider": "codex",
    "model": "gpt-5.5",
    "effort": "low",
    "heavy": {"provider": "codex", "model": "gpt-6-astra", "effort": "high"},
}


class FileStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        (self.data_dir / "history").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "projects").mkdir(parents=True, exist_ok=True)

    def _plan_path(self, project: str | None) -> Path:
        if project:
            return self.data_dir / "projects" / project / "plan.md"
        return self.data_dir / "plan.md"

    def read_plan(self, project: str | None = None) -> str:
        path = self._plan_path(project)
        return path.read_text() if path.exists() else ""

    def write_plan(self, text: str, project: str | None = None) -> None:
        self._plan_path(project).write_text(text)

    def write_plan_project(self, name: str, text: str) -> None:
        self.write_plan(text, project=name)

    def read_timeline(self, project: str | None = None) -> str:
        base = self.data_dir / "projects" / project if project else self.data_dir
        path = base / "timeline.md"
        return path.read_text() if path.exists() else ""

    def read_settings(self) -> dict:
        path = self.data_dir / "settings.json"
        if not path.exists():
            path.write_text(json.dumps(DEFAULT_SETTINGS, indent=2))
        return json.loads(path.read_text())

    def write_settings(self, settings: BrainSettings) -> None:
        current = self.read_settings()
        current.update(provider=settings.provider, model=settings.model, effort=settings.effort)
        (self.data_dir / "settings.json").write_text(json.dumps(current, indent=2))

    def write_heavy_settings(self, settings: BrainSettings) -> None:
        current = self.read_settings()
        current["heavy"] = {
            "provider": settings.provider,
            "model": settings.model,
            "effort": settings.effort,
        }
        (self.data_dir / "settings.json").write_text(json.dumps(current, indent=2))

    def read_state(self) -> dict:
        path = self.data_dir / "state.json"
        if not path.exists():
            path.write_text("{}")
        return json.loads(path.read_text())

    def write_state(self, state: dict) -> None:
        self._atomic_write(self.data_dir / "state.json", json.dumps(state, indent=2))

    def read_tasks(self) -> list[Task]:
        path = self.data_dir / "tasks.json"
        return task_graph.parse(path.read_text()) if path.exists() else []

    def write_tasks(self, tasks: list[Task]) -> None:
        self._atomic_write(self.data_dir / "tasks.json", task_graph.dump(tasks))

    def _atomic_write(self, path: Path, text: str) -> None:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, path)

    def _history_path(self, day: date) -> Path:
        return self.data_dir / "history" / f"{day.isoformat()}.md"

    def append_history(self, text: str) -> None:
        with open(self._history_path(date.today()), "a") as f:
            f.write(text + "\n")

    def read_history(self, day: date) -> str:
        path = self._history_path(day)
        return path.read_text() if path.exists() else ""

    def list_history_days(self) -> list[date]:
        days = []
        for path in (self.data_dir / "history").glob("*.md"):
            try:
                days.append(date.fromisoformat(path.stem))
            except ValueError:
                continue
        return sorted(days)

    def read_recent_history(self, days: int = 2) -> str:
        recent = self.list_history_days()[-days:]
        return "\n".join(self.read_history(d) for d in recent)

    def read_summary(self) -> str:
        path = self.data_dir / "history" / "summary.md"
        return path.read_text() if path.exists() else ""

    def write_summary(self, text: str) -> None:
        (self.data_dir / "history" / "summary.md").write_text(text)

    def projects(self) -> list[Project]:
        base = self.data_dir / "projects"
        return [
            Project(name=p.name, path=str(p), repo_path=_read_repo_path(p))
            for p in sorted(base.iterdir())
            if p.is_dir() and p.name != "_template"
        ]

    def add_project(self, name: str, repo_path: str) -> None:
        dest = self.data_dir / "projects" / name
        shutil.copytree(self.data_dir / "projects" / "_template", dest)
        project_md = dest / "project.md"
        text = project_md.read_text().replace("<name>", name).replace("<path>", repo_path)
        project_md.write_text(text)


def _read_repo_path(project_dir: Path) -> str:
    for line in (project_dir / "project.md").read_text().splitlines():
        if line.startswith("repo:"):
            return line.removeprefix("repo:").strip()
    return ""
