"""Start `mentor job work` in the background; the job itself makes sure only one runs."""

import os
import subprocess
import sys
from pathlib import Path

from mentor.adapters.store.lock import try_lock


def kick() -> None:
    """No-op when an executor is already waiting for its turn (it holds .kick.lock): it will see the new work."""
    data_dir = Path(os.environ.get("DATA_DIR", "./data"))
    waiting = try_lock(data_dir, ".kick.lock")
    if waiting is None:
        return
    waiting.close()
    log = (data_dir / "work.log").open("ab")
    subprocess.Popen(
        [sys.executable, "-m", "mentor.app.cli", "job", "work"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
    )
