from datetime import date, datetime, timedelta

from mentor.adapters.store.files import FileStore
from mentor.domain.actions import BrainResult, BrainTask
from mentor.usecases import compact
from tests.fixed_clock import FixedClock


class _DocBrain:
    """Fake brain that returns a document instead of writing summary.md, per the read-only sandbox."""

    def __init__(self, document: str | None):
        self._document = document
        self.tasks: list[BrainTask] = []

    def run(self, task: BrainTask) -> BrainResult:
        self.tasks.append(task)
        return BrainResult(reply="folded", actions=[], raw={}, document=self._document)


def _seed_days(store: FileStore, today: date, count: int) -> None:
    for i in range(count):
        day = today - timedelta(days=i)
        (store.data_dir / "history" / f"{day.isoformat()}.md").write_text(f"notes for {day}")


def test_folds_only_days_older_than_keep_days(tmp_path):
    store = FileStore(tmp_path)
    today = date(2026, 9, 29)
    _seed_days(store, today, 20)
    brain = _DocBrain("folded summary")
    clock = FixedClock(datetime(2026, 9, 29))

    status = compact.run(store, brain, clock, keep_days=14)

    assert len(brain.tasks) == 1
    prompt = brain.tasks[0].prompt
    assert (today - timedelta(days=13)).isoformat() not in prompt
    assert (today - timedelta(days=19)).isoformat() in prompt
    assert len(store.list_history_days()) == 20  # day files are never deleted
    compacted_through = (today - timedelta(days=14)).isoformat()
    assert store.read_state()["compacted_through"] == compacted_through
    assert store.read_summary() == "folded summary"
    assert status == f"folded 6 day(s) through {compacted_through}"


def test_second_call_has_nothing_to_compact(tmp_path):
    store = FileStore(tmp_path)
    today = date(2026, 9, 29)
    _seed_days(store, today, 20)
    clock = FixedClock(datetime(2026, 9, 29))
    compact.run(store, _DocBrain("first fold"), clock, keep_days=14)

    status = compact.run(store, _DocBrain("second fold"), clock, keep_days=14)

    assert status == "nothing to compact"
    assert store.read_summary() == "first fold"


def test_no_document_leaves_summary_unchanged_and_state_unadvanced(tmp_path):
    store = FileStore(tmp_path)
    today = date(2026, 9, 29)
    _seed_days(store, today, 20)
    clock = FixedClock(datetime(2026, 9, 29))

    status = compact.run(store, _DocBrain(None), clock, keep_days=14)

    assert status == "compact failed: no document"
    assert store.read_summary() == ""
    assert store.read_state().get("compacted_through") is None
