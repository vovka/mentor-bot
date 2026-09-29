"""add_project use case: validate a project slug and repo path, then create it."""

import re
from typing import Any

_SLUG_RE = re.compile(r"^[a-z0-9_-]+$")


def run(store, args: dict[str, Any]) -> str:
    name = args.get("name", "")
    repo_path = args.get("repo_path", "")

    if not _SLUG_RE.match(name):
        return f"invalid project name {name!r}; use lowercase letters, digits, _ or -"
    if not repo_path:
        return "repo_path is required"

    store.add_project(name, repo_path)
    return f"Project {name!r} added at {repo_path}"
