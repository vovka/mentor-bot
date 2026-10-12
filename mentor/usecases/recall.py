"""recall: what was said or decided on a past day, or every line mentioning some words."""

from datetime import date

_MAX_LINES = 60


def run(store, day: str = "", query: str = "") -> str:
    if day:
        when = date.fromisoformat(day)
        summary, transcript = store.read_day(when), store.read_history(when)
        return (f"Summary of {day}:\n{summary or '(none)'}\n\nTranscript:\n{_tail(transcript)}"
                if summary or transcript else f"nothing recorded on {day}")
    words = query.lower().split()
    if not words:
        return "give a date or a query"
    hits = []
    for when in reversed(store.list_history_days()):
        for source in (store.read_day(when), store.read_history(when)):
            hits += [f"{when}: {line}" for line in source.splitlines() if all(w in line.lower() for w in words)]
    return "\n".join(hits[:_MAX_LINES]) or f"no mention of {query!r}"


def _tail(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-_MAX_LINES:])
