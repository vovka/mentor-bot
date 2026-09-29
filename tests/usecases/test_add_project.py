from mentor.adapters.store.files import FileStore
from mentor.usecases import add_project


def test_missing_repo_path_dir_is_rejected(tmp_path):
    store = FileStore(tmp_path)
    out = add_project.run(store, {"name": "x", "repo_path": str(tmp_path / "nope")})
    assert "does not exist" in out
    assert not (tmp_path / "projects" / "x").exists()


def test_existing_repo_path_is_added(tmp_path):
    (tmp_path / "projects" / "_template").mkdir(parents=True)
    for f in ("project.md", "timeline.md", "plan.md"):
        (tmp_path / "projects" / "_template" / f).write_text("# <name>\nrepo: <path>\n")
    repo = tmp_path / "repo"; repo.mkdir()
    out = add_project.run(FileStore(tmp_path), {"name": "x", "repo_path": str(repo)})
    assert "added" in out
    assert (tmp_path / "projects" / "x" / "project.md").exists()
