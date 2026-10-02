"""Brain provider/model/effort selection and validation."""

from dataclasses import dataclass

ALLOWED = {
    "codex": {  # models the ChatGPT-account login accepts (probed 2026-09-29)
        "gpt-5.5": ["low", "medium", "high", "xhigh"],
        "gpt-5.6-luna": ["low", "medium", "high", "xhigh", "max"],
        "gpt-5.6-sol": ["low", "medium", "high", "xhigh", "max", "ultra"],
        "gpt-5.6-terra": ["low", "medium", "high", "xhigh", "max", "ultra"],
        "gpt-reserve": ["low", "medium", "high", "xhigh", "max"],
    },
    "claude": {
        "haiku": ["low", "medium", "high"],
        "sonnet": ["low", "medium", "high", "xhigh", "max"],
        "opus": ["low", "medium", "high", "xhigh", "max"],
        "fable": ["low", "medium", "high", "xhigh", "max"],
        "claude-opus-5-5": ["low", "medium", "high", "xhigh", "max"],
    },
}


@dataclass(frozen=True)
class BrainSettings:
    provider: str
    model: str
    effort: str


def validate(provider: str, model: str, effort: str) -> BrainSettings:
    models = ALLOWED.get(provider)
    if models is None:
        raise ValueError(f"unknown provider {provider!r}; allowed: {sorted(ALLOWED)}")
    efforts = models.get(model)
    if efforts is None:
        raise ValueError(f"unknown model {model!r} for {provider}; allowed: {sorted(models)}")
    if effort not in efforts:
        raise ValueError(f"unknown effort {effort!r} for {provider}/{model}; allowed: {efforts}")
    return BrainSettings(provider=provider, model=model, effort=effort)


DEFAULT_CODER = {"provider": "claude", "model": "sonnet", "effort": "high"}
DEFAULT_HEAVY = {"provider": "codex", "model": "gpt-5.6-sol", "effort": "high"}
DEFAULT_PLAN = {"provider": "codex", "model": "gpt-5.6-sol", "effort": "medium"}
DEFAULT_WORK = {"daily_runs": 12, "timeout": 1800}


def tier(raw: dict, name: str) -> BrainSettings:
    """chat = top-level provider/model/effort; plan, heavy and coder = their key, else the default."""
    defaults = {"plan": DEFAULT_PLAN, "heavy": DEFAULT_HEAVY, "coder": DEFAULT_CODER}
    src = raw if name == "chat" else raw.get(name, defaults[name])
    return BrainSettings(src["provider"], src["model"], src["effort"])


def work_limits(raw: dict) -> dict:
    return {**DEFAULT_WORK, **raw.get("work", {})}
