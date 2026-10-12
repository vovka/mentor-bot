"""Live status of background jobs inside the chat reply that started them, edited in place.

While a job runs, the reply shows its elapsed time and last steps; once done, the steps fold into a collapsed
block and the job's report follows in the same message. The gateway links each new job to its reply
(`status_msg`, `status_base` in job.json), so a restarted service keeps editing the same message.
"""

import html
import re
import sys
import time
from datetime import datetime

from mentor.adapters.store.jobs import FINISHED
from mentor.adapters.telegram.markdown import to_html
from mentor.usecases.jobs import summary

_EDIT_EVERY = 10  # seconds between edits of one message: Telegram rate-limits edits, jobs log many steps
_LIVE_STEPS = 3
_KEPT_STEPS = 30  # in the collapsed block, newest last
_MAX_TEXT = 4096
_ICON = {"queued": "⏳", "running": "⏳", "done": "✅", "failed": "❌", "cancelled": "🛑"}


def attach(book, chat, new_jobs: list[dict], reply: str, reply_id: int) -> None:
    """Make the reply that started `new_jobs` their status message (a separate one if the reply is too long)."""
    base = reply if len(reply) <= _MAX_TEXT // 2 else ""
    message = reply_id if base else chat.send(", ".join(f"job {j['id']}" for j in new_jobs), reply_to=reply_id)
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
        text, overflow = self.render(jobs)
        last_at, last_text = self.shown.get(message, (0.0, ""))
        if text == last_text or (not finished and time.monotonic() - last_at < _EDIT_EVERY):
            return
        try:
            self.chat.edit_html(message, text)
        except Exception:  # Telegram rejected the markup: show it as plain text rather than not at all
            self.chat.edit(message, html.unescape(re.sub(r"<[^>]+>", "", text)))
        self.shown[message] = (time.monotonic(), text)
        if finished:
            for report in overflow:
                self.chat.send(report, reply_to=message)
            for job in jobs:
                self.book.update(job["id"], status_closed=True)

    def render(self, jobs: list[dict]) -> tuple[str, list[str]]:
        """HTML: the reply, then each job. Too long: fewer collapsed steps, then reports as separate replies."""
        reports = [summary(self.book.result(j["id"])) or "(no report written)" for j in jobs]
        for kept, inline in ((_KEPT_STEPS, True), (10, True), (0, True), (0, False)):
            parts = [self._job(j, kept, to_html(r) if inline else "(report below)") for j, r in zip(jobs, reports)]
            text = "\n\n".join([to_html(jobs[0]["status_base"]), *parts]).strip()
            if len(text) <= _MAX_TEXT or not inline:
                break
        finished = [r for j, r in zip(jobs, reports) if j["status"] in FINISHED]
        return text, ([] if inline else finished)

    def _job(self, job: dict, kept: int, report: str) -> str:
        head = html.escape(f"{_ICON[job['status']]} job {job['id']} {job['status']} · {_elapsed(job)}")
        log = self.book.dir(job["id"]) / "steps.log"
        steps = log.read_text().splitlines() if log.exists() else []
        if job["status"] not in FINISHED:
            # <code>: plain text would turn file names like README.md into links
            return "\n".join([head, *(f"· <code>{html.escape(s)}</code>" for s in steps[-_LIVE_STEPS:])])
        folded = steps[-kept:] if kept else []
        block = f"<blockquote expandable>{html.escape(chr(10).join(folded))}</blockquote>" if folded else ""
        return f"{head} · {len(steps)} steps\n{block}\n{report}"


def _elapsed(job: dict) -> str:
    end = datetime.fromisoformat(job["finished"]) if job["finished"] else datetime.now()
    seconds = int((end - datetime.fromisoformat(job["created"])).total_seconds())
    return f"{seconds // 60}m {seconds % 60:02d}s"
