import threading
from datetime import date, datetime, timezone
from types import SimpleNamespace

from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.fake import FakeChat
from mentor.app.cli import dispatch, serve_loop
from mentor.domain.actions import BrainResult
from mentor.domain.conversation import Update
from tests.fixed_clock import FixedClock

_AT = datetime(2026, 10, 1, tzinfo=timezone.utc)


class _BlockingBrain:
    """The first call waits for `release`; later calls answer at once."""

    def __init__(self):
        self.started, self.release, self._calls = threading.Event(), threading.Event(), 0
        self._lock = threading.Lock()

    def run(self, task):
        with self._lock:
            self._calls += 1
            first = self._calls == 1
        if first:
            self.started.set()
            self.release.wait()
        return BrainResult(reply="one" if first else "two", actions=[], raw={})


def _container(tmp_path, brain, chat):
    return SimpleNamespace(store=FileStore(tmp_path), brain=brain, chat=chat,
                           clock=FixedClock(_AT), renderer=None)


def _msg(update_id, text, message_id):
    return Update(update_id=update_id, chat_id=1, text=text, at=_AT, message_id=message_id)


def test_second_message_is_answered_while_the_first_is_still_thinking(tmp_path):
    brain, chat = _BlockingBrain(), FakeChat()
    c = _container(tmp_path, brain, chat)
    [first] = dispatch(c, _msg(1, "slow question", 100), kick=lambda: None)
    assert brain.started.wait(5)
    [second] = dispatch(c, _msg(2, "quick question", 200), kick=lambda: None)
    second.join(5)
    assert chat.outbox == ["two"] and chat.replies == {1: 200}
    history = c.store.read_history(date.today())
    assert "user: slow question" in history and "user: quick question" in history
    brain.release.set()
    first.join(5)
    assert chat.outbox == ["two", "one"] and chat.replies == {1: 200, 2: 100}


def test_replayed_update_is_not_dispatched(tmp_path):
    brain = _BlockingBrain()
    brain.release.set()
    c = _container(tmp_path, brain, FakeChat())
    dispatch(c, _msg(1, "hi", 10), kick=lambda: None)[0].join(5)
    assert dispatch(c, _msg(1, "hi", 10), kick=lambda: None) == []


def test_stop_event_ends_the_loop_after_the_poll_and_joins_handlers(tmp_path):
    brain, stop = _BlockingBrain(), threading.Event()
    brain.release.set()
    chat = FakeChat([_msg(1, "hello", 10)])
    poll = chat.poll

    def poll_then_stop(offset):
        stop.set()  # SIGTERM arriving during the long poll
        return poll(offset)

    chat.poll = poll_then_stop
    serve_loop(_container(tmp_path, brain, chat), stop, kick=lambda: None)
    assert chat.outbox == ["one"] and chat.replies == {1: 10}
