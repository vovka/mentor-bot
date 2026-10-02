import pytest

from mentor.adapters.store.files import FileStore
from mentor.usecases import change_settings


@pytest.mark.parametrize("name", ["plan", "heavy", "coder"])
def test_tier_updates_only_that_block(tmp_path, name):
    store = FileStore(tmp_path)
    reply = change_settings.run(store, {"tier": name, "provider": "codex", "model": "gpt-5.6-terra", "effort": "xhigh"})
    raw = store.read_settings()
    assert raw[name] == {"provider": "codex", "model": "gpt-5.6-terra", "effort": "xhigh"}
    assert raw["model"] == "gpt-5.5" and name in reply


def test_tier_keeps_unspecified_fields_from_its_default(tmp_path):
    store = FileStore(tmp_path)
    change_settings.run(store, {"tier": "plan", "effort": "high", "model": None})
    assert store.read_settings()["plan"] == {"provider": "codex", "model": "gpt-5.6-sol", "effort": "high"}


def test_no_tier_changes_chat_settings(tmp_path):
    store = FileStore(tmp_path)
    change_settings.run(store, {"tier": None, "effort": "high"})
    assert store.read_settings()["effort"] == "high"


def test_astra_and_unknown_tier_rejected(tmp_path):
    store = FileStore(tmp_path)
    assert "gpt-6-astra" in change_settings.run(store, {"tier": "plan", "model": "gpt-6-astra"})
    assert "unknown tier" in change_settings.run(store, {"tier": "boss"})
    assert store.read_settings()["plan"]["model"] == "gpt-5.6-sol"
