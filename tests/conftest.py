"""Fixtures partagées — aucun test de ce dossier ne doit effectuer de vrai
appel réseau/LLM/TTS : tout provider externe est remplacé par un double de
test (voir FakeLLMProvider) qui rejoue des réponses préparées à l'avance."""

from __future__ import annotations

import pytest

from app.llm.base import LLMProvider


class FakeLLMProvider(LLMProvider):
    """Double de test pour LLMProvider : rejoue une liste de réponses brutes
    (une par appel, dans l'ordre) au lieu de faire un vrai appel réseau.
    Permet de tester complete_json/generate_script/etc. avec des réponses
    JSON valides, malformées, ou entourées de texte parasite."""

    def __init__(self, responses: list[str]):
        super().__init__(api_key="fake-key", model="fake-model")
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        # Appels multimodaux (voir app/critique/visual_critique.py) suivis
        # séparément des appels texte : puise dans la même file de réponses
        # préparées (l'ordre d'appel réel décide laquelle est consommée),
        # mais garde trace des images reçues pour vérifier le contenu envoyé.
        self.image_calls: list[tuple[str, str, list[bytes]]] = []

    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("FakeLLMProvider : plus de réponse préparée pour cet appel")
        return self._responses.pop(0)

    def _complete_with_images(self, system_prompt: str, user_prompt: str, images: list[bytes]) -> str:
        self.image_calls.append((system_prompt, user_prompt, images))
        if not self._responses:
            raise AssertionError("FakeLLMProvider : plus de réponse préparée pour cet appel")
        return self._responses.pop(0)


@pytest.fixture
def fake_llm():
    return FakeLLMProvider
