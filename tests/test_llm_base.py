"""Tâche A : robustesse de LLMProvider.complete_json face à des réponses
LLM imparfaites (texte parasite autour du JSON, réponse totalement
inexploitable)."""

from __future__ import annotations

import pytest

from app.llm.base import LLMJsonError
from tests.conftest import FakeLLMProvider


def test_complete_json_parses_pure_json():
    llm = FakeLLMProvider(['{"a": 1, "b": [2, 3]}'])
    assert llm.complete_json("sys", "user") == {"a": 1, "b": [2, 3]}


def test_complete_json_extracts_object_from_surrounding_text():
    llm = FakeLLMProvider(['Voici le JSON demandé :\n{"a": 1}\nVoilà !'])
    assert llm.complete_json("sys", "user") == {"a": 1}


def test_complete_json_raises_llm_json_error_on_garbage():
    llm = FakeLLMProvider(["ceci n'est pas du JSON du tout"])
    with pytest.raises(LLMJsonError) as exc_info:
        llm.complete_json("sys", "user")
    assert exc_info.value.raw_response == "ceci n'est pas du JSON du tout"


def test_complete_json_raises_llm_json_error_on_empty_response():
    llm = FakeLLMProvider([""])
    with pytest.raises(LLMJsonError):
        llm.complete_json("sys", "user")


def test_complete_json_with_images_parses_json_same_as_text_variant():
    llm = FakeLLMProvider(['{"sufficient": false, "missing_elements": []}'])
    result = llm.complete_json_with_images("sys", "user", [b"fake-jpeg-bytes"])
    assert result == {"sufficient": False, "missing_elements": []}
    assert llm.image_calls == [("sys", "user", [b"fake-jpeg-bytes"])]


def test_complete_json_with_images_tolerates_surrounding_text():
    llm = FakeLLMProvider(['Voici : {"sufficient": true}\nFin.'])
    assert llm.complete_json_with_images("sys", "user", []) == {"sufficient": True}


def test_provider_without_vision_support_raises_not_implemented_error():
    # LLMProvider._complete_with_images (le repli par défaut, pas surchargé
    # par FakeLLMProvider ici) doit échouer explicitement plutôt que
    # silencieusement, pour que l'appelant (analyze_scene_illustration)
    # puisse le distinguer d'une vraie réponse.
    from app.llm.base import LLMProvider

    class _TextOnlyProvider(LLMProvider):
        def _complete(self, system_prompt, user_prompt):
            return "{}"

    provider = _TextOnlyProvider(api_key="k", model="m")
    with pytest.raises(NotImplementedError):
        provider.complete_json_with_images("sys", "user", [b"img"])
