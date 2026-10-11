"""Morning: close yesterday (day summary, rolling context), rank today's tasks, post priorities, fresh chat."""

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from mentor.domain.tasks import render
from mentor.usecases.jobs import summary
from mentor.usecases.oneshot import ask_json

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "morning.md"
POST_AT = (8, 0)


def run(store, book, chat, agents, cwd: str, wait: bool = True, today: date | None = None) -> str:
    today = today or date.today()
    since = store.read_state().get("last_morning", (today - timedelta(days=1)).isoformat())
    answer = ask_json(agents, store.read_settings(), ("morning", "job_fallback"),
                      prompt(store, book, today, since), cwd, role="morning")
    yesterday = today - timedelta(days=1)
    store.write_day(yesterday, answer["day_summary"])
    store.write_context(answer["context"])
    if wait:
        _sleep_until(datetime.combine(today, datetime.min.time()).replace(hour=POST_AT[0], minute=POST_AT[1]))
    chat.send(answer["post"])
    store.append_history(f"[{datetime.now():%H:%M}] mentor (morning post): {answer['post']}", day=today)
    store.update_state(chat={}, last_morning=datetime.now().isoformat(timespec="seconds"))
    return answer["post"]


def prompt(store, book, today: date, since: str) -> str:
    yesterday = today - timedelta(days=1)
    finished = [f"- job {j['id']} [{j['status']}] {j['title']}: {summary(book.result(j['id']))}"
                for j in book.all() if j["finished"] >= since]
    events = [json.dumps(e, ensure_ascii=False) for e in store.events_since(since)]
    return "\n\n".join([
        PROMPT.read_text(), f"Today: {today:%A %Y-%m-%d}",
        "## Rolling context\n" + (store.read_context() or "(empty)"),
        f"## Conversation {yesterday}\n" + (store.read_history(yesterday) or "(none)"),
        f"## Conversation {today} so far\n" + (store.read_history(today) or "(none)"),
        "## Jobs finished since last morning\n" + ("\n".join(finished) or "(none)"),
        "## Task list changes since last morning\n" + ("\n".join(events) or "(none)"),
        "## Aims and tasks now\n" + render(store.agenda())])


def _sleep_until(moment: datetime) -> None:
    delay = (moment - datetime.now()).total_seconds()
    if delay > 0:
        time.sleep(delay)
