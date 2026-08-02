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
from app.llm.base import LLMJsonError, LLMProvider
from app.render.theme_registry import palette_for_theme, semantic_color_for_icon, text_color_for_theme
from app.scenes.schema import (
    Project,
    Scene,
    add_mascot_timeline,
    default_mascot_timeline,
    remove_mascot_timeline,
    strokes_from_visual_elements,
    truncate_voice_over_to_duration,
)

logger = logging.getLogger(__name__)

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
    # Message utilisateur si la traduction commande -> JSON a echoue (voir
    # LLMJsonError) : le Project reste alors strictement inchange (aucune
    # action n'a pu etre evaluee), l'UI affiche ce message plutot que de
    # planter ou de rester silencieuse — voir ui/editor/editor.js.
    error: str | None = None


def _resolve_index(project: Project, index: int) -> int:
    if not (0 <= index < len(project.scenes)):
        raise EditCommandError(f"scene_index hors limites : {index}")
    return index


def _apply_update_scene_duration(project: Project, action: dict, result: EditResult) -> None:
    scene = project.scenes[_resolve_index(project, int(action["scene_index"]))]
    max_duration = float(action["max_duration"])
    # Même heuristique que le glisser d'un bloc de scène sur la timeline
    # (voir app/scenes/timeline.py) — partagée, pas dupliquée, voir
    # truncate_voice_over_to_duration.
    truncate_voice_over_to_duration(scene, max_duration)
    result.changed_scene_ids.append(scene.scene_id)
    result.voice_changed_scene_ids.append(scene.scene_id)


def _recolor_strokes_for_theme(project: Project, theme: str) -> None:
    """La couleur d'un stroke est figée à la génération d'après la palette
    du thème d'ALORS (voir strokes_from_visual_elements) — sans ce
    recalcul, changer de thème via set_theme laisserait des strokes avec
    la couleur de l'ancien thème (ex: blanc, valide sur fond vert craie,
    devient du texte blanc invisible sur fond blanc feutre).

    Hiérarchie de recoloration par kind (même logique que
    strokes_from_visual_elements) :
    - "text" : une des quelques couleurs "sûres" du thème
      (text_color_for_theme), jamais la palette cyclique complète — un
      texte a besoin d'un contraste garanti, pas d'une teinte pensée pour
      une icône ponctuelle.
    - "icon"/"animation" : couleur sémantique si connue (eau=bleu,
      vegetation=vert...), sinon repli sur la palette cyclique.
    - "shape"/"diagram" : palette cyclique — ce sont des tracés déjà
      résolus géométriquement (diagramme vectorisé, dessin libre), la
      variation de couleur y est purement décorative."""
    palette = palette_for_theme(theme)
    for scene in project.scenes:
        text_index = 0
        for i, stroke in enumerate(scene.strokes):
            if stroke.kind == "text":
                stroke.color = text_color_for_theme(theme, text_index)
                text_index += 1
            elif stroke.kind in ("icon", "animation"):
                stroke.color = semantic_color_for_icon(stroke.text, theme) or palette[i % len(palette)]
            else:
                stroke.color = palette[i % len(palette)]


def _apply_set_theme(project: Project, action: dict, result: EditResult) -> None:
    theme = str(action["theme"])
    if theme not in VALID_THEMES:
        raise EditCommandError(f"theme inconnu : {theme!r}")
    project.theme = theme
    _recolor_strokes_for_theme(project, theme)
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
        strokes=strokes_from_visual_elements(action.get("visual_elements", []), project.theme, *project.canvas_size),
    )
    if project.mascot_enabled:
        # La scène vient d'être créée, pas encore insérée dans
        # project.scenes : jamais "greet" (réservé à la toute première
        # scène du projet, déjà saluée si elle existe).
        scene.mascot_timeline = default_mascot_timeline(scene, greet=False)
    project.scenes.insert(before_index, scene)
    result.changed_scene_ids.append(scene.scene_id)
    result.voice_changed_scene_ids.append(scene.scene_id)


