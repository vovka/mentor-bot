"""Live status of background jobs inside the chat reply that started them, edited in place as steps come in.

The gateway links each new job to its reply (`status_msg`, `status_base` in job.json), so a restarted service keeps
editing the same message. Jobs started in one turn share that message.
"""

import sys
import time
from datetime import datetime

from mentor.adapters.store.jobs import FINISHED

_EDIT_EVERY = 10  # seconds between edits of one message: Telegram rate-limits edits, jobs log many steps
_STEPS = 3
_MAX_BASE = 3000  # the reply plus the status must fit one Telegram message (4096)
_ICON = {"queued": "⏳", "running": "⏳", "done": "✅", "failed": "❌", "cancelled": "🛑"}


def attach(book, chat, new_jobs: list[dict], reply: str, reply_id: int) -> None:
    """Make the reply that started `new_jobs` their status message (a separate one if the reply is too long)."""
    base = reply if len(reply) <= _MAX_BASE else ""
    message = reply_id if base else chat.send(", ".join(f"job {j['id']}" for j in new_jobs))
    for job in new_jobs:
        book.update(job["id"], status_msg=message, status_base=base)


class JobProgress:
    def __init__(self, book, chat):
        self.book, self.chat = book, chat
        self.shown: dict[int, tuple[float, str]] = {}  # message id -> (monotonic time of last edit, text)

    def refresh(self) -> None:
        groups: dict[int, list[dict]] = {}
        for job in self.book.all():
            if job.get("status_msg") and not job.get("status_closed"):
                groups.setdefault(job["status_msg"], []).append(job)
        for message, jobs in groups.items():
            try:
                self._show(message, jobs)
            except Exception as exc:  # a status line is only an indicator
                print(f"job status error on message {message}: {exc}", file=sys.stderr)

    def _show(self, message: int, jobs: list[dict]) -> None:
        finished = all(j["status"] in FINISHED for j in jobs)
        text = "\n\n".join([jobs[0]["status_base"], *(self.status(j) for j in jobs)]).strip()
        last_at, last_text = self.shown.get(message, (0.0, ""))
        if text == last_text or (not finished and time.monotonic() - last_at < _EDIT_EVERY):
            return
        self.chat.edit(message, text)
        self.shown[message] = (time.monotonic(), text)
        for job in jobs if finished else ():
            self.book.update(job["id"], status_closed=True)

    def status(self, job: dict) -> str:
        head = f"{_ICON[job['status']]} job {job['id']} {job['status']} · {_elapsed(job)}"
        if job["status"] in FINISHED:
            return head
        log = self.book.dir(job["id"]) / "steps.log"
        steps = log.read_text().splitlines()[-_STEPS:] if log.exists() else []
        # `code`: plain text would turn file names like README.md into links
        return "\n".join([head, *(f"· `{s.replace('`', '')}`" for s in steps)])


def _elapsed(job: dict) -> str:
    end = datetime.fromisoformat(job["finished"]) if job["finished"] else datetime.now()
    seconds = int((end - datetime.fromisoformat(job["created"])).total_seconds())
    return f"{seconds // 60}m {seconds % 60:02d}s"
