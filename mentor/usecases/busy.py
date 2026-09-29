"""busy: chat-level progress indicators while a brain call runs (no extra messages).

👀 reaction on the user's message = received; "typing…" keep-alive = working;
🤔 = a heavy action (replan/scout) started; reaction cleared = reply sent.
"""

import threading
from contextlib import contextmanager

_TYPING_INTERVAL = 4  # Telegram forgets "typing" after ~5 s


@contextmanager
def busy(chat, message_id: int = 0):
    if message_id:
        chat.react(message_id, "👀")
    stop = threading.Event()

    def keep_typing():
        while not stop.is_set():
            chat.typing()
            stop.wait(_TYPING_INTERVAL)

    threading.Thread(target=keep_typing, daemon=True).start()
    try:
        yield
    finally:
        stop.set()
        if message_id:
            chat.react(message_id, None)
