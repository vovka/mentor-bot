from datetime import datetime

from mentor.adapters.scheduler.inprocess import Scheduler
from tests.fixed_clock import FixedClock


def test_fires_once_per_slot_not_again_same_day():
    clock = FixedClock(datetime(2026, 9, 29, 7, 59))
    fired = []
    scheduler = Scheduler(clock, {"morning": "08:00"}, runner=fired.append)

    scheduler.tick()
    assert fired == []

    clock.now_value = datetime(2026, 9, 29, 8, 0)
    scheduler.tick()
    assert fired == ["morning"]

    clock.now_value = datetime(2026, 9, 29, 8, 30)
    scheduler.tick()
    assert fired == ["morning"]


def test_weekly_job_only_fires_on_its_weekday():
    clock = FixedClock(datetime(2026, 9, 28, 20, 0))  # a Monday
    fired = []
    scheduler = Scheduler(clock, {"replan": "Sun 20:00"}, runner=fired.append)

    scheduler.tick()
    assert fired == []

    clock.now_value = datetime(2026, 10, 4, 20, 0)  # the following Sunday
    scheduler.tick()
    assert fired == ["replan"]
