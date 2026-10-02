from typing import Protocol

from mentor.domain.conversation import Update


class Chat(Protocol):
    def send(self, text: str, buttons: list[tuple[str, str]] | None = None, reply_to: int | None = None) -> int:
        """Send text; buttons = [(label, callback_data)] become one inline keyboard row; reply_to quotes a message."""

    def answer_callback(self, callback_id: str) -> None: ...

    def clear_buttons(self, message_id: int) -> None: ...

    def send_photo(self, png: bytes, caption: str) -> int: ...

    def send_document(self, data: bytes, filename: str, caption: str = "") -> int: ...

    def edit(self, id: int, text: str) -> None: ...

    def send_html(self, text: str, reply_to: int | None = None) -> int:
        """One HTML-formatted message (parse_mode HTML, no chunking); text must fit 4096 chars."""

    def edit_html(self, id: int, text: str) -> None: ...

    def pin(self, id: int) -> None: ...

    def poll(self, offset: int) -> list[Update]: ...

    def react(self, message_id: int, emoji: str | None) -> None:
        """Set (or clear, with None) the bot's reaction on a user's message."""

    def typing(self) -> None:
        """Show the 'typing…' indicator; Telegram drops it after ~5 s."""
