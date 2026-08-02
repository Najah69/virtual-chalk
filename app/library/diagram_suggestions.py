"""Pré-génération de schémas vers la bibliothèque personnelle (idée
utilisateur, voir docs/architecture.md) : avant même de lancer la
génération d'une leçon, un seul appel LLM propose une liste de schémas
STATIQUES pertinents pour le texte source fourni (ex: "molécule de sucre",
"graphique simplifié du krach de 1929") — l'utilisateur choisit ensuite
lesquels faire réellement générer/vectoriser (voir
Pipeline.generate_library_diagrams), jamais automatique.

Ce module ne fait QUE la suggestion (texte -> liste de descriptions) : la
génération d'image et la vectorisation restent dans
app/render/diagram_generator.py, appelées depuis app/pipeline.py."""

from __future__ import annotations

import logging

from app.llm.base import LLMJsonError, LLMProvider

logger = logging.getLogger(__name__)

# Borne le coût de la passe de génération qui suit (un appel Gemini Image
# par description retenue) — pas une limite technique du LLM de suggestion
# lui-même.
MAX_SUGGESTIONS = 6

SUGGEST_DIAGRAMS_SYSTEM_PROMPT = f"""Tu prépares en avance des schémas pédagogiques pour une future vidéo
explicative façon tableau noir (craie/feutre), à partir d'un texte source
(cours, article, notes...). Propose jusqu'à {MAX_SUGGESTIONS} schémas
STATIQUES qui illustreraient utilement les concepts les plus importants de
ce texte — pas un schéma par paragraphe, seulement ceux qui apportent
vraiment quelque chose qu'un texte seul n'apporte pas (structure, relation,
comparaison, évolution simplifiée...).

Chaque schéma doit rester simple (2 à 4 formes de base, jamais de
proportions exactes entre plusieurs formes) et se décrire comme une
consigne précise à un illustrateur qui ne connaît pas le sujet — même
registre que la description d'un diagramme dans l'édition de scène.
N'invente rien qui ne soit pas déjà présent dans le texte source.

Si le texte ne s'y prête pas (rien de suffisamment visuel/structurel),
renvoie une liste vide plutôt que d'inventer un schéma superflu.

Renvoie UNIQUEMENT du JSON, exactement ce schéma :
{{"descriptions": ["...", "..."]}}
"""


def _build_user_prompt(source_text: str) -> str:
    return f"Texte source :\n\n{source_text}"


def suggest_diagram_topics(llm: LLMProvider, source_text: str) -> list[str]:
    """Un seul appel LLM. Ne lève jamais : une suggestion indisponible ou
    inexploitable équivaut à une liste vide (dégradation silencieuse, même
    logique que analyze_scene_illustration côté auto-critique visuelle) —
    ce n'est qu'une aide optionnelle, jamais un prérequis à la génération
    normale du projet."""
    try:
        data = llm.complete_json(SUGGEST_DIAGRAMS_SYSTEM_PROMPT, _build_user_prompt(source_text))
    except LLMJsonError as exc:
        logger.warning("Suggestion de schémas indisponible : %s", exc)
        return []
    descriptions = [str(d).strip() for d in (data.get("descriptions") or []) if str(d).strip()]
    return descriptions[:MAX_SUGGESTIONS]
