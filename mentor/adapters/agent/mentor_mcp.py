"""How a CLI agent launches the mentor MCP server (`mentor mcp --role <role>`) as its stdio child."""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def mentor_server(role: str) -> tuple[str, list[str], str, dict]:
    """(command, args, cwd, env). The CLI passes few env vars to MCP children, so the data dir goes explicitly."""
    env = {"DATA_DIR": str(Path(os.environ.get("DATA_DIR", REPO / "data")).resolve()),
           "TZ": os.environ.get("TZ", "Europe/Kyiv")}
    return sys.executable, ["-m", "mentor.app.cli", "mcp", "--role", role], str(REPO), env
