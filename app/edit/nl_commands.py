"""Édition d'un Project par instruction en langage naturel ("NL Editing").

Principe : un seul appel LLM traduit l'instruction utilisateur en une liste
d'actions JSON structurées à partir d'un vocabulaire d'actions primitives
fixe (voir app/edit/prompts.py) ; ces actions sont ensuite appliquées
localement au Project par du code Python déterministe — jamais de
régénération complète ni de second appel LLM (le contenu de "insert_scene"
est généré dans ce même appel de traduction, pas dans un aller-retour
séparé).

Ce module ne fait que muter le Project : aucun appel TTS/rendu ici — c'est
Pipeline/api_bridge qui orchestrent l'I/O une fois l'EditResult connu (voir
Pipeline.resynthesize_scene et Pipeline.rerender_scene), pour que ce module
reste testable sans dépendances réseau/fichiers autres que le LLM."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from app.edit.prompts import EDIT_SYSTEM_PROMPT, build_edit_user_prompt
from app.llm.base import LLMProvider
from app.scenes.schema import Project, Scene, strokes_from_visual_elements

logger = logging.getLogger(__name__)

# Rythme de parole approximatif, pour estimer un budget de caractères a
# partir d'une duree cible (update_scene_duration) — sans rapport avec
# CHARS_PER_SECOND de app/render/timing.py, qui regle la vitesse du TRACE
# a la craie, pas le debit de la voix off.
_CHARS_PER_SECOND_SPEECH = 15.0

VALID_THEMES = ("chalk_board", "whiteboard_marker")


class EditCommandError(RuntimeError):
    """Action individuelle invalide (index hors limites, thème inconnu...) —
    n'interrompt pas l'application des autres actions de la commande."""


@dataclass
class EditResult:
    project: Project
    changed_scene_ids: list[str] = field(default_factory=list)
    voice_changed_scene_ids: list[str] = field(default_factory=list)
    theme_changed: bool = False
    applied_actions: list[dict] = field(default_factory=list)
    skipped_actions: list[dict] = field(default_factory=list)


def _resolve_index(project: Project, index: int) -> int:
    if not (0 <= index < len(project.scenes)):
        raise EditCommandError(f"scene_index hors limites : {index}")
    return index


def _apply_update_scene_duration(project: Project, action: dict, result: EditResult) -> None:
    scene = project.scenes[_resolve_index(project, int(action["scene_index"]))]
    max_duration = float(action["max_duration"])
    # duration_sec n'est qu'une estimation tant que la scene n'a pas ete
    # re-synthetisee (voir docs/architecture.md) : on tronque voice_over a
    # une longueur cohérente avec le budget demande (heuristique locale,
    # sans appel LLM supplementaire) ; Pipeline.resynthesize_scene fixera
    # ensuite la duree reelle a partir du nouvel audio.
    max_chars = max(20, int(max_duration * _CHARS_PER_SECOND_SPEECH))
    voice_over = scene.voice_over
    if len(voice_over) > max_chars:
        truncated = voice_over[:max_chars]
        cut = max(truncated.rfind(". "), truncated.rfind("! "), truncated.rfind("? "))
        scene.voice_over = truncated[: cut + 1].strip() if cut > 0 else truncated.strip() + "…"
    scene.duration_sec = max_duration
    result.changed_scene_ids.append(scene.scene_id)
    result.voice_changed_scene_ids.append(scene.scene_id)


def _apply_set_theme(project: Project, action: dict, result: EditResult) -> None:
    theme = str(action["theme"])
    if theme not in VALID_THEMES:
        raise EditCommandError(f"theme inconnu : {theme!r}")
    project.theme = theme
    result.theme_changed = True


def _apply_delete_scene(project: Project, action: dict, result: EditResult) -> None:
    index = _resolve_index(project, int(action["scene_index"]))
    removed = project.scenes.pop(index)
    result.changed_scene_ids.append(removed.scene_id)


def _apply_move_scene(project: Project, action: dict, result: EditResult) -> None:
    index = _resolve_index(project, int(action["scene_index"]))
    to_index = max(0, min(int(action["to_index"]), len(project.scenes) - 1))
    scene = project.scenes.pop(index)
    project.scenes.insert(to_index, scene)
    result.changed_scene_ids.append(scene.scene_id)


def _apply_insert_scene(project: Project, action: dict, result: EditResult) -> None:
    before_index = max(0, min(int(action.get("before_index", len(project.scenes))), len(project.scenes)))
    scene = Scene(
        scene_id=f"scene-{uuid.uuid4().hex[:8]}",
        voice_over=str(action.get("voice_over", "")).strip(),
        duration_sec=10.0,
        visual_instruction="",
        strokes=strokes_from_visual_elements(action.get("visual_elements", []), project.theme),
    )
    project.scenes.insert(before_index, scene)
    result.changed_scene_ids.append(scene.scene_id)
    result.voice_changed_scene_ids.append(scene.scene_id)


def _apply_replace_scene_content(project: Project, action: dict, result: EditResult) -> None:
    scene = project.scenes[_resolve_index(project, int(action["scene_index"]))]
    if "voice_over" in action:
        scene.voice_over = str(action["voice_over"]).strip()
        result.voice_changed_scene_ids.append(scene.scene_id)
    if "visual_elements" in action:
        scene.strokes = strokes_from_visual_elements(action["visual_elements"], project.theme)
    result.changed_scene_ids.append(scene.scene_id)


_ACTION_HANDLERS = {
    "update_scene_duration": _apply_update_scene_duration,
    "set_theme": _apply_set_theme,
    "delete_scene": _apply_delete_scene,
    "move_scene": _apply_move_scene,
    "insert_scene": _apply_insert_scene,
    "replace_scene_content": _apply_replace_scene_content,
}


def apply_nl_edit_command(project: Project, command_text: str, llm: LLMProvider) -> EditResult:
    """Traduit command_text en actions (un seul appel LLM) puis les
    applique au Project, dans l'ordre. Une action individuelle invalide
    (index hors limites, thème inconnu...) est ignorée et journalisée
    plutôt que de faire échouer toute la commande si le LLM en a produit
    plusieurs dont une seule est mauvaise."""
    data = llm.complete_json(EDIT_SYSTEM_PROMPT, build_edit_user_prompt(project, command_text))
    result = EditResult(project=project)

    for action in data.get("actions", []):
        handler = _ACTION_HANDLERS.get(action.get("action"))
        if handler is None:
            logger.warning("Action d'édition inconnue ignorée : %r", action.get("action"))
            result.skipped_actions.append(action)
            continue
        try:
            handler(project, action, result)
            result.applied_actions.append(action)
        except EditCommandError:
            logger.warning("Action d'édition ignorée (invalide) : %r", action)
            result.skipped_actions.append(action)

    return result
