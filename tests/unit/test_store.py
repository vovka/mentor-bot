from datetime import date

from mentor.adapters.store.files import FileStore
from mentor.adapters.store.jobs import JobBook


def test_change_agenda_saves_and_logs(tmp_path):
    store = FileStore(tmp_path)
    task = store.change_agenda("task_add", {"title": "x"}, "chat", lambda g: g.add_task("x"))
    assert task.id == "t1"
    assert store.agenda().task("t1").title == "x"
    [event] = store.events_since("2000")
    assert (event["op"], event["by"], event["args"]) == ("task_add", "chat", {"title": "x"})


def test_failed_change_saves_nothing(tmp_path):
    store = FileStore(tmp_path)
    try:
        store.change_agenda("task_add", {}, "chat", lambda g: g.add_task(""))
    except ValueError:
        pass
    assert store.agenda().tasks == [] and store.events_since("2000") == []


def test_history_days_and_state(tmp_path):
    store = FileStore(tmp_path)
    store.append_history("you: hi", day=date(2026, 10, 1))
    store.write_day(date(2026, 10, 1), "said hi")
    assert store.list_history_days() == [date(2026, 10, 1)]
    assert store.update_state(a=1)["a"] == 1 and store.update_state(b=2) == {"a": 1, "b": 2}


def test_job_book(tmp_path):
    book = JobBook(tmp_path)
    j1, j2 = book.create("one", "brief 1"), book.create("two", "brief 2")
    assert (j1["id"], j2["id"]) == ("1", "2")
    assert (book.dir("1") / "brief.md").read_text() == "brief 1"
    done = book.update("1", status="done")
    assert done["finished"] and [j["status"] for j in book.all()] == ["done", "queued"]
    assert book.result("1") == {}
