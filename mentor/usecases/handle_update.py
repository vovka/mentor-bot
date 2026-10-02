"""handle_update use case: dedup Telegram updates by update_id, then route /cancel, a button press or a message."""

import os
import signal

from mentor.adapters.store.lock import locked
from mentor.domain.conversation import Update
from mentor.usecases import checkin, handle_message, task_buttons


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
        chat.send(_cancel(store.read_state().get("executor_pid")), reply_to=update.message_id)
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
    checkin.after_message(store, brain, chat, clock, kick)


def _cancel(pid) -> str:
    """SIGTERM makes the executor kill its running brain CLI; the job or task then fails normally."""
    if not pid:
        return "Nothing is running."
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return "Nothing is running."
    return "Cancelling the current job."
