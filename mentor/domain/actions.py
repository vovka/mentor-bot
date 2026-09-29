"""Brain call contract: what we send, what we get back."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mentor.domain.settings import BrainSettings

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "output_schema.json"
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


@dataclass(frozen=True)
class BrainResult:
    reply: str
    actions: list[Action]
    raw: dict[str, Any]
