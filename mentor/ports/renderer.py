from typing import Protocol


class Renderer(Protocol):
    def render(self, mermaid: str) -> bytes:
        """Mermaid source -> PNG bytes. Raises RuntimeError with a short reason on failure."""
