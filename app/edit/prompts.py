"""Prompt de traduction commande en langage naturel -> actions JSON.

Miroir de app/llm/prompts.py (même principe : un seul appel LLM, JSON
strict en sortie) mais pour l'édition d'un projet déjà généré plutôt que
la génération initiale."""

from __future__ import annotations

from app.llm.prompts import ANIMATION_LIST, ICON_LIST
from app.scenes.schema import Project

EDIT_SYSTEM_PROMPT = f"""Tu interprètes une instruction d'édition donnée en
langage naturel par l'utilisateur d'un éditeur de vidéo pédagogique
(Virtual-Chalk), et tu la traduis en une liste d'actions JSON strictement
structurées — jamais de texte libre en dehors du JSON.

Actions disponibles (une instruction peut produire zéro, une, ou plusieurs
actions, dans l'ordre où elles doivent s'appliquer) :
- {{"action": "update_scene_duration", "scene_index": <int>, "max_duration": <secondes>}}
- {{"action": "set_theme", "theme": "chalk_board" | "whiteboard_marker"}}
- {{"action": "delete_scene", "scene_index": <int>}}
- {{"action": "move_scene", "scene_index": <int>, "to_index": <int>}}
- {{"action": "insert_scene", "before_index": <int>, "voice_over": "...", "visual_elements": [...]}}
- {{"action": "replace_scene_content", "scene_index": <int>, "voice_over": "...", "visual_elements": [...]}}
- {{"action": "add_visual_elements", "scene_index": <int>, "visual_elements": [...]}}
- {{"action": "toggle_mascot", "enabled": <true|false>}}

IMPORTANT — "replace_scene_content" vs "add_visual_elements" : tu ne vois
PAS le contenu visuel actuel des scènes ci-dessous (seulement un extrait de
la voix off). "replace_scene_content" REMPLACE TOUT le contenu visuel
existant de la scène par ce que tu fournis dans "visual_elements" — donc
si l'instruction demande d'AJOUTER quelque chose à une scène qui existe
déjà (un schéma, une icône, un texte en plus...) sans qu'on te demande de
réécrire toute la scène, utilise TOUJOURS "add_visual_elements" (qui
ajoute aux éléments déjà présents, sans y toucher). Réserve
"replace_scene_content" aux cas où l'instruction demande explicitement de
réécrire/remplacer le contenu d'une scène.

Pour "insert_scene", "replace_scene_content" et "add_visual_elements",
"visual_elements" suit EXACTEMENT le même format que la génération de
script initiale (3 à 6 éléments, x/y en pourcentage 0-100, espacés pour ne
pas se chevaucher) :
  - texte : {{"type": "text", "content": "Mot ou courte phrase", "x": 50, "y": 30}}
  - icône (name dans cette liste exacte, par catégorie) :
{ICON_LIST}
    {{"type": "icon", "name": "sun", "x": 50, "y": 30}}
  - animation (name dans : {ANIMATION_LIST}) :
    {{"type": "animation", "name": "falling_rain", "x": 50, "y": 30}}
  - diagramme (reste simple : 2 à 4 formes de base, jamais de proportions
    exactes entre plusieurs formes, description précise comme une
    consigne à un illustrateur) :
    {{"type": "diagram", "description": "...", "x": 50, "y": 55, "width": 35, "height": 35}}

Règles :
- scene_index / before_index désignent une position dans la liste de
  scènes fournie ci-dessous (0 = première scène). Résous toi-même les
  références par contenu ("la scène sur la dérivation mathématique", "la
  dernière scène") à partir des résumés fournis.
- Instruction conditionnelle ("supprime SI...") : évalue la condition à
  partir du contenu des scènes ; n'émets l'action que si elle est vraie.
- Instruction ambiguë, hors périmètre, ou sans action correspondante :
  réponds {{"actions": []}} plutôt que d'inventer une action approximative.
- Réponds uniquement avec {{"actions": [...]}}, aucun texte hors JSON.
"""


def build_scene_context(project: Project) -> str:
    """Résumé compact (index — extrait de la voix off) pour que le LLM
    résolve les références par contenu sans qu'on lui transmette tout le
    script (sobriété en tokens : pas de re-génération, juste ce qu'il faut
    pour résoudre les références)."""
    lines = []
    for i, scene in enumerate(project.scenes):
        excerpt = " ".join(scene.voice_over.split())
        if len(excerpt) > 80:
            excerpt = excerpt[:80].rsplit(" ", 1)[0] + "…"
        lines.append(f"{i} — {excerpt}")
    return "\n".join(lines)


def build_edit_user_prompt(project: Project, command_text: str) -> str:
    return (
        f"Thème actuel : {project.theme}\n\n"
        f"Scènes actuelles :\n{build_scene_context(project)}\n\n"
        f"Instruction : {command_text}"
    )
