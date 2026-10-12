"""A one-off agent run that must answer with a JSON object; retries on the fallback tier after a usage limit."""

import json

from mentor.domain.agent import AgentRun
from mentor.domain.settings import tier


def ask_json(agents, settings: dict, tiers: tuple[str, str], prompt: str, cwd: str, role: str) -> dict:
    result = None
    for name in tiers:
        result = agents.run(AgentRun(prompt, tier(settings, name), cwd, role=role))
        if not result.limited:
            break
    if not result.ok:
        raise RuntimeError(f"agent failed: {result.error[:300]}")
    return parse_object(result.text)


def parse_object(text: str) -> dict:
    """The outermost {...} in the reply; models sometimes wrap JSON in prose or a code fence."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError(f"agent did not answer with JSON: {text[:300]}")
    return json.loads(text[start:end + 1])
