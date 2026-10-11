"""E2E: a full bot day against a fake Telegram Bot API and a scripted fake brain, no network.

Wires the real handle_update/morning_brief/replan use cases the way mentor.app.container.build
does, but with FakeBrain and a TelegramChat pointed at BotApiStub via TELEGRAM_API_BASE.
"""

import json
import shutil
from datetime import date, datetime
from pathlib import Path

from mentor.adapters.brain.fake import FakeBrain
from mentor.adapters.render.fake import FakeRenderer
from mentor.adapters.store.files import FileStore
from mentor.adapters.telegram.api import TelegramChat
from mentor.app.container import Container
from mentor.domain.actions import Action, BrainResult
from mentor.domain.conversation import Update
from mentor.usecases import handle_update, morning_brief, work
from tests.e2e.bot_api_stub import BotApiStub
from tests.fixed_clock import FixedClock

_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "data" / "projects" / "_template"
_REPLAN_ACTION = [Action(kind="replan", args={"reason": "move demo to Friday"})]


_DOC = '{"tasks": [{"id": "a-1", "title": "do it"}]}'


def _build_container(tmp_path, stub, monkeypatch) -> Container:
    monkeypatch.setenv("TELEGRAM_API_BASE", stub.base_url)
    store = FileStore(tmp_path)
    shutil.copytree(_TEMPLATE, store.data_dir / "projects" / "_template")
    store.add_project("alpha", "/repo/alpha")
    store.add_project("beta", "/repo/beta")
    # no task budget: the inline executor runs queued jobs only (jobs don't count against daily_runs)
    settings = store.read_settings()
    (tmp_path / "settings.json").write_text(json.dumps({**settings, "work": {"daily_runs": 0}}))
    chat = TelegramChat("stub-token", str(stub.chat_id))
    clock = FixedClock(datetime(2026, 9, 29, 8, 0))
    return Container(store=store, brain=FakeBrain([]), chat=chat, clock=clock, renderer=FakeRenderer(b"PNG"))


def _step(container, stub, offset, text, results):
    """Enqueue a message, script the brain's reply, poll+handle it like cli._serve does."""
    stub.enqueue(text)
    container.brain = FakeBrain(results)
    for update in container.chat.poll(offset):
        handle_update.run(
            container.store, container.brain, container.chat, container.clock, update,
            renderer=container.renderer, kick=lambda: _executor(container),
        )
        offset = update.update_id + 1
    return offset


def _executor(c):
    """kick() inline: the work loop drains the queue in this process instead of a background one."""
    work.run(c.store, c.brain, c.chat, c.clock)


def _replan_results(reply: str, document: str) -> list[BrainResult]:
    return [
        BrainResult(reply=reply, actions=_REPLAN_ACTION, raw={}),
        BrainResult(reply="plan changed", actions=[], raw={}, document=document),
    ]


def test_full_day_scenario(tmp_path, monkeypatch):
    stub = BotApiStub()
    container = _build_container(tmp_path, stub, monkeypatch)
    offset = 1

    # a. plain question -> one reply, recorded in history.
    results = [BrainResult(reply="due today: item X", actions=[], raw={})]
    offset = _step(container, stub, offset, "what's due?", results)
    sends = [c for c in stub.calls if c[0] == "sendMessage"]
    assert len(sends) == 1 and sends[0][1]["text"] == "due today: item X"
    history = container.store.read_history(date.today())
    assert "user: what's due?" in history and "bot: due today: item X" in history

    # b. settings change via action.
    settings_action = [Action(kind="set_settings", args={"model": "gpt-5.6-sol", "effort": "low"})]
    results = [BrainResult(reply="switching model", actions=settings_action, raw={})]
    offset = _step(container, stub, offset, "use gpt-5.6-sol low", results)
    settings = container.store.read_settings()
    assert settings["model"] == "gpt-5.6-sol" and settings["effort"] == "low"
    last_send = [c for c in stub.calls if c[0] == "sendMessage"][-1]
    assert "Settings updated" in last_send[1]["text"]
    methods = [c[0] for c in stub.calls]
    assert "sendChatAction" in methods and methods[-1] == "setMessageReaction"

    # b2. send_image action -> rendered via the fake renderer, posted with multipart sendPhoto.
    image_action = [Action(kind="send_image", args={"diagram": "gantt\n  title t", "caption": "Plan"})]
    results = [BrainResult(reply="here is the gantt", actions=image_action, raw={})]
    offset = _step(container, stub, offset, "draw the plan", results)
    photos = [c for c in stub.calls if c[0] == "sendPhoto"]
    assert len(photos) == 1 and photos[0][1]["_bytes"] > len(b"PNG")
    assert "(image sent)" in [c for c in stub.calls if c[0] == "sendMessage"][-1][1]["text"]

    # c. replan action -> plan.md updated, sendMessage + pinChatMessage on first run.
    calls_before = len(stub.calls)
    offset = _step(container, stub, offset, "move demo to Friday", _replan_results("on it", _DOC))
    assert container.store.read_plan() == "**Next:** do it\n\nDone: 0 of 1"
    new_calls = [c[0] for c in stub.calls[calls_before:]]
    assert "sendMessage" in new_calls and "pinChatMessage" in new_calls
    pinned_id = container.store.read_state()["pinned_message_id"]

    # run the same again -> editMessageText on the same pinned id, no second pin.
    calls_before = len(stub.calls)
    offset = _step(container, stub, offset, "move demo to Friday", _replan_results("on it again", _DOC))
    edits = [c[1] for c in stub.calls[calls_before:] if c[0] == "editMessageText"]
    assert [e["message_id"] for e in edits if "parse_mode" not in e] == [pinned_id]
    assert any(e["text"].startswith("✅ Done: Replanning") and e["parse_mode"] == "HTML" for e in edits)
    assert len([c for c in stub.calls if c[0] == "pinChatMessage"]) == 1

    # d. replaying an already-seen update_id makes zero new Bot API calls.
    calls_before = len(stub.calls)
    stale = Update(update_id=1, chat_id=stub.chat_id, text="anything", at=datetime.now())
    handle_update.run(container.store, container.brain, container.chat, container.clock, stale)
    assert len(stub.calls) == calls_before

    # e. morning brief: one send; same-day rerun sends nothing, brain not called.
    container.brain = FakeBrain([BrainResult(reply="good morning", actions=[], raw={})])
    calls_before = len(stub.calls)
    first = morning_brief.run(container.store, container.brain, container.chat, container.clock)
    assert first == "good morning"
    assert [c[0] for c in stub.calls[calls_before:]] == ["sendMessage"]

    container.brain = FakeBrain([])  # would raise if the brain were called again
    calls_before = len(stub.calls)
    second = morning_brief.run(container.store, container.brain, container.chat, container.clock)
    assert second == "already sent"
    assert len(stub.calls) == calls_before

    stub.stop()
