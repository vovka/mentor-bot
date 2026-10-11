import pytest


@pytest.fixture(autouse=True)
def _no_browser_env(monkeypatch):
    """A BROWSER_CDP_URL exported in the developer's shell must not leak into command-building tests."""
    monkeypatch.delenv("BROWSER_CDP_URL", raising=False)
