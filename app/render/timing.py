from __future__ import annotations

from app.scenes.schema import Scene

# Rythme d'écriture volontairement rapide (comme un vrai enseignant qui
# écrit un mot-clé, pas une révélation lente lettre par lettre) : le trait
# se dessine vite puis reste statique le reste de son créneau, plutôt que
# d'être étiré sur toute la durée de la scène — étirer un mot de 3 syllabes
# sur 15 secondes fait qu'il reste inachevé/illisible pendant l'essentiel
# du temps de visionnage (constaté à l'image en extrayant des frames
# régulièrement espacées d'une vraie vidéo générée).
CHARS_PER_SECOND = 10.0
SHAPE_UNITS_PER_SECOND = 400.0
MIN_DRAW_SECONDS = 0.6
MAX_DRAW_SECONDS = 2.5


def _path_length(points) -> float:
    length = 0.0
    for a, b in zip(points, points[1:]):
        length += ((b.x - a.x) ** 2 + (b.y - a.y) ** 2) ** 0.5
    return max(length, 1.0)


def _draw_duration(stroke) -> float:
    if stroke.kind == "text" and stroke.text:
        raw = len(stroke.text) / CHARS_PER_SECOND
    else:
        raw = _path_length(stroke.points) / SHAPE_UNITS_PER_SECOND
    return max(MIN_DRAW_SECONDS, min(MAX_DRAW_SECONDS, raw))


def compute_stroke_timings(scene: Scene) -> None:
    """Répartit les tracés sur la durée de la scène : chacun démarre dans
    un créneau égal (scene.duration_sec / nombre de tracés) pour apparaître
    progressivement pendant la narration, mais se dessine à un rythme
    d'écriture rapide et fixe plutôt que proportionnel à la durée
    disponible — voir CHARS_PER_SECOND ci-dessus. Calculé côté Python pour
    rester la source de vérité unique (le JS se contente de lire
    start_sec/end_sec, il ne recalcule rien)."""
    strokes = scene.strokes
    if not strokes:
        return
    slot = scene.duration_sec / len(strokes)
    for i, stroke in enumerate(strokes):
        slot_start = i * slot
        duration = min(_draw_duration(stroke), slot)
        stroke.start_sec = slot_start
        stroke.end_sec = slot_start + duration
