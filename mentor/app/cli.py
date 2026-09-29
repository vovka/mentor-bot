"""mentor CLI: serve | job {morning,replan,compact} | doctor."""

import argparse
import subprocess
import sys
import time

from mentor.app.config import Config
from mentor.app.container import build
from mentor.usecases import handle_update


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mentor")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--with-scheduler", action="store_true")
    job = sub.add_parser("job")
    job.add_argument("name", choices=["morning", "replan", "compact"])
    job.add_argument("--dry-run", action="store_true")
    sub.add_parser("doctor")
    return parser


def _start_scheduler(container) -> None:
    import threading

    from mentor.adapters.scheduler.inprocess import Scheduler, load_schedule
    from mentor.app import jobs

    schedule = load_schedule(container.store.data_dir)
    scheduler = Scheduler(container.clock, schedule, jobs.run)
    threading.Thread(target=scheduler.run_forever, daemon=True).start()


def _serve(with_scheduler: bool = False) -> None:
    container = build(Config.from_env())
    if with_scheduler:
        _start_scheduler(container)
    offset = container.store.read_state().get("last_update_id", 0) + 1
    while True:
        try:
            for update in container.chat.poll(offset):
                handle_update.run(
                    container.store, container.brain, container.chat, container.clock, update
                )
                offset = update.update_id + 1
        except KeyboardInterrupt:
            return
        except Exception as exc:  # long-poll loop must survive transient errors
            print(f"serve error: {exc}", file=sys.stderr)
            time.sleep(1)


def _doctor() -> None:
    container = build(Config.from_env())
    container.chat.send("doctor: ok")
    result = subprocess.run(
        [
            "codex", "exec", "-s", "read-only", "--ignore-user-config",
            "-m", "gpt-5.5", "-c", "model_reasoning_effort=low",
            "--skip-git-repo-check", "--", "reply with exactly: ok",
        ],
        stdin=subprocess.DEVNULL,  # codex exec blocks on an open stdin
        capture_output=True,
        text=True,
        timeout=180,
    )
    print("telegram: sent 'doctor: ok'")
    print(f"codex exec: {result.stdout.strip() or result.stderr.strip()}")


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "doctor":
        _doctor()
    elif args.command == "serve":
        _serve(with_scheduler=args.with_scheduler)
    elif args.command == "job":
        from mentor.app import jobs

        print(jobs.run(args.name, dry_run=args.dry_run))
    else:
        print("not implemented")


if __name__ == "__main__":
    main()
