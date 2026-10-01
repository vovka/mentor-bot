"""RoutingBrain: picks the provider adapter per task, building each lazily once."""

from mentor.domain.actions import BrainResult, BrainTask
from mentor.ports.brain import Brain

_SCHEMA_PATH = "prompts/output_schema.json"


def brain_for(provider: str) -> Brain:
    from mentor.adapters.brain.claude_cli import ClaudeBrain
    from mentor.adapters.brain.codex_cli import CodexBrain

    return {"codex": CodexBrain, "claude": ClaudeBrain}[provider](_SCHEMA_PATH)


class RoutingBrain:
    def __init__(self, factory=brain_for):
        self._factory = factory
        self._cache: dict[str, Brain] = {}

    def run(self, task: BrainTask) -> BrainResult:
        provider = task.settings.provider
        if provider not in self._cache:
            try:
                self._cache[provider] = self._factory(provider)
            except KeyError:
                return BrainResult(reply=f"brain error: unknown provider {provider}", actions=[], raw={})
        return self._cache[provider].run(task)
