"""Cross-process locks over files in the data dir."""

import contextlib
import fcntl
from pathlib import Path


@contextlib.contextmanager
def locked(data_dir: Path, name: str = ".lock"):
    lock_path = data_dir / name
    lock_path.touch(exist_ok=True)
    with open(lock_path) as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def try_lock(data_dir: Path, name: str):
    """The open file holding an exclusive lock on `name` (close it to release), or None when it is busy."""
    f = open(data_dir / name, "a")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f
