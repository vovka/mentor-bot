"""In-process scheduler: polls the clock every 30s and fires jobs that are due."""

import json
import time
from pathlib import Path
from typing import Callable

DEFAULT_SCHEDULE = {"morning": "08:00", "replan": "Sun 20:00", "compact": "Sun 21:00"}
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_schedule(data_dir: Path) -> dict[str, str]:
    path = data_dir / "schedule.json"
    if path.exists():
        return json.loads(path.read_text())
    return dict(DEFAULT_SCHEDULE)


class Scheduler:
    def __init__(self, clock, schedule: dict[str, str], runner: Callable[[str], None]):
        self._clock = clock
        self._schedule = schedule
        self._runner = runner
        self._last_fired: dict[str, str] = {}

    def run_forever(self) -> None:
        while True:
            self.tick()
            time.sleep(30)

    def tick(self) -> None:
        now = self._clock.now()
        today = now.date().isoformat()
        for name, spec in self._schedule.items():
            if self._last_fired.get(name) == today:
                continue
            if _due(now, spec):
                self._last_fired[name] = today
                self._runner(name)


def _due(now, spec: str) -> bool:
    weekday, _, hhmm = spec.rpartition(" ")
    hour, minute = (int(x) for x in hhmm.split(":"))
    if weekday and _WEEKDAYS[now.weekday()] != weekday:
        return False
    return (now.hour, now.minute) >= (hour, minute)
