"""Build the worker's BrainTask for one task: work dir, cwd, brain tier and prompt."""

import os
from pathlib import Path

from mentor.domain.actions import BrainTask
from mentor.domain.settings import tier

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "work.md"
_BROWSER = (
    "use the `browser` MCP server (the user's logged-in Chrome). Read only: open your own new tab, "
    "close it when done, never touch, navigate or close any other tab, never submit or click anything that changes data."
)
_NO_BROWSER = "no browser is attached. If a page needs a login, return `needs_user` asking for its fields or a screenshot."


def _tiers(task) -> tuple[str, str]:
    return ("coder", "heavy") if task.kind in ("coding", "system") else ("heavy", "coder")


def settings_for(raw: dict, task):
    """The kind's own tier, or the other tier when `task.provider` names that tier's provider."""
    own, alt = (tier(raw, name) for name in _tiers(task))
    return alt if task.provider and task.provider == alt.provider != own.provider else own


def other_provider(raw: dict, task) -> str | None:
    """The provider of the tier this task would not run on, when it differs."""
    current = settings_for(raw, task).provider
    others = {tier(raw, name).provider for name in _tiers(task)} - {current}
    return others.pop() if others else None


def project_of(store, task):
    return next((p for p in store.projects() if p.name == task.project), None)


def repo_of(store, task) -> str:
    """The project's repo path when it exists on disk, else ""."""
    project = project_of(store, task)
    return project.repo_path if project and project.repo_path and Path(project.repo_path).is_dir() else ""


def dir_of(store, task) -> Path:
    base = store.data_dir / "projects" / task.project if project_of(store, task) else store.data_dir
    return base / "work" / task.id


def work_dir(store, task) -> Path:
    path = dir_of(store, task)
    path.mkdir(parents=True, exist_ok=True)
    return path


def build(store, clock, task, all_tasks) -> BrainTask:
    raw, project = store.read_settings(), project_of(store, task)
    wdir, repo = work_dir(store, task), repo_of(store, task)
    use_repo = task.kind == "coding" and repo
    return BrainTask(
        prompt=_prompt(store, clock, task, all_tasks, project, repo, wdir),
        cwd=repo if use_repo else str(wdir),
        write=True,
        settings=settings_for(raw, task),
        extra_dirs=(str(wdir),) if use_repo else (),
    )


def _prompt(store, clock, task, all_tasks, project, repo, wdir) -> str:
    return _PROMPT_PATH.read_text().format_map(
        {
            "today": clock.now().date().isoformat(),
            "id": task.id, "title": task.title, "kind": task.kind,
            "note": task.note or "(none)", "due": task.due or "(none)",
            "project": project.name if project else "(none)",
            "repo": repo or "(none)",
            "work_dir": str(wdir),
            "deps": "\n\n".join(_dep(store, t) for t in all_tasks if t.id in task.deps) or "(none)",
            "browser": _BROWSER if os.environ.get("BROWSER_CDP_URL") else _NO_BROWSER,
            "approval": f"APPROVED proposal — carry it out:\n{task.proposal}" if task.approved else "(none)",
        }
    )


def _dep(store, dep) -> str:
    report = dir_of(store, dep) / "report.md"
    files = ", ".join(dep.files) or "(none)"
    return f"- {dep.title} ({dep.id})\n  note: {dep.note or '(none)'}\n  files: {files}\n  report: {report}"
