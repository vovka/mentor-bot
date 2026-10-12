"""One-off: distill the v2 task graph into aims + tasks. `propose` writes a draft and sends it; `apply` installs it."""

import json
import shutil
from pathlib import Path

from mentor.domain.tasks import Agenda, render
from mentor.usecases.oneshot import ask_json

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "migrate.md"


def run(step: str, store, chat, agents, cwd: str) -> str:
    draft = store.data_dir / "migration" / "tasks.json"
    if step == "propose":
        return propose(store, chat, agents, cwd, draft)
    agenda = Agenda.from_dict(json.loads(draft.read_text()))
    store.change_agenda("migrate", {"aims": len(agenda.aims), "tasks": len(agenda.tasks)}, "user",
                        lambda g: (setattr(g, "aims", agenda.aims), setattr(g, "tasks", agenda.tasks)))
    return f"installed {len(agenda.aims)} aims and {len(agenda.tasks)} tasks"


def propose(store, chat, agents, cwd: str, draft: Path) -> str:
    legacy = store.data_dir / "legacy" / "tasks-v2.json"
    current = store.data_dir / "tasks.json"
    if not legacy.exists():
        legacy.parent.mkdir(exist_ok=True)
        shutil.move(current, legacy)  # the v2 graph; tasks.json starts empty until `apply`
    prompt = PROMPT.read_text().replace("{LEGACY}", str(legacy)).replace("{DATA}", str(store.data_dir))
    answer = ask_json(agents, store.read_settings(), ("job", "job_fallback"), prompt, cwd, role="job")
    agenda = _validated(answer)
    draft.parent.mkdir(exist_ok=True)
    draft.write_text(json.dumps(agenda.to_dict(), indent=2, ensure_ascii=False))
    text = render(agenda) + "\n\nLeft out:\n" + answer.get("dropped", "")
    chat.send_document(text.encode(), "proposed-tasks.md", "Proposed aims and tasks from the old list")
    return f"draft: {draft}\n\n{text}"


def _validated(answer: dict) -> Agenda:
    """Rebuild through the domain operations so ids, aims and dates are checked."""
    agenda, ids = Agenda(), {}
    for aim in answer["aims"]:
        ids[aim["id"]] = agenda.add_aim(aim["title"], aim.get("why", ""), aim.get("target", ""),
                                        aim.get("project", "")).id
    for task in answer["tasks"]:
        agenda.add_task(task["title"], ids.get(task.get("aim", ""), ""), task.get("deadline", ""),
                        task.get("notes", ""), task.get("project", ""))
    return agenda
