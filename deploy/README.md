# Deploy

## Option A: cron

    crontab deploy/crontab

## Option B: systemd --user

    cp deploy/mentor.service deploy/mentor-{morning,deadline,replan,compact,work}.{service,timer} \
      ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now mentor.service \
      mentor-morning.timer mentor-deadline.timer mentor-replan.timer mentor-compact.timer mentor-work.timer

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
