from dataclasses import dataclass


@dataclass(frozen=True)
class Project:
    name: str
    path: str
    repo_path: str
