"""Which model runs which role. Edited by hand in data/settings.json; missing keys take these defaults."""

from dataclasses import dataclass

# ChatGPT-account login accepts gpt-6-astra and gpt-5.6-* (probed 2026-10-11); gpt-6-luna/gpt-6.1-sol are rejected.
DEFAULTS = {
    "chat": {"provider": "codex", "model": "gpt-5.6-luna", "effort": "low"},
    "job": {"provider": "codex", "model": "gpt-6-astra", "effort": "high"},
    "morning": {"provider": "codex", "model": "gpt-6-astra", "effort": "medium"},
    "chat_fallback": {"provider": "claude", "model": "haiku", "effort": "low"},
    "job_fallback": {"provider": "claude", "model": "opus", "effort": "high"},
}


@dataclass(frozen=True)
class Tier:
    provider: str
    model: str
    effort: str


def tier(raw: dict, name: str) -> Tier:
    return Tier(**{**DEFAULTS[name], **raw.get(name, {})})
