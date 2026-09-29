"""E2E: compact.run folding 20 fixture history days into summary.md, no network."""

from datetime import date, datetime, timedelta

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.store.files import FileStore
from mentor.domain.actions import BrainResult
from mentor.usecases import compact
from tests.fixed_clock import FixedClock


def test_compact_folds_old_days_without_deleting_them(tmp_path):
    store = FileStore(tmp_path)
    today = date(2026, 9, 29)
    clock = FixedClock(datetime(2026, 9, 29))
    for i in range(20):
        day = today - timedelta(days=i)
        (store.data_dir / "history" / f"{day.isoformat()}.md").write_text(f"notes for {day}")
    brain = FakeBrain([BrainResult(reply="folded", actions=[], raw={}, document="summary v1")])

    status = compact.run(store, brain, clock, keep_days=14)

    assert store.read_summary() == "summary v1"
    assert len(store.list_history_days()) == 20
    assert status.startswith("folded")
    assert store.read_state()["compacted_through"] == (today - timedelta(days=14)).isoformat()
