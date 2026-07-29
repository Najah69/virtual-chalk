from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Callable, Optional

import webview

from app.render.capture import FPS, FrameCapture
from app.render.ffmpeg_wrapper import encode_scene
from app.scenes.schema import Project, Scene

ProgressCallback = Optional[Callable[[str, float], None]]


def _hash_scene(scene: Scene) -> str:
    payload = f"{scene.voice_over}|{scene.duration_sec}|{[s.__dict__ for s in scene.strokes]}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_scene(project: Project, scene_id: str) -> Path:
    scene = next(s for s in project.scenes if s.scene_id == scene_id)
    window = webview.windows[0]
    capture = FrameCapture(window)
    frames_dir = capture.render_scene_frames(scene, project.theme)
    out_path = Path(tempfile.mktemp(suffix=".mp4"))
    encode_scene(frames_dir, Path(scene.audio_path), FPS, out_path)
    scene.content_hash = _hash_scene(scene)
    return out_path


def render_all(project: Project, on_progress: ProgressCallback = None) -> list[Path]:
    """Ne re-rend que les scènes dont le contenu a changé depuis le dernier
    rendu (comparaison de content_hash) — économise temps et calcul."""
    paths = []
    total = len(project.scenes)
    for i, scene in enumerate(project.scenes):
        current_hash = _hash_scene(scene)
        if scene.content_hash != current_hash:
            paths.append(render_scene(project, scene.scene_id))
        if on_progress:
            on_progress("render", (i + 1) / total)
    return paths
