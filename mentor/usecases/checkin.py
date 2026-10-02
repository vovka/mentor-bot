"""Check-in buttons (yes/no/approve/reject) and the awaiting-updates hook after a chat message."""

from mentor.usecases import apply_plan, checkin_state, morning_brief, queue

_AWAIT = "OK, send me your updates by 09:00."
_ASK_CHANGE = "What should I change instead?"
_STAGE_FOR = {"yes": "asked", "no": "asked", "approve": "proposed", "reject": "proposed"}


def on_button(store, brain, chat, clock, update) -> str:
    chat.answer_callback(update.callback_id)
    chat.clear_buttons(update.message_id)
    stage = _STAGE_FOR.get(update.callback_data)
    checkin = stage and checkin_state.claim(store, {stage}, update.message_id)
    if not checkin:
        chat.send("Already handled.")
        return "stale"
    return _HANDLERS[update.callback_data](store, brain, chat, clock, checkin)


def after_message(store, brain, chat, clock, kick=lambda: None) -> None:
    if checkin_state.claim(store, {"awaiting_updates"}):
        queue.push(store, chat, "reconcile", {})
        kick()


def _no(store, brain, chat, clock, checkin) -> str:
    checkin_state.save(store, {**checkin, "stage": "awaiting_updates"})
    chat.send(_AWAIT)
    return _AWAIT


def _yes(store, brain, chat, clock, checkin) -> str:
    return queue.push(store, chat, "reconcile", {})  # handle_update kicks the executor after any button


def _approve(store, brain, chat, clock, checkin) -> str:
    error = apply_plan.run(store, chat, checkin["document"])
    if error:
        chat.send(f"Plan not changed: {error}")
    checkin_state.save(store, None)
    return morning_brief.run(store, brain, chat, clock)


def _reject(store, brain, chat, clock, checkin) -> str:
    checkin_state.save(store, None)
    chat.send(_ASK_CHANGE)
    return _ASK_CHANGE


_HANDLERS = {"yes": _yes, "no": _no, "approve": _approve, "reject": _reject}
