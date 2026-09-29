import pytest

from mentor.domain.settings import BrainSettings, validate


def test_valid_settings():
    result = validate("codex", "gpt-5.5", "low")
    assert result == BrainSettings(provider="codex", model="gpt-5.5", effort="low")


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="gpt-9000"):
        validate("codex", "gpt-9000", "low")


def test_effort_not_allowed_for_model_raises():
    with pytest.raises(ValueError, match="ultra"):
        validate("codex", "gpt-5.5", "ultra")
