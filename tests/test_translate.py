"""app/i18n/translate.py : ne mute jamais le Project source, et propage
LLMJsonError sans construire de résultat partiel (Tâche A appliquée à ce
consommateur de complete_json)."""

from __future__ import annotations

import json

import pytest

from app.llm.base import LLMJsonError
from app.i18n.translate import translate_project
from app.scenes.schema import Point, Project, Scene, Stroke
from tests.conftest import FakeLLMProvider


def _make_project() -> Project:
    scene = Scene(
        scene_id="s0", voice_over="Bonjour le monde", duration_sec=5, visual_instruction="",
        strokes=[
            Stroke(points=[Point(0, 0)], color="#fff", width=90.0, kind="text", text="Bonjour"),
            Stroke(points=[Point(0, 0)], color="#fff", width=220.0, kind="icon", text="sun"),
        ],
    )
    return Project(title="Titre FR", summary="Résumé FR", sections=[], scenes=[scene], theme="chalk_board")


def test_translate_project_applies_translated_text_and_keeps_geometry():
    project = _make_project()
    translated = {
        "title": "Title EN",
        "summary": "Summary EN",
        "scenes": [{"scene_id": "s0", "voice_over": "Hello world", "texts": ["Hello"]}],
        "exercises": [],
    }
    llm = FakeLLMProvider([json.dumps(translated)])

    result = translate_project(project, "en", llm)

    assert result.title == "Title EN"
    assert result.scenes[0].voice_over == "Hello world"
    assert result.scenes[0].strokes[0].text == "Hello"
    # L'icône (géométrie indépendante de la langue) est copiée telle quelle.
    assert result.scenes[0].strokes[1].text == "sun"
    # Le projet source n'est jamais muté.
    assert project.title == "Titre FR"
    assert project.scenes[0].voice_over == "Bonjour le monde"
    assert project.scenes[0].strokes[0].text == "Bonjour"


def test_translate_project_unsupported_language_raises_without_llm_call():
    project = _make_project()
    llm = FakeLLMProvider([])
    with pytest.raises(ValueError):
        translate_project(project, "ar", llm)
    assert llm.calls == []


def test_translate_project_propagates_llm_json_error_without_mutating_source():
    project = _make_project()
    llm = FakeLLMProvider(["réponse illisible"])
    with pytest.raises(LLMJsonError):
        translate_project(project, "en", llm)
    assert project.title == "Titre FR"
