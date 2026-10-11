import pytest

from mentor.domain.tasks import Agenda, render


def test_add_update_status_and_render():
    g = Agenda()
    aim = g.add_aim("Get a job", why="money", target="2026-12-01")
    t = g.add_task("Send CV to Acme", aim=aim.id, deadline="2026-10-16")
    assert (aim.id, t.id) == ("a1", "t1")
    g.update_task("t1", status="paused", notes="wait for referral")
    assert g.task("t1").status == "paused"
    assert "t1 Send CV to Acme (paused, aim a1, due 2026-10-16)" in render(g)


@pytest.mark.parametrize("call", [
    lambda g: g.add_task(""),
    lambda g: g.add_task("x", aim="a9"),
    lambda g: g.add_task("x", deadline="Friday"),
    lambda g: g.update_task("t1", status="running"),
    lambda g: g.update_task("t1", priority=1),
    lambda g: g.update_task("t404", title="x"),
    lambda g: g.reorder(["t1", "t1"]),
])
def test_invalid_operations_raise(call):
    g = Agenda()
    g.add_task("one")
    with pytest.raises(ValueError):
        call(g)


def test_reorder_ranks_listed_and_clears_others():
    g = Agenda()
    for title in ("a", "b", "c"):
        g.add_task(title)
    g.reorder(["t3", "t1"])
    assert [(t.id, t.priority) for t in g.open_tasks()] == [("t3", 1), ("t1", 2), ("t2", None)]
    g.reorder(["t2"])
    assert g.task("t3").priority is None


def test_round_trip_and_ids_continue_after_removed():
    g = Agenda()
    g.add_task("a")
    g.update_task("t1", status="removed")
    g2 = Agenda.from_dict(g.to_dict())
    assert g2.add_task("b").id == "t2"
    assert g2.open_tasks()[0].id == "t2"
