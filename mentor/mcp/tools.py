"""The deterministic tools agents get, by role. Each tool: (description, JSON schema, handler(args) -> text)."""

from dataclasses import dataclass
from datetime import date
from typing import Callable

from mentor.domain.tasks import render
from mentor.usecases import add_project, jobs, recall, send_image


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict
    handler: Callable[[dict], str]


def _obj(required=(), **props) -> dict:
    return {"type": "object", "properties": {k: {"type": v[0], "description": v[1]} for k, v in props.items()},
            "required": list(required)}


_STR = "string"
_TASK_FIELDS = dict(title=(_STR, "short imperative title"), aim=(_STR, "aim id like a2, or empty"),
                    deadline=(_STR, "ISO date YYYY-MM-DD, or empty"), notes=(_STR, "free text"),
                    project=(_STR, "project slug from projects_list; empty = the aim's project"))
_AIM_FIELDS = ("title", "why", "target", "status", "project")


def build(role: str, store, book, renderer=None, chat=None) -> list[Tool]:
    by = role

    def change(op, args, fn):
        if args.get("project") and args["project"] not in {p.name for p in store.projects()}:
            raise ValueError(f"unknown project {args['project']!r}; see projects_list or add_project")
        return store.change_agenda(op, args, by, fn)

    tasks_list = Tool("tasks_list", "Aims and open tasks in priority order, plus done/disabled counts.",
                      _obj(project=(_STR, "only this project's aims and tasks")),
                      lambda a: render(store.agenda(), a.get("project", "")) + _closed(store.agenda()))
    projects_list = Tool("projects_list", "Known projects and their repo paths.", _obj(),
                         lambda a: "\n".join(f"- {p.name}: {p.repo_path or '(no repo)'}" for p in store.projects())
                         or "(no projects)")
    reorder = Tool("tasks_reorder", "Set priorities: task ids top first. Unlisted tasks lose their rank.",
                   {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}}},
                    "required": ["ids"]},
                   lambda a: (change("reorder", a, lambda g: g.reorder(a["ids"])), "reordered")[1])
    recall_tool = Tool("recall", "Past conversations and day summaries. Give a date (YYYY-MM-DD) or a search query.",
                       _obj(date=(_STR, "a past day"), query=(_STR, "words to search for")),
                       lambda a: recall.run(store, a.get("date", ""), a.get("query", "")))
    if role == "job":
        return [tasks_list, projects_list]
    if role == "morning":
        return [tasks_list, projects_list, reorder, recall_tool]

    return [
        tasks_list, projects_list, reorder, recall_tool,
        Tool("task_add", "Add a task the user asked for.", _obj(["title"], **_TASK_FIELDS),
             lambda a: "added " + _task_line(change("task_add", a, lambda g: g.add_task(**_pick(a, _TASK_FIELDS))))),
        Tool("task_update", "Change a task's title, aim, project, deadline or notes.", _obj(["id"], id=(_STR, "task id"),
                                                                                 **_TASK_FIELDS),
             lambda a: "updated " + _task_line(change("task_update", a, lambda g: g.update_task(
                 a["id"], **_pick(a, _TASK_FIELDS))))),
        Tool("task_set_status", "Pause, resume (active), disable, finish (done) or remove a task.",
             {"type": "object", "properties": {"id": {"type": "string"}, "status": {
                 "type": "string", "enum": ["active", "paused", "disabled", "done", "removed"]}},
              "required": ["id", "status"]},
             lambda a: "now " + _task_line(change("task_set_status", a,
                                                  lambda g: g.update_task(a["id"], status=a["status"])))),
        Tool("aim_add", "Add an aim (a goal the user wants to achieve).",
             _obj(["title"], title=(_STR, "the aim"), why=(_STR, "why it matters"), target=(_STR, "ISO date"),
                                  project=(_STR, "project slug from projects_list, or empty")),
             lambda a: "added aim " + change("aim_add", a, lambda g: g.add_aim(
                 **_pick(a, ("title", "why", "target", "project")))).id),
        Tool("aim_update", "Change an aim's title, why, target date, status (active, paused, done) or project.",
             _obj(["id"], id=(_STR, "aim id"), title=(_STR, ""), why=(_STR, ""), target=(_STR, "ISO date"),
                  status=(_STR, "active | paused | done"), project=(_STR, "project slug")),
             lambda a: "updated aim " + change("aim_update", a, lambda g: g.update_aim(
                 a["id"], **_pick(a, _AIM_FIELDS))).id),
        Tool("job_start", "Hand a piece of work to a background orchestrator agent. Returns the job id at once.",
             _obj(["title", "brief"], title=(_STR, "a few words"),
                  brief=(_STR, "everything the agent needs: the user's request in their words, context, "
                               "project/repo paths, what done looks like")),
             lambda a: jobs.start(book, a["title"], a["brief"])),
        Tool("job_list", "Recent jobs and their status.", _obj(), lambda a: jobs.listing(book)),
        Tool("job_status", "One job's status and result.", _obj(["id"], id=(_STR, "job id")),
             lambda a: jobs.describe(book, a["id"])),
        Tool("job_cancel", "Stop a running job.", _obj(["id"], id=(_STR, "job id")),
             lambda a: jobs.cancel(book, a["id"])),
        Tool("add_project", "Register a project folder so jobs know its repo path.",
             _obj(["name"], name=(_STR, "slug"), repo_path=(_STR, "absolute path")),
             lambda a: add_project.run(store, a)),
        Tool("send_image", "Draw a Mermaid diagram and post it to the chat as a picture.",
             _obj(["diagram"], diagram=(_STR, "Mermaid source"), caption=(_STR, "")),
             lambda a: send_image.run(renderer, chat, a)),
    ]


def _pick(args: dict, keys) -> dict:
    return {k: args[k] for k in keys if k in args and args[k] is not None}


def _task_line(task) -> str:
    return (f"{task.id} [{task.status}] {task.title}" + (f" ({task.project})" if task.project else "")
            + (f" due {task.deadline}" if task.deadline else ""))


def _closed(agenda) -> str:
    today = date.today().strftime("%A %Y-%m-%d")
    counts = {s: sum(t.status == s for t in agenda.tasks) for s in ("done", "disabled")}
    return f"\n(done: {counts['done']}, disabled: {counts['disabled']}; today is {today})"
