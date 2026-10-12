# Deploy

The bot runs on the host as systemd `--user` units: its agents need the desktop, your Chrome, your MCP servers
and `~/dev`, which a container would hide. Docker is for tests only (`docker compose run --rm test`).

## Install (first time, or after switching from v2)

    # stop and remove the v2 timers
    systemctl --user disable --now mentor-work.timer mentor-deadline.timer mentor-replan.timer mentor-compact.timer
    rm ~/.config/systemd/user/mentor-{work,deadline,replan,compact}.{service,timer}
    rm -r ~/.config/systemd/user/mentor-work.service.d

    cp deploy/mentor.service deploy/mentor-morning.{service,timer} ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now mentor.service mentor-morning.timer

`loginctl enable-linger $USER` keeps them running without a login session.

## What runs

- `mentor.service`: `mentor serve`. Telegram long-poll, the chat agent (one `codex exec`/`resume` per turn),
  and a job watcher that every 2 s launches queued jobs, reaps dead ones and reports finished ones.
- Each job is a detached `mentor job-run <id>` in its own session. `KillMode=process` keeps running jobs
  alive across a service restart; the restarted service still reports them.
- `mentor-morning.timer`: 07:30 `mentor morning`. It summarizes yesterday, rewrites `data/context.md`, ranks
  the tasks, waits until 08:00, posts the priorities and starts a fresh chat session.

Logs: `journalctl --user -u mentor -u mentor-morning`; per job `data/jobs/<id>/{run.log,steps.log}`.

## Environment (`.env`)

`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DATA_DIR`, `TZ`, and a full `PATH` (systemd user services do not
get the nvm bin dir, and MCP servers started through `npx` need Node 24). Optional: `KROKI_URL`,
`CODEX_BIN` / `CLAUDE_BIN` (other CLI binaries; also how the usage-limit fallback is tested with a stub).

## Codex sandbox on Ubuntu 24.04

Ubuntu blocks unprivileged user namespaces, so Codex's bubblewrap sandbox cannot start. Grant the
capability to bubblewrap only:

    sudo cp deploy/apparmor-bwrap /etc/apparmor.d/bwrap
    sudo apparmor_parser -r /etc/apparmor.d/bwrap
