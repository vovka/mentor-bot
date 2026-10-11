"""Gateway: Telegram messages and job reports feed one queue; one worker runs chat turns in order.

Whatever arrives while a turn runs is batched into the next turn, so the agent session never runs twice at once.
"""

import queue
import threading
from datetime import datetime

_TYPING_EVERY = 4  # seconds; Telegram drops the indicator after ~5
_SETTLE = 0.7  # seconds to wait for the rest of a burst of messages before answering


class Gateway:
    def __init__(self, store, chat, turn, announce):
        self.store, self.chat, self.turn, self.announce = store, chat, turn, announce
        self.inbox: queue.Queue = queue.Queue()

    def on_update(self, update) -> None:
        if not update.text:
            return
        self._receive(f"you: {update.text}", update.message_id)
        self.chat.react(update.message_id, "👀")

    def check_jobs(self) -> None:
        for line in self.announce():
            self._receive(line, None)

    def work(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                batch = [self.inbox.get(timeout=1)]
            except queue.Empty:
                continue
            stop.wait(_SETTLE)
            while not self.inbox.empty():
                batch.append(self.inbox.get_nowait())
            self.answer(batch)

    def answer(self, batch: list[tuple[str, int | None]]) -> None:
        reply = self._with_typing(lambda: self.turn.run([line for line, _ in batch]))
        message_ids = [m for _, m in batch if m]
        self.chat.send(reply or "(no reply)", reply_to=message_ids[-1] if message_ids else None)
        self.store.append_history(_stamp(f"mentor: {reply}"))
        for message_id in message_ids:
            self.chat.react(message_id, None)

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


def _stamp(text: str) -> str:
    return f"[{datetime.now():%H:%M}] {text}"
