from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.brain.router import RoutingBrain
from mentor.domain.actions import BrainResult, BrainTask
from mentor.domain.settings import BrainSettings


def _task(provider):
    return BrainTask("p", "/tmp", False, BrainSettings(provider, "m", "low"))


def test_routes_by_provider_and_caches():
    built = []
    brains = {"codex": FakeBrain([BrainResult("c1", [], {}), BrainResult("c2", [], {})]),
              "claude": FakeBrain([BrainResult("cl", [], {})])}

    def factory(provider):
        built.append(provider)
        return brains[provider]

    router = RoutingBrain(factory)
    assert [router.run(_task(p)).reply for p in ("codex", "claude", "codex")] == ["c1", "cl", "c2"]
    assert built == ["codex", "claude"]


def test_unknown_provider_returns_error():
    result = RoutingBrain().run(_task("gemini"))
    assert result.reply == "brain error: unknown provider gemini"
    assert result.actions == []
