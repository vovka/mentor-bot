import subprocess

from mentor.adapters.store.lock import try_lock
from mentor.app import kick as kick_module


def test_kick_spawns_only_when_no_executor_is_waiting(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: spawned.append(a))
    waiter = try_lock(tmp_path, ".kick.lock")  # a waiting executor holds it
    kick_module.kick()
    assert spawned == []
    waiter.close()
    kick_module.kick()
    assert len(spawned) == 1
