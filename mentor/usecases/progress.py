"""Progress: one HTML Telegram message, edited in place while a brain works, finalized with the outcome.

Steps arrive from the brain adapter's reader thread; a daemon ticker re-renders every `interval` s so the
elapsed time moves even without new steps. Telegram failures never reach the caller.
"""

import html
import threading
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

LIMIT = 4096  # Telegram's message length
_STEP_MAX = 200
_STATUS = {
    "done": "✅ Done", "needs_user": "🟡 Prepared", "needs_approval": "🟠 Needs approval",
    "failed": "❌ Failed", "dropped": "⚪ Dropped meanwhile",
}


class Progress:
    def __init__(self, chat, title: str, model_line: str, steps_path: Path | None = None,
                 interval: float = 10, now=time.monotonic, message_id: int | None = None):
        self._chat, self._title, self._model_line = chat, title, model_line
        self._path, self._interval, self._now = steps_path, interval, now
        self._steps: list[str] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._id = message_id  # set: adopt that message (e.g. a queued job's) instead of sending one
        self._started = now()

    def start(self) -> None:
        if self._id is None:
            self._id = self._safely(self._chat.send_html, self.render())
        else:
            self._safely(self._chat.edit_html, self._id, self.render())
        threading.Thread(target=self._tick, daemon=True).start()

    def step(self, line: str) -> None:
        line = " ".join(line.split())[:_STEP_MAX]
        with self._lock:
            self._steps.append(line)
        if self._path:
            self._safely(self._log, line)

    def finish(self, status: str, brief: str = "", extra: str = "") -> None:
        self._stop.set()
        text = self.render(status, brief + extra)
        if self._id is None:
            self._safely(self._chat.send_html, text)
        else:
            self._safely(self._chat.edit_html, self._id, text)

    def render(self, status: str | None = None, brief: str = "") -> str:
        head = f"{_STATUS[status]}: {self._title}" if status else f"⏳ {self._title}"
        head = f"{html.escape(head)}\n{html.escape(self._model_line)} · {_elapsed(self._now() - self._started)}"
        brief = clip(brief, LIMIT - len(head) - 600) if brief else ""
        tag = "<blockquote expandable>" if status else "<blockquote>"
        room = LIMIT - len(head) - len(brief) - len(tag) - 30
        with self._lock:
            quote = _fit(self._steps, room, "✓ " if status else "")
        quote = f"\n{tag}{quote}</blockquote>" if quote else ""
        return head + quote + (f"\n{brief}" if brief else "")

    def _tick(self) -> None:
        while not self._stop.wait(self._interval):
            if self._id is not None:
                self._safely(self._chat.edit_html, self._id, self.render())

    def _log(self, line: str) -> None:
        with self._path.open("a") as f:
            f.write(f"- {datetime.now():%Y-%m-%d %H:%M:%S} {line}\n")

    @staticmethod
    def _safely(call, *args):
        try:
            return call(*args)
        except Exception as error:  # progress is cosmetic: never break the task over it
            print(f"progress: {error}")
            return None


def model_line(kind: str, settings) -> str:
    return f"{kind} · {settings.provider} {settings.model} · effort {settings.effort}"


def tracked(chat, brain, task, title: str, kind: str, message_id: int | None = None):
    """brain.run with a progress message that ends as a short Done/Failed; the reply flow is the caller's."""
    progress = Progress(chat, title, model_line(kind, task.settings), message_id=message_id)
    progress.start()
    try:
        result = brain.run(replace(task, on_step=progress.step))
    except BaseException:
        progress.finish("failed")
        raise
    progress.finish("failed" if result.reply.startswith("brain error") else "done")
    return result


def _fit(steps: list[str], room: int, mark: str) -> str:
    """Newest steps that fit in `room` escaped chars; older ones are counted, not shown."""
    lines: list[str] = []
    for line in reversed(steps):
        escaped = html.escape(mark + line)
        if sum(len(x) + 1 for x in lines) + len(escaped) + 40 > room:
            break
        lines.insert(0, escaped)
    earlier = len(steps) - len(lines)
    return "\n".join(([f"({earlier} earlier steps in steps.md)"] if earlier else []) + lines)


def clip(text: str, limit: int) -> str:
    """HTML-escaped text of at most `limit` chars, cut with … when longer."""
    if len(html.escape(text)) <= limit:
        return html.escape(text)
    cut = text[: limit - 1]
    while len(html.escape(cut)) > limit - 1:
        cut = cut[: -(len(html.escape(cut)) - limit + 1)]
    return html.escape(cut) + "…"


def _elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs}s" if minutes else f"{secs}s"
