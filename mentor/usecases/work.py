"""Autonomous work loop: take the next ready task, do it (or park it), report, repeat until done or out of budget."""

from mentor.adapters.store.lock import locked
from mentor.domain import tasks
from mentor.domain.actions import BrainResult
from mentor.domain.settings import work_limits
from mentor.usecases import apply_plan, work_brain, work_result

_BUDGET = "daily budget used"


def run(store, brain, chat, clock, mail=None) -> str:
    _reset_stale(store)
    touched: list[str] = []
    while True:
        task = _claim(store, clock)
        if not isinstance(task, tasks.Task):
            break
        touched.append(_park(store, chat, task) if task.kind == "user" else _work(store, brain, chat, clock, mail, task))
    if not touched:
        return task or "nothing ready"
    summary = "\n".join(["Work loop finished:", *touched] + ([f"Stopped: {_BUDGET}."] if task else []))
    chat.send(summary)
    apply_plan.refresh(store, chat)
    return summary


def _reset_stale(store) -> None:
    """The loop is single-instance, so anything still `running` was left by a crash."""
    with locked(store.data_dir):
        all_tasks = store.read_tasks()
        stale = [t for t in all_tasks if t.status == "running"]
        for t in stale:
            t.status = "todo"
        if stale:
            store.write_tasks(all_tasks)


def _claim(store, clock):
    """Next ready task moved to `running` (a brain run costs one daily run); `_BUDGET` or None to stop."""
    with locked(store.data_dir):
        all_tasks, state = store.read_tasks(), store.read_state()
        task = tasks.next_ready(all_tasks)
        if task is None:
            return None
        today = clock.now().date().isoformat()
        budget = state.get("work") or {}
        if budget.get("date") != today:
            budget = {"date": today, "runs": 0}
        if task.kind != "user":
            if budget["runs"] >= work_limits(store.read_settings())["daily_runs"]:
                return _BUDGET
            state["work"] = {**budget, "runs": budget["runs"] + 1}
            store.write_state(state)
        task.status = "running"
        store.write_tasks(all_tasks)
        return task


def _park(store, chat, task) -> str:
    args = {"outcome": "needs_user", "user_action": task.note or task.title}
    parked = work_result.apply(store, task.id, args)
    if parked:
        note = f"\n\n{task.note}" if task.note else ""
        chat.send(f"Your turn: {task.title}{note}", buttons=work_result.done_button(task))
    return f"- waiting on you: {task.title}"


def _work(store, brain, chat, clock, mail, task) -> str:
    try:
        result = brain.run(work_brain.build(store, clock, task, store.read_tasks()))
    except OSError as error:  # e.g. the CLI is missing: fail the task rather than retry it on every run
        result = BrainResult(reply=f"brain error: {error}", actions=[], raw={})
    args = work_result.outcome_of(result)
    updated = work_result.apply(store, task.id, args)
    if updated is None:
        return f"- dropped meanwhile: {task.title}"
    wdir = work_brain.work_dir(store, task)
    try:
        work_result.notify(store, chat, mail, updated, args, result.reply, wdir, work_brain.repo_of(store, task))
    except OSError as error:  # Telegram hiccup: the outcome is stored, keep the loop going
        print(f"work: could not report {task.id}: {error}")
    return f"- {args['outcome'].replace('_', ' ')}: {task.title}"
