"""Test double for Brain: returns queued results, records tasks it was asked to run."""

from mentor.domain.actions import BrainResult, BrainTask


class FakeBrain:
    def __init__(self, results: list[BrainResult] | None = None):
        self._queue = list(results or [])
        self.tasks: list[BrainTask] = []

    def run(self, task: BrainTask) -> BrainResult:
        self.tasks.append(task)
        return self._queue.pop(0)
