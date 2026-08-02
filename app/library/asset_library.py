"""Bibliothèque personnelle d'éléments vectorisés (Tâche 6, issue du
brainstorming "champ des possibles" — voir docs/architecture.md) : stockage
GLOBAL (comme les profils de voix, app/tts/voice_profiles.py — même
répertoire que app/settings.py::config_dir), jamais embarqué dans un
projet, disponible dans tous les projets futurs. Décisions actées avant
d'écrire ce code : purement statique pour l'instant (pas de presets animés
— dépend d'un panneau de propriétés pour éléments animés qui n'existe pas
encore), et aucune connaissance du LLM (purement manuel via l'éditeur, pas
de suggestion automatique à la génération)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.settings import config_dir

# Convention identique à icon_to_path.js::iconToPoints : un point stocké en
# {x,y} natif se replace à n'importe quelle taille via
# x_placé = x_ancre + x_natif * (taille_cible / LIBRARY_NATIVE_WIDTH). La
# largeur native est fixée une fois pour toutes ; seule la hauteur native
# varie pour préserver l'aspect d'origine (jamais de déformation).
LIBRARY_NATIVE_WIDTH = 24.0

# Seul "shape" est éligible : c'est la représentation FINALE d'un tracé déjà
# vectorisé — un diagramme généré passe en kind="shape" une fois vectorisé
# (voir Pipeline.finish_generation, app/pipeline.py), "diagram" n'étant
# qu'un kind transitoire avant résolution. "shape" est aussi le seul kind
# dont TOUS les points bougent ensemble lors d'un déplacement dans l'éditeur
# (voir editor_canvas.js::moveStroke) — un icône/texte/image a une ancre
# séparée du contenu réellement dessiné, "shape" non, ce qui en fait la
# seule représentation sûre pour un tracé complet réutilisable tel quel.
LIBRARY_ELIGIBLE_KINDS = {"shape"}


def library_file():
    return config_dir() / "asset_library.json"


@dataclass
class LibraryAssetPoint:
    x: float
    y: float
    pen_up: bool = False


@dataclass
class LibraryAsset:
    asset_id: str
    name: str
    kind: str
    color: str
    points: list[LibraryAssetPoint]
    native_height: float
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LibraryAsset":
        points = [LibraryAssetPoint(**p) for p in data["points"]]
        return cls(
            asset_id=data["asset_id"], name=data["name"], kind=data["kind"], color=data["color"],
            points=points, native_height=data["native_height"], created_at=data["created_at"],
        )


def load_library() -> list[LibraryAsset]:
    path = library_file()
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [LibraryAsset.from_dict(a) for a in raw]


def _save_library(assets: list[LibraryAsset]) -> None:
    library_file().write_text(
        json.dumps([a.to_dict() for a in assets], indent=2, ensure_ascii=False), encoding="utf-8",
    )


def normalize_points(points: list[dict[str, Any]], bbox: dict[str, float]) -> tuple[list[LibraryAssetPoint], float]:
    """Ramène des points en espace canvas réel (pixels du tableau) dans une
    boîte normalisée de largeur LIBRARY_NATIVE_WIDTH, origine (0,0) au coin
    haut-gauche de `bbox` — même convention que les icônes (viewBox 24x24,
    voir icon_paths.js). Retourne aussi la hauteur native correspondante
    (aspect d'origine préservé, jamais de déformation à la réutilisation)."""
    width = max(bbox["w"], 0.001)
    scale = LIBRARY_NATIVE_WIDTH / width
    native_points = [
        LibraryAssetPoint(
            x=(p["x"] - bbox["x"]) * scale, y=(p["y"] - bbox["y"]) * scale,
            pen_up=bool(p.get("penUp", False)),
        )
        for p in points
    ]
    native_height = bbox["h"] * scale
    return native_points, native_height


def add_asset(name: str, kind: str, color: str, points: list[dict[str, Any]], bbox: dict[str, float]) -> LibraryAsset:
    if kind not in LIBRARY_ELIGIBLE_KINDS:
        raise ValueError(f"Type non enregistrable dans la bibliothèque : {kind!r}")
    native_points, native_height = normalize_points(points, bbox)
    asset = LibraryAsset(
        asset_id=str(uuid.uuid4()), name=name.strip() or "Sans titre", kind=kind, color=color,
        points=native_points, native_height=native_height,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    assets = load_library()
    assets.append(asset)
    _save_library(assets)
    return asset


def remove_asset(asset_id: str) -> None:
    assets = [a for a in load_library() if a.asset_id != asset_id]
    _save_library(assets)
