"""Blocking cross-process lock over a file in the data dir."""

import contextlib
import fcntl
from pathlib import Path


@contextlib.contextmanager
def locked(data_dir: Path):
    lock_path = data_dir / ".lock"
    lock_path.touch(exist_ok=True)
    with open(lock_path) as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
