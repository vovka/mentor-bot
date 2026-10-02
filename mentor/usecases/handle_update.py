"""handle_update use case: dedup Telegram updates by update_id, then route /cancel, a button press or a message."""

import os
import signal
from pathlib import Path

from mentor.adapters.store.lock import locked
from mentor.domain.conversation import Update
from mentor.usecases import checkin, handle_message, queue, task_buttons


def run(store, brain, chat, clock, update: Update, renderer=None, kick=lambda: None) -> None:
    if claim(store, update):
        route(store, brain, chat, clock, update, renderer, kick)


def claim(store, update: Update) -> bool:
    """Dedup by update_id; False for a replayed update. Serve calls this in poll order, before the thread."""
    with locked(store.data_dir):
        state = store.read_state()
        if update.update_id <= state.get("last_update_id", 0):
            return False
        state["last_update_id"] = update.update_id
        store.write_state(state)
        return True


def route(store, brain, chat, clock, update: Update, renderer=None, kick=lambda: None) -> None:
    if update.text.strip() == "/cancel":
        chat.send(_cancel(store), reply_to=update.message_id)
        return
    if update.callback_data.startswith("t:"):
        task_buttons.on_button(store, chat, update, kick)
        return
    if update.callback_data:
        checkin.on_button(store, brain, chat, clock, update)
        kick()  # an approved plan may have made tasks ready
        return
    if not update.text.strip():
        return

    handle_message.run(store, brain, chat, clock, update.text, update.message_id, renderer, kick)
    checkin.after_message(store, brain, chat, clock)


def _cancel(store) -> str:
    """SIGUSR1 makes the executor kill its running brain CLI; the job or task then fails normally."""
    pid = store.read_state().get("executor_pid")
    if not pid or not _is_executor(pid):
        _clear_executor_pid(store)
        return "Nothing is running."
    try:
        os.kill(pid, signal.SIGUSR1)
    except ProcessLookupError:
        return "Nothing is running."
    what = _running(store)
    return f"Cancelling: {what}" if what else "Cancelling the current job."


def _is_executor(pid: int) -> bool:
    """Alive and ours (`mentor job work`), not a stranger that reused the pid after a crash."""
    try:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    return b"job" in args and b"work" in args


def _clear_executor_pid(store) -> None:
    with locked(store.data_dir):
        state = store.read_state()
        if state.get("executor_pid"):
            state["executor_pid"] = None
            store.write_state(state)


def _running(store) -> str:
    """The task in `running`, else the job taken by the executor, else ""."""
    task = next((t for t in store.read_tasks() if t.status == "running"), None)
    if task:
        return task.title
    job = next((j for j in queue.pending(store) if j["attempts"]), None)
    return queue.LABELS[job["kind"]] if job else ""
