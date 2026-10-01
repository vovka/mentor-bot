"""Start `mentor job work` in the background; the job itself makes sure only one runs."""

import os
import subprocess
import sys
from pathlib import Path


def kick() -> None:
    log = (Path(os.environ.get("DATA_DIR", "./data")) / "work.log").open("ab")
    subprocess.Popen(
        [sys.executable, "-m", "mentor.app.cli", "job", "work"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
    )
