"""app/library/diagram_suggestions.py : un seul appel LLM propose une liste
de schémas à pré-générer vers la bibliothèque personnelle (idée
utilisateur, voir docs/architecture.md) — jamais d'exception, une
suggestion indisponible/inexploitable équivaut à une liste vide (ce n'est
qu'une aide optionnelle, pas un prérequis à la génération normale)."""

from __future__ import annotations

import json

from app.library.diagram_suggestions import MAX_SUGGESTIONS, suggest_diagram_topics
from tests.conftest import FakeLLMProvider


def test_suggest_diagram_topics_returns_descriptions_from_llm():
    llm = FakeLLMProvider([json.dumps({"descriptions": ["molécule de sucre", "cycle de l'eau"]})])

    result = suggest_diagram_topics(llm, "Un texte sur la chimie et le climat.")

    assert result == ["molécule de sucre", "cycle de l'eau"]


def test_suggest_diagram_topics_caps_at_max_suggestions():
    many = [f"schéma {i}" for i in range(MAX_SUGGESTIONS + 5)]
    llm = FakeLLMProvider([json.dumps({"descriptions": many})])

    result = suggest_diagram_topics(llm, "Texte source")

    assert len(result) == MAX_SUGGESTIONS


def test_suggest_diagram_topics_strips_blank_entries():
    llm = FakeLLMProvider([json.dumps({"descriptions": ["  ", "un vrai schéma", ""]})])

    result = suggest_diagram_topics(llm, "Texte source")

    assert result == ["un vrai schéma"]


def test_suggest_diagram_topics_returns_empty_list_on_unparsable_response():
    llm = FakeLLMProvider(["réponse illisible, pas du JSON"])

    result = suggest_diagram_topics(llm, "Texte source")

    assert result == []


def test_suggest_diagram_topics_returns_empty_list_when_no_descriptions_key():
    llm = FakeLLMProvider([json.dumps({"descriptions": []})])

    result = suggest_diagram_topics(llm, "Texte peu propice aux schémas")

    assert result == []
