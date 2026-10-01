"""handle_update use case: dedup Telegram updates by update_id, then route a button press or a message."""

from mentor.adapters.store.lock import locked
from mentor.domain.conversation import Update
from mentor.usecases import checkin, handle_message, task_buttons


def run(store, brain, chat, clock, update: Update, renderer=None, kick=lambda: None) -> None:
    with locked(store.data_dir):
        state = store.read_state()
        if update.update_id <= state.get("last_update_id", 0):
            return
        state["last_update_id"] = update.update_id
        store.write_state(state)

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
