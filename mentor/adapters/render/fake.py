"""Test double for Renderer: returns fixed bytes or raises."""


class FakeRenderer:
    def __init__(self, png: bytes = b"PNG", error: str | None = None):
        self.png, self.error = png, error
        self.rendered: list[str] = []

    def render(self, mermaid: str) -> bytes:
        self.rendered.append(mermaid)
        if self.error:
            raise RuntimeError(self.error)
        return self.png
