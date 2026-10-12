import os

from mentor.adapters.agent.secrets import deny_paths


def test_finds_home_secrets_and_dev_files_and_resolves_symlinks(tmp_path):
    home, dev = tmp_path / "home", tmp_path / "home" / "dev"
    (home / ".ssh").mkdir(parents=True)
    (dev / "app" / "node_modules").mkdir(parents=True)
    (dev / "app" / ".env").write_text("X=1")
    (dev / "app" / ".env.example").write_text("X=")
    (dev / "app" / "node_modules" / ".env").write_text("X=1")
    (dev / "app" / "tls.key").write_text("k")
    os.symlink(dev / "app" / ".env", dev / ".env")
    found = deny_paths(home, scan=(dev,))
    assert found == sorted({str(home / ".ssh"), str(dev / "app" / ".env"), str(dev / "app" / "tls.key")})


def test_scrub_env():
    from mentor.adapters.agent.secrets import scrub_env
    env = {"PATH": "/bin", "TELEGRAM_BOT_TOKEN": "x", "SSH_AUTH_SOCK": "/s", "OPENAI_API_KEY": "k", "HOME": "/h"}
    scrub_env(env)
    assert env == {"PATH": "/bin", "HOME": "/h", "GIT_SSH_COMMAND": "false", "GIT_TERMINAL_PROMPT": "0"}
