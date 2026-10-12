"""One agent turn: what to run and what came back. Adapters turn these into codex / claude CLI calls."""

from dataclasses import dataclass, field
from typing import Callable

from mentor.domain.settings import Tier


@dataclass(frozen=True)
class Sandbox:
    """Read-only unless `writable` lists roots; `deny_read` paths are hidden from shell commands."""
    writable: tuple[str, ...] = ()
    deny_read: tuple[str, ...] = ()


@dataclass
class AgentRun:
    prompt: str
    tier: Tier
    cwd: str
    role: str  # the mentor MCP tool set: chat | job | morning
    session: str = ""  # resume this session; empty = start a new one
    sandbox: Sandbox = field(default_factory=Sandbox)
    user_tools: bool = False  # the user's own CLI config: MCP servers, skills, plugins
    on_step: Callable[[str], None] | None = None


@dataclass(frozen=True)
class AgentResult:
    text: str
    session: str = ""
    error: str = ""
    limited: bool = False  # the provider refused because a usage limit is hit: retry elsewhere

    @property
    def ok(self) -> bool:
        return not self.error
