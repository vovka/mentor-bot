"""Test clock that returns a fixed, mutable datetime — set `.now_value` to move time."""

from datetime import datetime


class FixedClock:
    def __init__(self, when: datetime):
        self.now_value = when

    def now(self) -> datetime:
        return self.now_value
