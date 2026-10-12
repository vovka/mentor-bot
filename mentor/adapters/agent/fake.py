"""FakeAgent: returns queued results in order and records every request."""

from mentor.domain.agent import AgentResult


class FakeAgent:
    def __init__(self, *results: AgentResult):
        self.results = list(results)
        self.requests = []

    def run(self, request) -> AgentResult:
        self.requests.append(request)
        return self.results.pop(0) if self.results else AgentResult("ok", session="s-default")
