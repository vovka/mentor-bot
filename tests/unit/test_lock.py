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


def test_named_lock_blocks_a_second_acquirer_until_released(tmp_path):
    holding, release, order = threading.Event(), threading.Event(), []

    def first():
        with locked(tmp_path, ".work.lock"):
            holding.set()
            release.wait()
            order.append("first")

    def second():
        with locked(tmp_path, ".work.lock"):
            order.append("second")

    t1 = threading.Thread(target=first)
    t1.start()
    holding.wait()
    t2 = threading.Thread(target=second)
    t2.start()
    t2.join(0.2)
    assert t2.is_alive() and order == []
    release.set()
    t1.join(), t2.join()
    assert order == ["first", "second"]
