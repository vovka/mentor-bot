"""Test double for Chat: in-memory outbox, no network."""

import threading

from mentor.domain.conversation import Update


class FakeChat:
    def __init__(self, updates: list[Update] | None = None):
        self.outbox: list[str] = []
        self.edits: list[tuple[int, str]] = []
        self.pinned: list[int] = []
        self.html_sent: list[str] = []
        self.html_edits: list[tuple[int, str]] = []
        self.reactions: list[tuple[int, str | None]] = []
        self.photos: list[tuple[bytes, str]] = []
        self.documents: list[tuple[str, str, int]] = []
        self.typing_calls = 0
        self.buttons: dict[int, list[tuple[str, str]]] = {}
        self.answered: list[str] = []
        self.cleared: list[int] = []
        self._updates = list(updates or [])
        self.replies: dict[int, int] = {}  # message id -> id of the message it replies to
        self._next_id = 1
        self._ids = threading.Lock()  # handler threads send concurrently

    def _new_id(self, reply_to: int | None) -> int:
        with self._ids:
            msg_id = self._next_id
            self._next_id += 1
        if reply_to:
            self.replies[msg_id] = reply_to
        return msg_id

    def send(self, text: str, buttons: list[tuple[str, str]] | None = None, reply_to: int | None = None) -> int:
        self.outbox.append(text)
        msg_id = self._new_id(reply_to)
        if buttons:
            self.buttons[msg_id] = buttons
        return msg_id

    def answer_callback(self, callback_id: str) -> None:
        self.answered.append(callback_id)

    def clear_buttons(self, message_id: int) -> None:
        self.cleared.append(message_id)

    def send_photo(self, png: bytes, caption: str) -> int:
        self.photos.append((png, caption))
        return self.send(f"[photo] {caption}")

    def send_document(self, data: bytes, filename: str, caption: str = "") -> int:
        self.documents.append((filename, caption, len(data)))
        return self.send(f"[document] {filename} {caption}".strip())

    def edit(self, id: int, text: str) -> None:
        self.edits.append((id, text))

    def send_html(self, text: str, reply_to: int | None = None) -> int:
        self.html_sent.append(text)
        return self._new_id(reply_to)

    def edit_html(self, id: int, text: str) -> None:
        self.html_edits.append((id, text))

    def pin(self, id: int) -> None:
        self.pinned.append(id)

    def poll(self, offset: int) -> list[Update]:
        updates = [u for u in self._updates if u.update_id >= offset]
        self._updates = []
        return updates

    def react(self, message_id: int, emoji: str | None) -> None:
        self.reactions.append((message_id, emoji))

    def typing(self) -> None:
        self.typing_calls += 1
