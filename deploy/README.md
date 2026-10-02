# Deploy

## Option A: cron

    crontab deploy/crontab

## Option B: systemd --user

    cp deploy/mentor.service deploy/mentor-{morning,deadline,replan,compact,work}.{service,timer} \
      ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now mentor.service \
      mentor-morning.timer mentor-deadline.timer mentor-replan.timer mentor-compact.timer mentor-work.timer

`mentor-work.timer` runs `mentor job work` hourly as a safety net. The bot also starts the worker
itself after button presses, `work`, `add_task` and `task_update` chat actions, replan and the morning job;
only one worker runs at a time (`data/.work.lock`); a second start waits for the lock and then drains
whatever is queued. `/cancel` in chat sends SIGTERM to the running worker, which kills only the brain
run in progress.

`mentor.service` uses `KillMode=process`: a restart stops only `mentor serve` (it waits up to
`TimeoutStopSec=300` for in-flight messages), while a running executor survives and keeps the old
code until it exits (a SIGTERM to the executor means cancel, which is why systemd must not signal it). The new `serve` kicks the executor on startup to drain leftover jobs.

Worker logs: a worker started by the bot writes to `data/work.log`; a run from the timer goes to
the journal (`journalctl --user -u mentor-work`); cron appends to `data/jobs.log`.

### PATH for `npx` (browser access)

With `BROWSER_CDP_URL` set, the worker starts the Playwright MCP server through `npx`. A systemd
user service does not get the nvm bin directory, so `npx` is not found. Set `PATH` in `.env`
(for example `PATH=/home/you/.nvm/versions/node/<version>/bin:/usr/local/bin:/usr/bin:/bin`) or
with `Environment=PATH=...` in `mentor.service` and `mentor-work.service`. The bot's own
`mentor.service` needs it too, because workers it kicks inherit its environment. Chrome must be
running with remote debugging on the port in `BROWSER_CDP_URL`.

## Option C: Docker

    docker compose build
    docker compose up -d
    docker compose exec mentor mentor doctor

## Codex sandbox on Ubuntu 24.04

Ubuntu blocks unprivileged user namespaces, so Codex's bubblewrap sandbox cannot start and
shell commands inside `codex exec` fail. Grant the capability to bubblewrap only (safer than
turning the global restriction off):

    sudo cp deploy/apparmor-bwrap /etc/apparmor.d/bwrap
    sudo apparmor_parser -r /etc/apparmor.d/bwrap

Verify: `codex exec --ignore-user-config -s read-only -- "run: ls" </dev/null` no longer warns
about bubblewrap. `loginctl enable-linger $USER` keeps the timers running without a login session.
