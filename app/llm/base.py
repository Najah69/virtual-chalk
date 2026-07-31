from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.llm.prompts import DEFAULT_VIDEO_PROFILE, build_system_prompt, build_user_prompt
from app.scenes.schema import Project


class LLMJsonError(RuntimeError):
    """La réponse du LLM n'est pas un JSON exploitable — ni telle quelle,
    ni après extraction d'une sous-chaîne {...}. Porte un extrait de la
    réponse brute pour rester diagnosticable sans avoir à relire les logs."""

    def __init__(self, message: str, raw_response: str):
        super().__init__(message)
        self.raw_response = raw_response


def _extract_json_object(raw: str) -> str:
    """La plupart des modèles renvoient du JSON pur (demandé explicitement
    dans tous nos prompts systeme), mais certains l'entourent parfois de
    texte ("Voici le JSON : {...}", commentaire après coup...) — on ne
    tente l'extraction qu'en repli, après l'échec d'un parsing direct."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Aucune sous-chaine {...} trouvee")
    return raw[start : end + 1]


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
        Project), app/edit/nl_commands.py (schéma actions d'édition) et
        app/i18n/translate.py (schéma traduction) — trois consommateurs
        différents du même appel brut.

        Tolère une réponse entourée de texte parasite (essaie d'abord un
        parsing direct, puis extrait la sous-chaîne {...} en repli) ; lève
        LLMJsonError si aucune des deux tentatives n'aboutit, plutôt que de
        laisser un json.JSONDecodeError brut remonter jusqu'à l'appelant —
        celui-ci doit pouvoir dégrader proprement (voir apply_nl_edit_command,
        translate_project) au lieu de planter toute l'opération en cours."""
        raw = self._complete(system_prompt, user_prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_extract_json_object(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMJsonError(
                f"Réponse du modèle non exploitable en JSON : {exc}", raw_response=raw,
            ) from exc

    def generate_script(self, source_text: str, theme: str = "chalk_board",
                         script_profile: str = DEFAULT_VIDEO_PROFILE,
                         github_content_kind: str | None = None) -> Project:
        data = self.complete_json(
            build_system_prompt(script_profile),
            build_user_prompt(source_text, github_content_kind),
        )
        return Project.from_llm_response(data, theme=theme)
