from __future__ import annotations

import zipfile
from pathlib import Path

from app.scenes.project_store import dumps, loads
from app.scenes.schema import Project

PROJECT_JSON_NAME = "project.json"


def save_project_file(project: Project, path: Path) -> None:
    """.golpoproj = zip {project.json, audio/*.wav} — le MP4 n'y est pas
    inclus, il est toujours régénérable à partir de ce fichier."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(PROJECT_JSON_NAME, dumps(project))
        for scene in project.scenes:
            if scene.audio_path and Path(scene.audio_path).exists():
                zf.write(scene.audio_path, f"audio/{scene.scene_id}.wav")


def load_project_file(path: Path) -> Project:
    with zipfile.ZipFile(path, "r") as zf:
        project = loads(zf.read(PROJECT_JSON_NAME).decode("utf-8"))
        extract_dir = path.with_suffix("")
        extract_dir.mkdir(exist_ok=True)
        for scene in project.scenes:
            member = f"audio/{scene.scene_id}.wav"
            if member in zf.namelist():
                target = extract_dir / f"{scene.scene_id}.wav"
                target.write_bytes(zf.read(member))
                scene.audio_path = str(target)
    return project
