"""Apply one worker result to tasks.json, then hand the outcome to the human in Telegram."""

import imaplib
from pathlib import Path

from mentor.adapters.store.lock import locked
from mentor.usecases.progress import CANCELLED
from mentor.usecases.work_brain import other_provider

_MAX_UPLOAD = 50 * 1024 * 1024
_STATUS = {"done": "done", "needs_approval": "awaiting_approval", "needs_user": "awaiting_user", "failed": "failed"}


def outcome_of(result) -> dict:
    """The task_result args; a missing action (e.g. a brain error) is a failure with the reply as reason."""
    action = next((a for a in result.actions if a.kind == "task_result"), None)
    args = dict(action.args) if action else {}
    if args.get("outcome") not in _STATUS:
        args["outcome"] = "failed"
    return args


def apply(store, task_id: str, args: dict):
    """Store the outcome under the lock; returns the updated task, or None if it is no longer ours."""
    with locked(store.data_dir):
        all_tasks = store.read_tasks()
        task = next((t for t in all_tasks if t.id == task_id), None)
        if task is None or task.status != "running":
            return None  # dropped, finished or replanned away while the brain was working
        task.status = _STATUS[args["outcome"]]
        task.files = args.get("files") or task.files
        task.proposal = args.get("proposal") or task.proposal
        task.approved = False  # an approval covers one run; a retry or a new proposal needs its own
        store.write_tasks(all_tasks)
        return task


def notify(store, chat, mail, task, args: dict, reply: str, wdir: Path, repo: str, progress) -> None:
    """Finalize the progress message with the outcome and brief; buttons, files and drafts follow it."""
    outcome = args["outcome"]
    store.append_history(f"work: {task.title} [{outcome}]: {reply}")
    if outcome in ("done", "needs_user"):
        _hand_off(chat, mail, task, args, reply, wdir, repo, progress)
        return
    progress.finish("cancelled" if reply.startswith(CANCELLED) else outcome, reply)
    if outcome == "needs_approval":
        chat.send(f"Approve? {task.title}\n\n{task.proposal}", buttons=_approval_buttons(store, task))


def _hand_off(chat, mail, task, args: dict, reply: str, wdir: Path, repo: str, progress) -> None:
    """Report, deliverables and email drafts; a task that still needs the human ends with a Done button."""
    (wdir / "report.md").write_text(reply)
    listed = "\n".join(f"- {Path(f).name}" for f in task.files if Path(f).name != "report.md")
    progress.finish(args["outcome"], reply, f"\n\nFiles (ask me to send any):\n{listed}" if listed else "")
    for path in args.get("send") or []:  # only what the human must upload or attach somewhere
        send_file(chat, path, wdir, repo)
    for draft in args.get("drafts") or []:
        chat.send(_save_draft(mail, draft))
    if args["outcome"] == "needs_user":
        chat.send(f"Your turn: {task.title}\n\n{args.get('user_action') or reply}", buttons=done_button(task))


def _save_draft(mail, draft: dict) -> str:
    """Save to the mailbox's Drafts when mail is configured; otherwise (or on failure) hand over the text."""
    head = f"to: {draft['to']}\nsubject: {draft['subject']}"
    if mail is None:
        return f"Email draft\n{head}\n\n{draft['body']}"
    try:
        mail.draft(draft["to"], draft["subject"], draft["body"])
    except (imaplib.IMAP4.error, OSError) as error:
        return f"Email draft (not saved: {error})\n{head}\n\n{draft['body']}"
    return f"Email draft saved in Drafts\n{head}"


def done_button(task) -> list[tuple[str, str]]:
    return [("Done", f"t:{task.id}:done")]


def _approval_buttons(store, task) -> list[tuple[str, str]]:
    other = other_provider(store.read_settings(), task)
    alt = [(f"Approve · {other}", f"t:{task.id}:alt")] if other else []
    return [("Approve", f"t:{task.id}:ok"), *alt, ("Reject", f"t:{task.id}:no")]


def send_file(chat, name: str, wdir: Path, repo: str) -> bool:
    path = (wdir / name).resolve()
    roots = [wdir.resolve(), *([Path(repo).resolve()] if repo else [])]
    root = next((r for r in roots if path.is_relative_to(r)), None)
    if root is None or not path.is_file() or any(p.startswith(".") for p in path.relative_to(root).parts):
        return False  # outside the work dir and repo, or a dotfile such as .env or .git/*
    if path.stat().st_size > _MAX_UPLOAD:
        chat.send(f"Too big for Telegram: {path}")
        return True
    chat.send_document(path.read_bytes(), path.name)
    return True
