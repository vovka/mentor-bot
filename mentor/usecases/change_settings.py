"""change_settings use case: validate + persist BrainSettings (regular or heavy)."""

from typing import Any

from mentor.domain.settings import validate


def run(store, args: dict[str, Any]) -> str:
    heavy = args.get("heavy") is True
    current = store.read_settings()
    block = current.get("heavy", {}) if heavy else current
    provider = args.get("provider", block.get("provider"))
    model = args.get("model", block.get("model"))
    effort = args.get("effort", block.get("effort"))

    try:
        settings = validate(provider, model, effort)
    except ValueError as exc:
        return str(exc)

    if heavy:
        store.write_heavy_settings(settings)
        return f"Heavy settings updated: {settings.provider}/{settings.model}/{settings.effort}"
    store.write_settings(settings)
    return f"Settings updated: {settings.provider}/{settings.model}/{settings.effort}"
