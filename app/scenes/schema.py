from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.render.layout import resolve_overlaps
from app.render.theme_registry import palette_for_theme, semantic_color_for_icon

CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
TEXT_STROKE_WIDTH = 90.0
ICON_SIZE = 220.0

# Doit rester synchronisé avec les icônes réellement converties dans
# app/render/web_template/icon_paths.js (voir docs/architecture.md pour
# la procédure de conversion depuis Feather Icons + Tabler Icons).
ICON_NAMES = {
    # Feather Icons (vocabulaire de base, meteo/UI générique)
    "sun", "cloud", "cloud-rain", "droplet", "arrow-right", "arrow-up",
    "arrow-down", "thermometer", "wind", "umbrella", "home", "book",
    "check", "refresh-cw", "map-pin", "zap",
    # Tabler Icons : nature/geographie (ajoutees pour couvrir riviere,
    # fleuve, ocean, mer, terre, montagne qui manquaient totalement)
    "mountain", "world", "beach", "anchor", "sailboat", "ship", "tree",
    "plant", "leaf", "seedling", "flower", "fish", "droplets", "ripple",
    "wave-sine", "snowflake", "moon", "stars",
    # Tabler Icons : concepts generaux reutilisables (pas specifiques a
    # un sujet), utiles pour composer des schemas dans n'importe quel domaine
    "flag", "heart", "bulb", "rocket", "clock", "calendar", "chart-bar",
    "brain", "building", "building-bank", "users", "user", "coin", "scale",
}

ANIMATION_SIZE = 220.0

# Doit rester synchronisé avec window.ANIMATIONS dans
# app/render/web_template/animations.js.
ANIMATION_NAMES = {"falling_rain"}


@dataclass
class Point:
    x: float
    y: float


@dataclass
class Stroke:
    """Unité vectorielle éditable : un tracé (texte converti en contour, ou
    dessin libre). La texture (grain craie, brillance feutre) est calculée
    au rendu à partir de ces données, jamais stockée."""

    points: list[Point]
    color: str
    width: float
    kind: Literal["text", "shape", "icon", "animation"] = "shape"
    text: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0


@dataclass
class Scene:
    scene_id: str
    voice_over: str
    duration_sec: float
    visual_instruction: str
    notes: str = ""
    strokes: list[Stroke] = field(default_factory=list)
    audio_path: str = ""
    content_hash: str = ""


@dataclass
class Section:
    title: str
    paragraphs: list[str]


@dataclass
class Exercise:
    """Un exercice H5P (QCM, vrai/faux, texte a trous, glisser les mots)
    positionne a un instant du montage final. `payload` contient les
    champs propres au type (voir app/h5p/interactions.py) ; `time_sec`
    est le temps absolu dans la video concatenee finale, pas relatif a
    une scene."""

    exercise_id: str
    exercise_type: Literal["true_false", "multi_choice", "blanks", "drag_text"]
    time_sec: float
    title: str
    payload: dict[str, Any]


