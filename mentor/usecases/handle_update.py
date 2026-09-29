"""handle_update use case: dedup Telegram updates by update_id, then handle the message."""

from mentor.adapters.store.lock import locked
from mentor.domain.conversation import Update
from mentor.usecases import handle_message


def run(store, brain, chat, clock, update: Update, renderer=None) -> None:
    with locked(store.data_dir):
        state = store.read_state()
        if update.update_id <= state.get("last_update_id", 0):
            return
        state["last_update_id"] = update.update_id
        store.write_state(state)

    if not update.text.strip():
        return

    handle_message.run(store, brain, chat, clock, update.text, update.message_id, renderer)
