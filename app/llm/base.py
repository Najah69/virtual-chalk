from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.llm.prompts import DEFAULT_VIDEO_PROFILE, build_system_prompt, build_user_prompt
from app.scenes.schema import Project


class LLMProvider(ABC):
    """Un seul appel produit résumé + script + scènes — jamais d'aller-retours multiples."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        """Retourne la réponse brute (texte JSON) du modèle."""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Primitive partagée : appel LLM + parsing JSON, sans hypothèse sur
        le schéma de la réponse. Utilisée par generate_script (schéma
        Project) et par app/edit/nl_commands.py (schéma actions d'édition) —
        deux consommateurs différents du même appel brut."""
        raw = self._complete(system_prompt, user_prompt)
        return json.loads(raw)

    def generate_script(self, source_text: str, theme: str = "chalk_board",
                         script_profile: str = DEFAULT_VIDEO_PROFILE,
                         github_content_kind: str | None = None) -> Project:
        data = self.complete_json(
            build_system_prompt(script_profile),
            build_user_prompt(source_text, github_content_kind),
        )
        return Project.from_llm_response(data, theme=theme)
