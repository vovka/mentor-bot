"""Gateway: Telegram messages feed one queue; one worker runs chat turns in order.

Whatever arrives while a turn runs is batched into the next turn, so the agent session never runs twice at once.
Job reports are already shown in the job's own message: they reach the agent with the next turn, without one of their own.
"""

import queue
import sys
import threading
import time
from datetime import datetime

from mentor.usecases import job_progress

_TYPING_EVERY = 4  # seconds; Telegram drops the indicator after ~5
_SETTLE = 0.7  # seconds to wait for the rest of a burst of messages before answering


class Gateway:
    def __init__(self, store, chat, turn, announce, book):
        self.store, self.chat, self.turn, self.announce, self.book = store, chat, turn, announce, book
        self.inbox: queue.Queue = queue.Queue()
        self.reports: queue.Queue = queue.Queue()

    def on_update(self, update) -> None:
        if not update.text:
            return
        self._receive(f"you: {update.text}", update.message_id)
        try:
            self.chat.react(update.message_id, "👀")
        except Exception:  # only an indicator
            pass

    def check_jobs(self) -> None:
        for line in self.announce():
            line = _stamp(line)
            self.store.append_history(line)
            self.reports.put(line)

    def work(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                batch = [self.inbox.get(timeout=1)]
            except queue.Empty:
                continue
            stop.wait(_SETTLE)
            while not self.inbox.empty():
                batch.append(self.inbox.get_nowait())
            try:
                self.answer(batch)
            except Exception as exc:  # the worker must outlive any single failed turn
                print(f"chat turn error: {exc}", file=sys.stderr)

    def answer(self, batch: list[tuple[str, int | None]]) -> None:
        known = {job["id"] for job in self.book.all()}
        reports = []
        while not self.reports.empty():
            reports.append(self.reports.get_nowait())
        reply = self._with_typing(lambda: self.turn.run(reports + [line for line, _ in batch])) or "(no reply)"
        message_ids = [m for _, m in batch if m]
        self.store.append_history(_stamp(f"mentor: {reply}"))
        sent = _retry(lambda: self.chat.send(reply, reply_to=message_ids[-1] if message_ids else None))
        started = [job for job in self.book.all() if job["id"] not in known]
        if started:  # the reply ("job 7 started") becomes the job's live status message
            job_progress.attach(self.book, self.chat, started, reply, sent)
        for message_id in message_ids:
            _retry(lambda: self.chat.react(message_id, None))

    def _receive(self, text: str, message_id: int | None) -> None:
        line = _stamp(text)
        self.store.append_history(line)
        self.inbox.put((line, message_id))

    def _with_typing(self, fn):
        done = threading.Event()

        def keep_typing():
            while not done.is_set():
                self.chat.typing()
                done.wait(_TYPING_EVERY)

        threading.Thread(target=keep_typing, daemon=True).start()
        try:
            return fn()
        except Exception as exc:  # the chat must answer something even when the agent adapter crashes
            return f"⚠️ chat turn crashed: {exc}"
        finally:
            done.set()


def _retry(call, attempts: int = 3, pause: float = 3):
    """Telegram calls fail now and then on a flaky network (TLS handshake timeouts): try again before giving up."""
    for attempt in range(attempts):
        try:
            return call()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(pause)


def _stamp(text: str) -> str:
    return f"[{datetime.now():%H:%M}] {text}"
