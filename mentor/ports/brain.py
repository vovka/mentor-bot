from typing import Protocol

from mentor.domain.actions import BrainResult, BrainTask


class Brain(Protocol):
    def run(self, task: BrainTask) -> BrainResult: ...
