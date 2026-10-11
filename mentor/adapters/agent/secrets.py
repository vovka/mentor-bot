"""Paths job agents must never read: credentials in the home dir plus secret-looking files under ~/dev.

Codex's own deny-read globs fail on unreadable folders under ~/dev, so files are found here and denied by exact path.
"""

import os
from pathlib import Path

HOME_SECRETS = (".ssh", ".gnupg", ".aws", ".kube", ".docker/config.json", ".netrc", ".git-credentials",
                ".config/gh", ".config/gcloud", ".config/rclone", ".npmrc", ".pypirc", ".password-store",
                ".local/share/keyrings", ".codex/auth.json", ".claude/.credentials.json", ".claude.json",
                ".config/google-chrome", ".config/google-chrome-for-testing", ".config/google-chrome-headless",
                ".config/chromium", ".config/BraveSoftware", "snap/chromium", ".mozilla")
_NAMES = (".env", ".secrets", "credentials.json", "token.json", "id_rsa", "id_ed25519")
_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".cache"}
_MAX_DEPTH = 6


def deny_paths(home: Path = Path.home(), scan: tuple[Path, ...] | None = None) -> list[str]:
    found = [str(home / p) for p in HOME_SECRETS if (home / p).exists()]
    for root in scan if scan is not None else (home / "dev",):
        found += _scan(root)
    return sorted(set(found))


def _scan(root: Path) -> list[str]:
    hits = []
    base_depth = len(root.parts)
    for folder, dirs, files in os.walk(root, onerror=lambda e: None):
        if len(Path(folder).parts) - base_depth >= _MAX_DEPTH:
            dirs.clear()
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        hits += [os.path.join(folder, d) for d in dirs if d == ".secrets"]
        hits += [os.path.join(folder, f) for f in files if _secret(f)]
    # codex refuses to deny a symlink ("crosses writable symlink"): deny its target instead
    return [os.path.realpath(h) for h in hits]


def _secret(name: str) -> bool:
    if name.startswith(".env"):
        return not name.endswith((".example", ".sample", ".template"))
    return name in _NAMES or name.endswith(_SUFFIXES)


_SECRET_ENV = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "PRIVATE_KEY")


def scrub_env(env) -> None:
    """For the job runner process and everything it starts: no tokens, no SSH agent, no git over ssh."""
    for name in list(env):
        if name == "SSH_AUTH_SOCK" or any(word in name.upper() for word in _SECRET_ENV):
            del env[name]
    env["GIT_SSH_COMMAND"] = "false"
    env["GIT_TERMINAL_PROMPT"] = "0"
