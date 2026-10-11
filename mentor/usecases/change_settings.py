"""change_settings use case: validate + persist BrainSettings for one tier (chat, plan, heavy, coder)."""

from typing import Any

from mentor.domain.settings import tier, validate


def run(store, args: dict[str, Any]) -> str:
    name = args.get("tier") or "chat"
    if name not in ("chat", "plan", "heavy", "coder"):
        return f"unknown tier {name!r}; allowed: chat, plan, heavy, coder"
    block = tier(store.read_settings(), name)
    provider = args.get("provider") or block.provider
    model = args.get("model") or block.model
    effort = args.get("effort") or block.effort

    try:
        settings = validate(provider, model, effort)
    except ValueError as exc:
        return str(exc)

    store.write_tier(name, settings)
    return f"Settings updated ({name}): {settings.provider}/{settings.model}/{settings.effort}"
