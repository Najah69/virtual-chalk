from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.scenes.schema import Exercise


def _wrapper(machine_name: str, version: str, params: dict[str, Any], title: str, content_type_label: str) -> dict:
    return {
        "library": f"{machine_name} {version}",
        "params": params,
        "subContentId": str(uuid.uuid4()),
        "metadata": {"contentType": content_type_label, "license": "U", "title": title},
    }


def build_true_false(question: str, correct: bool, title: str) -> dict:
    return _wrapper("H5P.TrueFalse", "1.8", {
        "question": f"<p>{question}</p>",
        "correct": "true" if correct else "false",
    }, title, "True/False Question")


def build_multi_choice(question: str, answers: list[tuple[str, bool]], title: str) -> dict:
    return _wrapper("H5P.MultiChoice", "1.16", {
        "question": f"<p>{question}</p>",
        "answers": [{"text": f"<div>{text}</div>", "correct": correct} for text, correct in answers],
    }, title, "Multiple Choice")


def build_blanks(instruction: str, sentence: str, title: str) -> dict:
    # Syntaxe H5P : *mot* marque un blanc, /variante pour une reponse
    # alternative, :indice pour un indice affiche a l'utilisateur.
    return _wrapper("H5P.Blanks", "1.14", {
        "text": f"<p>{instruction}</p>",
        "questions": [f"<p>{sentence}</p>"],
    }, title, "Fill in the Blanks")


def build_drag_text(instruction: str, text: str, title: str) -> dict:
    # Meme syntaxe *mot* que Blanks pour marquer les mots a glisser.
    return _wrapper("H5P.DragText", "1.10", {
        "taskDescription": f"<p>{instruction}</p>",
        "textField": text,
    }, title, "Drag Text")


BUILDERS = {
    "true_false": build_true_false,
    "multi_choice": build_multi_choice,
    "blanks": build_blanks,
    "drag_text": build_drag_text,
}


def build_interaction(exercise: "Exercise") -> dict:
    """Enveloppe une action (QCM/vrai-faux/...) dans le format
    d'interaction attendu par interactiveVideo.assets.interactions."""
    action = BUILDERS[exercise.exercise_type](**exercise.payload, title=exercise.title)
    return {
        "action": action,
        "x": 40,
        "y": 40,
        "width": 20,
        "height": 20,
        "duration": {"from": exercise.time_sec, "to": exercise.time_sec + 1},
        "pause": True,
        "displayType": "button",
        "label": f"<p>{exercise.title}</p>",
    }
