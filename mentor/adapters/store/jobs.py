"""JobBook: one folder per background job under DATA_DIR/jobs/<id>/ with job.json as its record."""

import json
import os
from datetime import datetime
from pathlib import Path

from mentor.adapters.store.lock import locked

# queued → running → done | failed | cancelled; `announced` flips once the chat has been told
FINISHED = ("done", "failed", "cancelled")


class JobBook:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.root = self.data_dir / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, title: str, brief: str) -> dict:
        with locked(self.data_dir, ".jobs.lock"):
            job_id = str(max((int(p.name) for p in self.root.iterdir() if p.name.isdigit()), default=0) + 1)
            folder = self.dir(job_id)
            (folder / "out").mkdir(parents=True)
            (folder / "brief.md").write_text(brief)
            job = {"id": job_id, "title": title, "status": "queued", "provider": "", "pid": 0,
                   "created": _now(), "finished": "", "announced": False}
            self._write(job)
        return job

    def dir(self, job_id: str) -> Path:
        return self.root / str(job_id)

    def read(self, job_id: str) -> dict:
        path = self.dir(job_id) / "job.json"
        if not path.exists():
            raise ValueError(f"no job {job_id!r}")
        return json.loads(path.read_text())

    def update(self, job_id: str, **changes) -> dict:
        with locked(self.data_dir, ".jobs.lock"):
            job = {**self.read(job_id), **changes}
            if changes.get("status") in FINISHED and not job["finished"]:
                job["finished"] = _now()
            self._write(job)
        return job

    def all(self) -> list[dict]:
        ids = sorted((int(p.name) for p in self.root.iterdir() if (p / "job.json").exists()))
        return [self.read(str(i)) for i in ids]

    def result(self, job_id: str) -> dict:
        path = self.dir(job_id) / "result.json"
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, job: dict) -> None:
        path = self.dir(job["id"]) / "job.json"
        tmp = path.with_name("job.json.tmp")
        tmp.write_text(json.dumps(job, indent=2, ensure_ascii=False))
        os.replace(tmp, path)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
