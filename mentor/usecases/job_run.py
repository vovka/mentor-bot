"""Run one background job to the end: orchestrator agent in a sandbox, Claude on a Codex usage limit."""

import json
import os
from pathlib import Path

from mentor.domain.agent import AgentRun, Sandbox
from mentor.domain.settings import tier

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "job.md"
WRITABLE = ("~/dev", "~/Документи", "~/Downloads")


def run(job_id: str, store, book, agents, deny_read: list[str]) -> dict:
    if book.read(job_id)["status"] != "queued":  # cancelled before it started, or already run
        return book.read(job_id)
    job = book.update(job_id, status="running", pid=os.getpid())
    folder = book.dir(job_id).resolve()
    roots = tuple(str(Path(p).expanduser()) for p in WRITABLE if Path(p).expanduser().is_dir()) + (str(folder),)
    sandbox = Sandbox(writable=roots, deny_read=tuple(deny_read))
    settings = store.read_settings()
    result = None
    for name in ("job", "job_fallback"):
        book.update(job_id, provider=f"{tier(settings, name).provider}/{tier(settings, name).model}")
        result = agents.run(AgentRun(prompt(store, job, folder), tier(settings, name), str(folder), role="job",
                                     sandbox=sandbox, user_tools=True, on_step=_logger(folder)))
        if not result.limited:
            break
    if book.read(job_id)["status"] == "cancelled":
        return book.read(job_id)
    return book.update(job_id, status=_finish(book, job_id, result))


def prompt(store, job: dict, folder: Path) -> str:
    projects = "\n".join(f"- {p.name}: {p.repo_path or '(no repo)'}" for p in store.projects()) or "(none)"
    text = PROMPT.read_text().replace("{JOB_DIR}", str(folder)).replace("<JOB_ID>", job["id"])
    brief = (folder / "brief.md").read_text()
    return f"{text}\n\n## Job {job['id']}: {job['title']}\n{brief}\n\n## Known projects\n{projects}"


def _finish(book, job_id: str, result) -> str:
    """The agent's result.json wins; without one, its last message (or the error) becomes the report."""
    report = book.result(job_id)
    if report.get("status") in ("done", "failed"):
        return report["status"]
    status = "done" if result.ok and result.text else "failed"
    fallback = {"status": status, "summary": result.text or f"The agent stopped: {result.error[:500]}",
                "assumptions": [], "artifacts": [], "your_move": []}
    (book.dir(job_id) / "result.json").write_text(json.dumps(fallback, ensure_ascii=False, indent=2))
    return status


def _logger(folder: Path):
    def log(line: str) -> None:
        with open(folder / "steps.log", "a") as f:
            f.write(line + "\n")
    return log
