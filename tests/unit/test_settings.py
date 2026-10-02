import pytest

from mentor.domain.settings import BrainSettings, tier, validate, work_limits


def test_valid_settings():
    result = validate("codex", "gpt-5.5", "low")
    assert result == BrainSettings(provider="codex", model="gpt-5.5", effort="low")


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="gpt-9000"):
        validate("codex", "gpt-9000", "low")


def test_effort_not_allowed_for_model_raises():
    with pytest.raises(ValueError, match="ultra"):
        validate("codex", "gpt-5.5", "ultra")


def test_tier_selects_by_name():
    raw = {
        "provider": "codex", "model": "gpt-5.5", "effort": "low",
        "heavy": {"provider": "codex", "model": "gpt-5.6-sol", "effort": "high"},
    }
    assert tier(raw, "chat") == BrainSettings("codex", "gpt-5.5", "low")
    assert tier(raw, "heavy").model == "gpt-5.6-sol"
    assert tier(raw, "coder") == BrainSettings("claude", "sonnet", "high")
    assert tier(raw, "plan") == BrainSettings("codex", "gpt-5.6-sol", "medium")
    assert tier({}, "heavy") == BrainSettings("codex", "gpt-5.6-sol", "high")
    raw["plan"] = {"provider": "codex", "model": "gpt-5.5", "effort": "high"}
    assert tier(raw, "plan").model == "gpt-5.5"
    raw["coder"] = {"provider": "codex", "model": "gpt-5.5", "effort": "low"}
    assert tier(raw, "coder").provider == "codex"


def test_work_limits_overlay():
    assert work_limits({}) == {"daily_runs": 12, "timeout": 1800}
    assert work_limits({"work": {"timeout": 60}}) == {"daily_runs": 12, "timeout": 60}


def test_astra_is_not_allowed():
    with pytest.raises(ValueError, match="gpt-6-astra"):
        validate("codex", "gpt-6-astra", "high")
