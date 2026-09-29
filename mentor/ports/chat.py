from typing import Protocol

from mentor.domain.conversation import Update


class Chat(Protocol):
    def send(self, text: str) -> int: ...

    def edit(self, id: int, text: str) -> None: ...

    def pin(self, id: int) -> None: ...

    def poll(self, offset: int) -> list[Update]: ...

    def react(self, message_id: int, emoji: str | None) -> None:
        """Set (or clear, with None) the bot's reaction on a user's message."""

    def typing(self) -> None:
        """Show the 'typing…' indicator; Telegram drops it after ~5 s."""
