# Deploy

## Option A: cron

    crontab deploy/crontab

## Option B: systemd --user

    cp deploy/mentor.service deploy/mentor-{morning,replan,compact}.{service,timer} \
      ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now mentor.service \
      mentor-morning.timer mentor-replan.timer mentor-compact.timer

## Option C: Docker

Not yet — see Phase 5 in docs/PLAN.md.
