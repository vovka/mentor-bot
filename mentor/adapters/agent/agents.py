"""Agents: dispatch a run to the CLI adapter named by its tier's provider."""

from mentor.domain.agent import AgentResult, AgentRun


class Agents:
    def __init__(self, by_provider: dict):
        self.by_provider = by_provider

    def run(self, request: AgentRun) -> AgentResult:
        agent = self.by_provider.get(request.tier.provider)
        if agent is None:
            return AgentResult("", error=f"unknown provider {request.tier.provider!r}")
        return agent.run(request)
