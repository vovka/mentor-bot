"""Brain call contract: what we send, what we get back."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mentor.domain.settings import BrainSettings

# Relative to cwd, like the brain adapters' own schema_path (repo root in dev, /app in Docker).
_SCHEMA_PATH = Path("prompts/output_schema.json")
OUTPUT_SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())


@dataclass(frozen=True)
class Action:
    """One thing the brain asked us to do, e.g. replan/scout/set_settings/add_project."""

    kind: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrainTask:
    prompt: str
    cwd: str
    write: bool
    settings: BrainSettings
    timeout: int | None = None
    extra_dirs: tuple[str, ...] = ()  # more dirs the brain may write to when write=True


@dataclass(frozen=True)
class BrainResult:
    reply: str
    actions: list[Action]
    raw: dict[str, Any]
    document: str | None = None
