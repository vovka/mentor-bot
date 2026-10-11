"""mentor CLI: serve | mcp --role R | job-run ID | morning [--now] | migrate {propose,apply} | doctor."""

import argparse
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from mentor.adapters.agent.mentor_mcp import REPO
from mentor.adapters.agent.secrets import deny_paths
from mentor.app.config import Config
from mentor.app.container import build
from mentor.usecases import job_announce, job_run, jobs
from mentor.usecases.chat_turn import ChatTurn
from mentor.usecases.gateway import Gateway

_JOB_POLL = 2  # seconds between job checks
_children: list[subprocess.Popen] = []  # job runners, polled so they do not linger as zombies


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mentor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("mcp").add_argument("--role", choices=["chat", "job", "morning"], required=True)
    sub.add_parser("job-run").add_argument("job_id")
    sub.add_parser("morning").add_argument("--now", action="store_true", help="post at once, not at 08:00")
    sub.add_parser("migrate").add_argument("step", choices=["propose", "apply"])
    sub.add_parser("doctor")
    args = parser.parse_args(argv)
    container = build(Config.from_env())
    if args.command == "serve":
        serve(container)
    elif args.command == "mcp":
        from mentor.mcp import server, tools
        server.serve(tools.build(args.role, container.store, container.book, container.renderer, container.chat))
    elif args.command == "job-run":
        job_run.run(args.job_id, container.store, container.book, container.agents, deny_paths())
    elif args.command == "morning":
        from mentor.usecases import morning
        morning.run(container.store, container.chat, container.agents, str(REPO), wait=not args.now)
    elif args.command == "migrate":
        from mentor.usecases import migrate
        print(migrate.run(args.step, container.store, container.chat, container.agents, str(REPO)))
    else:
        container.chat.send("doctor: ok")


def serve(container, stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
    roots = [Path(p).expanduser().resolve() for p in job_run.WRITABLE]
    gateway = Gateway(container.store, container.chat, ChatTurn(container.store, container.agents, str(REPO)),
                      lambda: job_announce.pending(container.book, container.chat, roots))
    threads = [threading.Thread(target=gateway.work, args=(stop,)),
               threading.Thread(target=watch_jobs, args=(container.book, gateway, stop))]
    for thread in threads:
        thread.start()
    poll_telegram(container, gateway, stop)
    for thread in threads:
        thread.join()


def watch_jobs(book, gateway, stop: threading.Event) -> None:
    while not stop.is_set():
        _children[:] = [p for p in _children if p.poll() is None]
        try:
            jobs.launch_queued(book, spawn_job)
            jobs.reap_dead(book)
            gateway.check_jobs()
        except Exception as exc:  # one bad job folder must not stop reporting the others
            print(f"job watch error: {exc}", file=sys.stderr)
        stop.wait(_JOB_POLL)


def poll_telegram(container, gateway, stop: threading.Event) -> None:
    offset = container.store.read_state().get("last_update_id", 0) + 1
    while not stop.is_set():
        try:
            for update in container.chat.poll(offset):
                offset = update.update_id + 1
                container.store.update_state(last_update_id=update.update_id)
                gateway.on_update(update)
        except Exception as exc:  # the long-poll loop must survive transient errors
            print(f"poll error: {exc}", file=sys.stderr)
            stop.wait(1)


def spawn_job(job_id: str) -> int:
    """Detached runner in its own session: survives a service restart and dies as a group on cancel."""
    with open(Path(os.environ["DATA_DIR"]) / "jobs" / job_id / "run.log", "a") as log:
        proc = subprocess.Popen([sys.executable, "-m", "mentor.app.cli", "job-run", job_id], cwd=REPO,
                                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    _children.append(proc)
    return proc.pid


if __name__ == "__main__":
    main()
