from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


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
    kind: Literal["text", "shape"] = "shape"
    text: str = ""


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
class Project:
    title: str
    summary: str
    sections: list[Section]
    scenes: list[Scene]
    theme: str = "chalk_board"

    @property
    def slug(self) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        return base or "virtual-chalk-project"

    @classmethod
    def from_llm_response(cls, data: dict[str, Any]) -> "Project":
        sections = [Section(**s) for s in data.get("sections", [])]
        scenes = [
            Scene(
                scene_id=s["scene_id"],
                voice_over=s["voice_over"],
                duration_sec=float(s.get("duration_sec", 10)),
                visual_instruction=s.get("visual_instruction", ""),
                notes=s.get("notes", ""),
            )
            for s in data.get("script", [])
        ]
        title = (data.get("summary", "")[:60] or "Projet Virtual-Chalk").strip()
        return cls(title=title, summary=data.get("summary", ""), sections=sections, scenes=scenes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        sections = [Section(**s) for s in data.get("sections", [])]
        scenes = []
        for s in data.get("scenes", []):
            strokes = [
                Stroke(points=[Point(**p) for p in st["points"]], color=st["color"],
                       width=st["width"], kind=st.get("kind", "shape"), text=st.get("text", ""))
                for st in s.get("strokes", [])
            ]
            scenes.append(Scene(**{**s, "strokes": strokes}))
        return cls(
            title=data["title"], summary=data["summary"], sections=sections,
            scenes=scenes, theme=data.get("theme", "chalk_board"),
        )
