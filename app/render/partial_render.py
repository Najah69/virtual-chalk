from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Optional

from app.render.capture import FPS, FrameCapture
from app.render.chalk_audio import build_chalk_track
from app.render.ffmpeg_wrapper import encode_scene
from app.render.theme_registry import tool_for_theme
from app.render.timing import compute_stroke_timings
from app.render.window_registry import get_render_window
from app.scenes.schema import Project, Scene

ProgressCallback = Optional[Callable[[str, float], None]]


def _hash_scene(scene: Scene) -> str:
    payload = (
        f"{scene.voice_over}|{scene.duration_sec}|{[s.__dict__ for s in scene.strokes]}"
        f"|{[m.__dict__ for m in scene.mascot_timeline]}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_scene(project: Project, scene_id: str, scenes_dir: Path) -> Path:
    """Rend UNE scène et l'écrit dans un emplacement stable
    (`scenes_dir/{scene_id}.mp4`) plutôt qu'un fichier temporaire jetable —
    nécessaire pour que `render_all`/`Pipeline.rerender_scene` puissent la
    réutiliser sans la re-rendre (cache), et pour que la vidéo finale
    reste reconstructible à tout moment à partir de ce qui existe
    réellement sur le disque. Rend INCONDITIONNELLEMENT (pas de vérification
    de hash ici — voir `render_all` pour la logique de cache).

    Lève ValueError (pas StopIteration) si scene_id n'existe pas dans
    project.scenes — un message explicite plutôt qu'une exception de bas
    niveau, utile si l'appelant transmet un id périmé (scène supprimée
    entre-temps)."""
    scene = project.find_scene(scene_id)
    if scene is None:
        raise ValueError(f"Scène introuvable : {scene_id!r}")
    compute_stroke_timings(scene)

    capture = FrameCapture(get_render_window())
    frames_dir = capture.render_scene_frames(scene, project.theme)

    chalk_audio_path = (
        build_chalk_track(scene) if tool_for_theme(project.theme) == "chalk" else None
    )

    scenes_dir.mkdir(parents=True, exist_ok=True)
    out_path = scenes_dir / f"{scene_id}.mp4"
    encode_scene(frames_dir, Path(scene.audio_path), FPS, out_path, chalk_audio_path=chalk_audio_path)
    scene.content_hash = _hash_scene(scene)
    return out_path


def render_all(project: Project, scenes_dir: Path, on_progress: ProgressCallback = None) -> list[Path]:
    """Ne re-rend que les scènes dont le contenu a changé depuis le dernier
    rendu (comparaison de content_hash), réutilise le clip en cache pour
    les autres — mais retourne TOUJOURS le chemin de TOUTES les scènes,
    dans l'ordre. Une version précédente ne retournait que les scènes
    changées, ce qui produisait un montage final incomplet (scènes
    inchangées silencieusement absentes) dès qu'un rendu partiel était
    recombiné après la génération initiale — voir Pipeline.rerender_scene,
    seul endroit où ce cas se produit réellement en pratique."""
    paths = []
    total = len(project.scenes)
    for i, scene in enumerate(project.scenes):
        current_hash = _hash_scene(scene)
        cached_path = scenes_dir / f"{scene.scene_id}.mp4"
        if scene.content_hash != current_hash or not cached_path.exists():
            paths.append(render_scene(project, scene.scene_id, scenes_dir))
        else:
            paths.append(cached_path)
        if on_progress:
            on_progress("render", (i + 1) / total)
    return paths
