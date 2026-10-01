"""Test double for Chat: in-memory outbox, no network."""

from mentor.domain.conversation import Update


class FakeChat:
    def __init__(self, updates: list[Update] | None = None):
        self.outbox: list[str] = []
        self.edits: list[tuple[int, str]] = []
        self.pinned: list[int] = []
        self.reactions: list[tuple[int, str | None]] = []
        self.photos: list[tuple[bytes, str]] = []
        self.typing_calls = 0
        self.buttons: dict[int, list[tuple[str, str]]] = {}
        self.answered: list[str] = []
        self.cleared: list[int] = []
        self._updates = list(updates or [])
        self._next_id = 1

    def send(self, text: str, buttons: list[tuple[str, str]] | None = None) -> int:
        self.outbox.append(text)
        msg_id = self._next_id
        self._next_id += 1
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

    def edit(self, id: int, text: str) -> None:
        self.edits.append((id, text))

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
