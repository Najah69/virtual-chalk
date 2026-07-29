from __future__ import annotations

from app.scenes.schema import Scene


def generate_bookmarks(scenes: list[Scene]) -> list[dict]:
    """Un bookmark par scène (titre + timestamp), généré automatiquement
    pour qu'un utilisateur lambda obtienne une vidéo interactive utilisable
    sans configuration manuelle."""
    bookmarks = []
    t = 0.0
    for scene in scenes:
        label = scene.notes or scene.visual_instruction[:40] or scene.scene_id
        bookmarks.append({"time": round(t, 2), "label": label})
        t += scene.duration_sec
    return bookmarks
