"""Test double for Mail: records drafts."""


class FakeMail:
    def __init__(self):
        self.drafts: list[tuple[str, str, str]] = []

    def draft(self, to: str, subject: str, body: str) -> None:
        self.drafts.append((to, subject, body))
