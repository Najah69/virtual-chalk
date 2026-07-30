from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.scenes.schema import Project


class LLMProvider(ABC):
    """Un seul appel produit résumé + script + scènes — jamais d'aller-retours multiples."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        """Retourne la réponse brute (texte JSON) du modèle."""

    def generate_script(self, source_text: str, theme: str = "chalk_board") -> Project:
        raw = self._complete(SYSTEM_PROMPT, build_user_prompt(source_text))
        data = json.loads(raw)
        return Project.from_llm_response(data, theme=theme)
