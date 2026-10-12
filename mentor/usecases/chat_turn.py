"""One chat turn: send a batch of incoming lines to today's agent session and post its reply.

The session lives until the morning job clears it. A usage limit moves the rest of the day to the fallback provider,
which starts a new session seeded with today's transcript; so does a session that can no longer be resumed.
"""

from datetime import datetime
from pathlib import Path

from mentor.domain.agent import AgentRun
from mentor.domain.settings import tier
from mentor.domain.tasks import render

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "chat.md"


class ChatTurn:
    def __init__(self, store, agents, cwd: str):
        self.store, self.agents, self.cwd = store, agents, cwd

    def run(self, lines: list[str]) -> str:
        """`lines` are already in the transcript. Returns the reply text, or an error note."""
        chat = self.store.read_state().get("chat", {})
        settings = self.store.read_settings()
        name = chat.get("tier", "chat")
        result = self._turn(name, settings, chat.get("session", ""), lines)
        if result.error and not result.limited and chat.get("session"):  # stale session: start over from the transcript
            result = self._turn(name, settings, "", lines)
        if result.limited and name == "chat":
            name = "chat_fallback"
            result = self._turn(name, settings, "", lines)
        self.store.update_state(chat={"tier": name, "session": result.session if result.ok else ""})
        return result.text if result.ok else f"⚠️ chat agent failed: {result.error[:300]}"

    def _turn(self, name: str, settings: dict, session: str, lines: list[str]):
        prompt = ("\n".join(lines) if session else self.seed(lines)) + language_hint(lines)
        return self.agents.run(AgentRun(prompt, tier(settings, name), self.cwd, role="chat", session=session))

    def seed(self, lines: list[str]) -> str:
        """The first prompt of a session: instructions, today, memory, tasks, today's transcript so far."""
        today = datetime.now().strftime("%A %Y-%m-%d %H:%M")
        earlier = self.store.read_history(datetime.now().date()).splitlines()[: -len(lines) or None]
        parts = [PROMPT.read_text(), f"Now: {today}",
                 "## Context (rolling memory)\n" + (self.store.read_context() or "(empty)"),
                 "## Aims and tasks\n" + render(self.store.agenda())]
        if earlier:
            parts.append("## Earlier today\n" + "\n".join(earlier[-200:]))
        parts.append("## New messages\n" + "\n".join(lines))
        return "\n\n".join(parts)


def language_hint(lines: list[str]) -> str:
    """luna drifts into Russian after tool calls; pin the reply language every turn. The user never wants Russian."""
    said = [line.split(" you: ", 1)[1] for line in lines if " you: " in line]
    letters = [c for c in (said[-1] if said else "") if c.isalpha()]
    if not letters:
        return "\n(Reply in English unless the user wrote Ukrainian. Never Russian.)"
    if sum(c.isascii() for c in letters) / len(letters) > 0.8:
        return "\n(Reply in English.)"
    return "\n(Reply in Ukrainian. Never Russian.)"
