import json
import threading

from mentor.adapters.store.lock import locked


def _increment(data_dir, times):
    for _ in range(times):
        with locked(data_dir):
            path = data_dir / "state.json"
            state = json.loads(path.read_text()) if path.exists() else {"count": 0}
            state["count"] += 1
            path.write_text(json.dumps(state))


def test_lock_serializes_concurrent_increments(tmp_path):
    t1 = threading.Thread(target=_increment, args=(tmp_path, 50))
    t2 = threading.Thread(target=_increment, args=(tmp_path, 50))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["count"] == 100