def _strokes_from_visual_elements(elements: list[dict[str, Any]], theme: str) -> list[Stroke]:
    """Convertit les éléments visuels générés par le LLM (mots/courtes
    phrases ou icônes, positionnés en pourcentage du tableau) en Stroke.
    Le tracé réel (contour de lettres/icône) est calculé côté JS au rendu
    (text_to_path.js / icon_to_path.js) — ici on ne fixe que le point
    d'ancrage. Les icônes hors vocabulaire connu (ICON_NAMES) sont
    ignorées plutôt que de planter le rendu sur une sortie LLM imprévue.

    Le LLM choisit x/y en pourcentage sans connaître les dimensions
    réelles de ce qu'il place (largeur du texte selon son contenu,
    empreinte d'une icône/animation) : rien ne garantit qu'un texte ne
    recouvre pas un dessin, ce qu'un professeur ne fait jamais au tableau.
    `resolve_overlaps` écarte donc les éléments dont la boîte englobante
    se chevauche avant de figer leur position finale dans les Stroke."""
    palette = palette_for_theme(theme)
    planned: list[dict[str, Any]] = []
    for i, el in enumerate(elements):
        el_type = el.get("type")
        x = (float(el.get("x", 50)) / 100.0) * CANVAS_WIDTH
        y = (float(el.get("y", 50)) / 100.0) * CANVAS_HEIGHT
        color = palette[i % len(palette)]

        if el_type == "text":
            content = str(el.get("content", "")).strip()
            if not content:
                continue
            planned.append({"kind": "text", "x": x, "y": y, "size": TEXT_STROKE_WIDTH, "content": content, "name": "", "color": color})
        elif el_type == "icon":
            name = str(el.get("name", "")).strip()
            if name not in ICON_NAMES:
                continue
            icon_color = semantic_color_for_icon(name, theme) or color
            planned.append({"kind": "icon", "x": x, "y": y, "size": ICON_SIZE, "content": "", "name": name, "color": icon_color})
        elif el_type == "animation":
            name = str(el.get("name", "")).strip()
            if name not in ANIMATION_NAMES:
                continue
            anim_color = semantic_color_for_icon(name, theme) or color
            planned.append({"kind": "animation", "x": x, "y": y, "size": ANIMATION_SIZE, "content": "", "name": name, "color": anim_color})

    resolve_overlaps(planned, CANVAS_WIDTH, CANVAS_HEIGHT)

    return [
        Stroke(points=[Point(el["x"], el["y"])], color=el["color"], width=el["size"],
               kind=el["kind"], text=el["content"] if el["kind"] == "text" else el["name"])
        for el in planned
    ]


@dataclass
class Project:
    title: str
    summary: str
    sections: list[Section]
    scenes: list[Scene]
    theme: str = "chalk_board"
    exercises: list[Exercise] = field(default_factory=list)

    @property
    def slug(self) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        return base or "virtual-chalk-project"

    def scene_start_times(self) -> dict[str, float]:
        """Instant absolu (dans la video concatenee finale) ou commence
        chaque scene — utilise par l'UI pour convertir un point choisi
        dans une scene en temps absolu pour un exercice."""
        starts = {}
        cursor = 0.0
        for scene in self.scenes:
            starts[scene.scene_id] = cursor
            cursor += scene.duration_sec
        return starts

    @classmethod
    def from_llm_response(cls, data: dict[str, Any], theme: str = "chalk_board") -> "Project":
        sections = [Section(**s) for s in data.get("sections", [])]
        scenes = [
            Scene(
                scene_id=s["scene_id"],
                voice_over=s["voice_over"],
                duration_sec=float(s.get("duration_sec", 10)),
                visual_instruction=s.get("visual_instruction", ""),
                notes=s.get("notes", ""),
                strokes=_strokes_from_visual_elements(s.get("visual_elements", []), theme),
            )
            for s in data.get("script", [])
        ]
        title = (data.get("summary", "")[:60] or "Projet Virtual-Chalk").strip()
        return cls(title=title, summary=data.get("summary", ""), sections=sections, scenes=scenes, theme=theme)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        sections = [Section(**s) for s in data.get("sections", [])]
        scenes = []
        for s in data.get("scenes", []):
            strokes = [
                Stroke(points=[Point(**p) for p in st["points"]], color=st["color"],
                       width=st["width"], kind=st.get("kind", "shape"), text=st.get("text", ""),
                       start_sec=st.get("start_sec", 0.0), end_sec=st.get("end_sec", 0.0))
                for st in s.get("strokes", [])
            ]
            scenes.append(Scene(**{**s, "strokes": strokes}))
        exercises = [Exercise(**ex) for ex in data.get("exercises", [])]
        return cls(
            title=data["title"], summary=data["summary"], sections=sections,
            scenes=scenes, theme=data.get("theme", "chalk_board"), exercises=exercises,
        )
