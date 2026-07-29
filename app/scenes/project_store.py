from __future__ import annotations

import json
from pathlib import Path

from app.scenes.schema import Project


def dumps(project: Project) -> str:
    return json.dumps(project.to_dict(), indent=2, ensure_ascii=False)

def loads(raw: str) -> Project:
    return Project.from_dict(json.loads(raw))

def write_json(project: Project, path: Path) -> None:
    path.write_text(dumps(project), encoding="utf-8")

def read_json(path: Path) -> Project:
    return loads(path.read_text(encoding="utf-8"))
