"""Turn finished jobs into chat lines (once each) and post their result files."""

from pathlib import Path

from mentor.usecases.jobs import summary

_MAX_UPLOAD = 50 * 1024 * 1024  # Telegram bot API limit


def pending(book, chat, file_roots: list[Path]) -> list[str]:
    """Lines for every finished, unannounced job; marks them announced and sends their artifacts."""
    lines = []
    for job in book.all():
        if job["status"] not in ("done", "failed", "cancelled") or job["announced"]:
            continue
        result = book.result(job["id"])
        roots = [book.dir(job["id"]).resolve(), *file_roots]
        reply_to = job.get("status_msg")
        sent = [name for name in result.get("artifacts", [])
                if send_file(chat, name, book.dir(job["id"]), roots, reply_to)]
        body = summary(result) or "(no report written)"
        head = f"[job {job['id']} {_verb(job['status'])}] {job['title']}"
        lines.append(f"{head}\n{body}" + (f"\n(sent to chat: {', '.join(sent)})" if sent else ""))
        book.update(job["id"], announced=True)
    return lines


def send_file(chat, name: str, job_dir: Path, roots: list[Path], reply_to: int | None = None) -> bool:
    path = (job_dir / Path(name).expanduser()).resolve()
    root = next((r for r in roots if path.is_relative_to(r)), None)
    if root is None or not path.is_file() or any(p.startswith(".") for p in path.relative_to(root).parts):
        return False  # outside the allowed roots, missing, or a dotfile such as .env or .git/*
    if path.stat().st_size > _MAX_UPLOAD:
        return False
    chat.send_document(path.read_bytes(), path.name, reply_to=reply_to)
    return True


def _verb(status: str) -> str:
    return {"done": "finished", "failed": "failed", "cancelled": "cancelled"}[status]
