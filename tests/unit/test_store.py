from datetime import date

from mentor.adapters.store.files import DEFAULT_SETTINGS, FileStore
from mentor.domain.settings import validate


def test_settings_round_trip_and_default_creation(tmp_path):
    store = FileStore(tmp_path)

    assert store.read_settings() == DEFAULT_SETTINGS
    assert (tmp_path / "settings.json").exists()

    store.write_settings(validate("claude", "opus", "medium"))
    reloaded = store.read_settings()
    assert reloaded["provider"] == "claude"
    assert reloaded["model"] == "opus"
    assert reloaded["heavy"] == DEFAULT_SETTINGS["heavy"]


def test_state_round_trip(tmp_path):
    store = FileStore(tmp_path)

    assert store.read_state() == {}
    store.write_state({"last_brief_date": "2026-09-29"})
    assert store.read_state() == {"last_brief_date": "2026-09-29"}


def test_history_append_and_list(tmp_path):
    store = FileStore(tmp_path)

    store.append_history("first line")
    store.append_history("second line")

    today = date.today()
    assert store.list_history_days() == [today]
    assert "first line" in store.read_history(today)
    assert "second line" in store.read_history(today)


def test_projects_discovery_skips_template(tmp_path):
    store = FileStore(tmp_path)
    for name in ("_template", "tusk", "campaignloop"):
        project_dir = tmp_path / "projects" / name
        project_dir.mkdir(parents=True)
        (project_dir / "project.md").write_text(f"# {name}\nrepo: /home/vova/dev/{name}\n")

    names = [p.name for p in store.projects()]
    assert names == ["campaignloop", "tusk"]
    tusk = next(p for p in store.projects() if p.name == "tusk")
    assert tusk.repo_path == "/home/vova/dev/tusk"


def test_add_project_creates_three_files(tmp_path):
    store = FileStore(tmp_path)
    template_dir = tmp_path / "projects" / "_template"
    template_dir.mkdir(parents=True)
    (template_dir / "project.md").write_text("# <name>\nrepo: <path>\n")
    (template_dir / "timeline.md").write_text("# <name> timeline\n")
    (template_dir / "plan.md").write_text("# <name> plan\n")

    store.add_project("jobpilot", "/home/vova/dev/jobpilot")

    project_dir = tmp_path / "projects" / "jobpilot"
    assert (project_dir / "project.md").exists()
    assert (project_dir / "timeline.md").exists()
    assert (project_dir / "plan.md").exists()
    assert "jobpilot" in (project_dir / "project.md").read_text()
    assert "/home/vova/dev/jobpilot" in (project_dir / "project.md").read_text()
