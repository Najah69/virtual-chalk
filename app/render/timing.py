from __future__ import annotations

from app.scenes.schema import Scene


def _path_length(points) -> float:
    length = 0.0
    for a, b in zip(points, points[1:]):
        length += ((b.x - a.x) ** 2 + (b.y - a.y) ** 2) ** 0.5
    return max(length, 1.0)


def _stroke_weight(stroke) -> float:
    # Les tracés "texte" n'arrivent ici qu'avec un point d'ancrage — le
    # tracé réel (contour des lettres) n'est développé que côté JS, après
    # ce calcul. _path_length donnerait donc 1.0 pour tous les textes quelle
    # que soit leur longueur (répartition égale, incorrecte). On utilise le
    # nombre de caractères comme proxy du temps d'écriture à la place.
    if stroke.kind == "text" and stroke.text:
        return max(len(stroke.text), 1)
    return _path_length(stroke.points)


def compute_stroke_timings(scene: Scene) -> None:
    """Répartit la durée de la scène entre ses tracés, proportionnellement à
    leur longueur (ou leur nombre de caractères pour du texte), dessinés
    séquentiellement (comme un vrai geste d'écriture) plutôt que tous en
    même temps. Calculé côté Python pour rester la source de vérité unique
    (le JS se contente de lire start_sec/end_sec, il ne recalcule rien)."""
    strokes = scene.strokes
    if not strokes:
        return
    weights = [_stroke_weight(s) for s in strokes]
    total = sum(weights) or 1.0
    cursor = 0.0
    for stroke, weight in zip(strokes, weights):
        span = (weight / total) * scene.duration_sec
        stroke.start_sec = cursor
        stroke.end_sec = cursor + span
        cursor += span
