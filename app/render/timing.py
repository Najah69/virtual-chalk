from __future__ import annotations

from app.scenes.schema import Scene


def _path_length(points) -> float:
    length = 0.0
    for a, b in zip(points, points[1:]):
        length += ((b.x - a.x) ** 2 + (b.y - a.y) ** 2) ** 0.5
    return max(length, 1.0)


def compute_stroke_timings(scene: Scene) -> None:
    """Répartit la durée de la scène entre ses tracés, proportionnellement à
    leur longueur, dessinés séquentiellement (comme un vrai geste
    d'écriture) plutôt que tous en même temps. Calculé côté Python pour
    rester la source de vérité unique (le JS se contente de lire
    start_sec/end_sec, il ne recalcule rien)."""
    strokes = scene.strokes
    if not strokes:
        return
    weights = [_path_length(s.points) for s in strokes]
    total = sum(weights) or 1.0
    cursor = 0.0
    for stroke, weight in zip(strokes, weights):
        span = (weight / total) * scene.duration_sec
        stroke.start_sec = cursor
        stroke.end_sec = cursor + span
        cursor += span