def _apply_replace_scene_content(project: Project, action: dict, result: EditResult) -> None:
    scene = project.scenes[_resolve_index(project, int(action["scene_index"]))]
    changed = False
    if "voice_over" in action:
        scene.voice_over = str(action["voice_over"]).strip()
        result.voice_changed_scene_ids.append(scene.scene_id)
        changed = True
    if "visual_elements" in action:
        scene.strokes = strokes_from_visual_elements(action["visual_elements"], project.theme, *project.canvas_size)
        changed = True
    if not changed:
        # Ni voice_over ni visual_elements : le LLM a renvoyé une action
        # vide — sans ce garde-fou elle était acceptée en silence et
        # remontée comme un succès (scène ajoutée à changed_scene_ids)
        # alors que rien n'avait changé. Rencontré en pratique : "dessine
        # la molécule Sucre+CO2" a produit ce cas.
        raise EditCommandError(f"replace_scene_content sans voice_over ni visual_elements : {action!r}")
    result.changed_scene_ids.append(scene.scene_id)


def _apply_add_visual_elements(project: Project, action: dict, result: EditResult) -> None:
    """Contrairement à replace_scene_content (remplacement intégral),
    AJOUTE aux strokes déjà présents dans la scène — c'est l'action que le
    LLM doit choisir pour "ajoute/dessine X sur la scène Y" puisqu'il ne
    voit jamais le contenu visuel actuel d'une scène (voir
    build_scene_context) et ne peut donc pas le reconstruire fidèlement
    dans un replace_scene_content sans risquer de tout écraser."""
    scene = project.scenes[_resolve_index(project, int(action["scene_index"]))]
    visual_elements = action.get("visual_elements") or []
    if not visual_elements:
        raise EditCommandError(f"add_visual_elements sans visual_elements : {action!r}")
    scene.strokes.extend(strokes_from_visual_elements(visual_elements, project.theme, *project.canvas_size))
    result.changed_scene_ids.append(scene.scene_id)


def _apply_toggle_mascot(project: Project, action: dict, result: EditResult) -> None:
    enabled = bool(action["enabled"])
    if enabled == project.mascot_enabled:
        return  # Déjà dans l'état demandé : aucune scène à re-rendre.
    (add_mascot_timeline if enabled else remove_mascot_timeline)(project)
    # Toutes les scènes voient leur content_hash changer (mascot_timeline
    # ajouté/vidé) : les lister ici déclenche Pipeline.render côté
    # api_bridge.py (voir Api.apply_edit_command) — le choix fin de ce qui
    # est réellement re-rendu reste décidé par render_all via le hash.
    result.changed_scene_ids.extend(scene.scene_id for scene in project.scenes)


_ACTION_HANDLERS = {
    "update_scene_duration": _apply_update_scene_duration,
    "set_theme": _apply_set_theme,
    "delete_scene": _apply_delete_scene,
    "move_scene": _apply_move_scene,
    "insert_scene": _apply_insert_scene,
    "replace_scene_content": _apply_replace_scene_content,
    "add_visual_elements": _apply_add_visual_elements,
    "toggle_mascot": _apply_toggle_mascot,
}


def apply_nl_edit_command(project: Project, command_text: str, llm: LLMProvider) -> EditResult:
    """Traduit command_text en actions (un seul appel LLM) puis les
    applique au Project, dans l'ordre. Une action individuelle invalide
    (index hors limites, thème inconnu...) est ignorée et journalisée
    plutôt que de faire échouer toute la commande si le LLM en a produit
    plusieurs dont une seule est mauvaise. Si le modèle ne renvoie rien
    d'exploitable en JSON (LLMJsonError), le Project n'est pas touché : on
    retourne un EditResult vide avec un message d'erreur plutôt que de
    laisser l'exception remonter et casser l'appelant."""
    try:
        data = llm.complete_json(EDIT_SYSTEM_PROMPT, build_edit_user_prompt(project, command_text))
    except LLMJsonError as exc:
        logger.warning("Traduction de la commande d'édition impossible : %s", exc)
        return EditResult(
            project=project,
            error="Le modèle n'a pas renvoyé une réponse exploitable — réessayez ou reformulez la commande.",
        )

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
