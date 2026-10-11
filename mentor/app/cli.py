"""mentor CLI: serve | job {morning,deadline,replan,compact,work} | doctor."""

import argparse
import signal
import subprocess
import sys
import threading

from mentor.app.config import Config
from mentor.app.container import build
from mentor.app.kick import kick
from mentor.usecases import handle_update


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mentor")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--with-scheduler", action="store_true")
    job = sub.add_parser("job")
    job.add_argument("name", choices=["morning", "deadline", "replan", "compact", "work"])
    job.add_argument("--dry-run", action="store_true")
    sub.add_parser("doctor")
    return parser


def _start_scheduler(container) -> None:
    from mentor.adapters.scheduler.inprocess import Scheduler, load_schedule
    from mentor.app import jobs

    schedule = load_schedule(container.store.data_dir)
    scheduler = Scheduler(container.clock, schedule, jobs.run)
    threading.Thread(target=scheduler.run_forever, daemon=True).start()


def _serve(with_scheduler: bool = False) -> None:
    container = build(Config.from_env())
    if with_scheduler:
        _start_scheduler(container)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    kick()  # drain jobs and tasks left over from before a restart
    serve_loop(container, stop)


def serve_loop(container, stop: threading.Event, kick=kick) -> None:
    """Long-poll until `stop`; each update runs in its own thread so a slow answer never blocks the chat."""
    offset = container.store.read_state().get("last_update_id", 0) + 1
    threads: list[threading.Thread] = []
    while not stop.is_set():
        try:
            for update in container.chat.poll(offset):
                offset = update.update_id + 1
                threads = [t for t in threads if t.is_alive()] + dispatch(container, update, kick)
        except Exception as exc:  # long-poll loop must survive transient errors
            print(f"serve error: {exc}", file=sys.stderr)
            stop.wait(1)
    for thread in threads:
        thread.join()


def dispatch(container, update, kick=kick) -> list[threading.Thread]:
    """Dedup in poll order, then handle the update in a new non-daemon thread (shutdown waits for it)."""
    # ponytail: one unbounded thread per update; fine for one user, add a pool if updates ever flood in
    if not handle_update.claim(container.store, update):
        return []
    thread = threading.Thread(target=_handle, args=(container, update, kick))
    thread.start()
    return [thread]


def _handle(container, update, kick) -> None:
    try:
        handle_update.route(
            container.store, container.brain, container.chat, container.clock, update,
            renderer=container.renderer, kick=kick,
        )
    except Exception as exc:  # one failed update must not take the others down
        print(f"serve error: update {update.update_id}: {exc}", file=sys.stderr)


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
