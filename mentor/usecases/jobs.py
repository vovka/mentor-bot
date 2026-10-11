"""Read and cancel background jobs (the chat agent's job_list / job_status / job_cancel tools)."""

import os
import signal
from pathlib import Path

_RECENT = 15


def listing(book) -> str:
    jobs = book.all()[-_RECENT:]
    if not jobs:
        return "(no jobs yet)"
    return "\n".join(f"- job {j['id']} [{j['status']}] {j['title']} (started {j['created']})" for j in jobs)


def describe(book, job_id: str) -> str:
    job = book.read(job_id)
    result = book.result(job_id)
    lines = [f"job {job_id} [{job['status']}] {job['title']}", f"started {job['created']}"
             + (f", finished {job['finished']}" if job["finished"] else "")
             + (f", on {job['provider']}" if job["provider"] else "")]
    if result:
        lines.append(summary(result))
    elif job["status"] == "running":
        lines.append("recent steps:\n" + _tail(book.dir(job_id) / "steps.log"))
    return "\n".join(lines)


def summary(result: dict) -> str:
    parts = [result.get("summary", "")]
    for key, label in (("assumptions", "Assumptions"), ("your_move", "Your move"), ("artifacts", "Files")):
        if result.get(key):
            items = [f"`{x}`" if key == "artifacts" else x for x in result[key]]  # file names: no auto-links
            parts.append(f"{label}:\n" + "\n".join(f"- {x}" for x in items))
    return "\n\n".join(p for p in parts if p)


def cancel(book, job_id: str) -> str:
    job = book.read(job_id)
    if job["status"] not in ("queued", "running"):
        return f"job {job_id} is already {job['status']}"
    book.update(job_id, status="cancelled")
    if job["pid"] and _is_job_runner(job["pid"]):
        try:
            os.killpg(job["pid"], signal.SIGTERM)  # the runner leads its own session: agent and tools die too
        except ProcessLookupError:
            pass
    return f"job {job_id} cancelled"


def _is_job_runner(pid: int) -> bool:
    try:
        return b"job-run" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False


def _tail(path: Path, lines: int = 8) -> str:
    return "\n".join(path.read_text().splitlines()[-lines:]) if path.exists() else "(none yet)"


def start(book, title: str, brief: str) -> str:
    """Queue a job; the gateway launches queued jobs within seconds (and after a restart)."""
    job = book.create(title, brief)
    return f"job {job['id']} started: {title}"


def launch_queued(book, spawn) -> None:
    for job in book.all():
        if job["status"] == "queued" and not job["pid"]:
            book.update(job["id"], pid=spawn(job["id"]))


def reap_dead(book) -> None:
    """A running job whose runner vanished (reboot, kill -9) would stay `running` forever: fail it."""
    for job in book.all():
        if job["status"] == "running" and not _is_job_runner(job["pid"]):
            book.update(job["id"], status="failed")
            if not book.result(job["id"]):
                (book.dir(job["id"]) / "result.json").write_text(
                    '{"status": "failed", "summary": "The job process stopped unexpectedly (machine restart?)."}')
