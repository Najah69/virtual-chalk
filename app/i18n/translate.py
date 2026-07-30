"""Traduction d'un Project généré vers une autre langue, pour l'export
multilingue (v1 : français -> anglais uniquement, l'arabe est reporté —
nécessite RTL + police manuscrite arabe + shaping contextuel, voir
docs/architecture.md).

Principe : un seul appel LLM traduit tout le contenu textuel (titre,
résumé, voix off, texte affiché à la craie, texte des exercices) d'un
coup. Les icônes/animations/diagrammes (déjà résolus en tracé vectoriel,
indépendants de la langue) sont copiés tels quels — jamais régénérés (un
diagramme régénéré coûterait un appel Gemini image-gen supplémentaire et
produirait un dessin visuellement différent de la version source).

v1 : le texte traduit garde exactement la position de l'original (pas de
recalcul d'anti-chevauchement) — un texte sensiblement plus long/court
dans la langue cible peut occasionnellement chevaucher un élément voisin,
défaut cosmétique accepté pour rester simple, corrigible ensuite via une
commande NL Editing (app/edit/nl_commands.py) si ça s'avère gênant en
pratique."""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from app.llm.base import LLMProvider
from app.scenes.schema import Exercise, Project, Scene

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {"en": "anglais"}

TRANSLATE_SYSTEM_PROMPT = """Tu traduis intégralement le contenu d'une
vidéo pédagogique vers {language}, en une seule réponse JSON strictement
structurée.

Règles :
- Traduis TOUT le texte humainement lisible ("title", "summary",
  "voice_over", chaque élément de "texts", les champs texte à l'intérieur
  de "payload" pour chaque exercice) vers {language} — jamais de mélange
  de langues.
- Conserve EXACTEMENT la même structure : même nombre de scènes dans le
  même ordre, même nombre d'éléments dans chaque liste "texts" dans le
  même ordre, même nombre d'exercices dans le même ordre. Ne fusionne, ne
  scinde, ni n'ajoute aucun élément.
- Les champs non-textuels (scene_id, exercise_id, type, correct,
  booléens) sont recopiés tels quels, jamais traduits.
- "texts" contient de courts mots/phrases écrits à la craie sur un
  tableau (pas de longues phrases) : garde des traductions courtes et
  naturelles, pas une traduction mot à mot artificiellement longue.
- Réponds uniquement avec le JSON, même structure que l'entrée.
"""


def _scene_texts(scene: Scene) -> list[str]:
    return [s.text for s in scene.strokes if s.kind == "text"]


def _build_payload(project: Project) -> dict:
    return {
        "title": project.title,
        "summary": project.summary,
        "scenes": [
            {"scene_id": scene.scene_id, "voice_over": scene.voice_over, "texts": _scene_texts(scene)}
            for scene in project.scenes
        ],
        "exercises": [
            {"exercise_id": ex.exercise_id, "title": ex.title, "type": ex.exercise_type, "payload": ex.payload}
            for ex in project.exercises
        ],
    }


def _apply_translated_scene(scene: Scene, translated: dict) -> Scene:
    translated_texts = iter(translated.get("texts", []))
    new_strokes = []
    for stroke in scene.strokes:
        if stroke.kind == "text":
            new_strokes.append(replace(stroke, text=next(translated_texts, stroke.text)))
        else:
            # icône/animation/forme (diagramme déjà vectorisé) : géométrie
            # indépendante de la langue, copiée telle quelle.
            new_strokes.append(stroke)
    return Scene(
        scene_id=scene.scene_id,
        voice_over=translated.get("voice_over", scene.voice_over),
        duration_sec=scene.duration_sec,
        visual_instruction=scene.visual_instruction,
        notes=scene.notes,
        strokes=new_strokes,
    )


def _apply_translated_exercise(exercise: Exercise, translated: dict) -> Exercise:
    return Exercise(
        exercise_id=exercise.exercise_id,
        exercise_type=exercise.exercise_type,
        time_sec=exercise.time_sec,
        title=translated.get("title", exercise.title),
        payload=translated.get("payload", exercise.payload),
    )


def translate_project(project: Project, target_lang: str, llm: LLMProvider) -> Project:
    """Traduit project vers target_lang (voir LANGUAGE_NAMES pour les
    langues supportées). Ne touche ni aux durées de scène (recalculées par
    Pipeline.synthesize_voices une fois la voix re-synthétisée dans la
    langue cible) ni aux icônes/animations/diagrammes déjà résolus."""
    language = LANGUAGE_NAMES.get(target_lang)
    if not language:
        raise ValueError(f"Langue cible non supportée : {target_lang!r}")

    payload = _build_payload(project)
    data = llm.complete_json(
        TRANSLATE_SYSTEM_PROMPT.format(language=language),
        json.dumps(payload, ensure_ascii=False),
    )

    translated_scenes_by_id = {s["scene_id"]: s for s in data.get("scenes", [])}
    new_scenes = [
        _apply_translated_scene(scene, translated_scenes_by_id.get(scene.scene_id, {}))
        for scene in project.scenes
    ]

    translated_exercises_by_id = {e["exercise_id"]: e for e in data.get("exercises", [])}
    new_exercises = [
        _apply_translated_exercise(ex, translated_exercises_by_id.get(ex.exercise_id, {}))
        for ex in project.exercises
    ]

    return Project(
        title=data.get("title", project.title),
        summary=data.get("summary", project.summary),
        sections=project.sections,
        scenes=new_scenes,
        theme=project.theme,
        exercises=new_exercises,
    )
