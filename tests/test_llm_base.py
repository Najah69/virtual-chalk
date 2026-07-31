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
