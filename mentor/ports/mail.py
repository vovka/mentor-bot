from typing import Protocol


class Mail(Protocol):
    def draft(self, to: str, subject: str, body: str) -> None:
        """Save an unsent email draft. Never sends. Errors propagate to the caller."""
