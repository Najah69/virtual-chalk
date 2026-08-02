"""Boucle d'auto-critique visuelle (proposition explicite de l'utilisateur,
voir docs/architecture.md) : après la synthèse vocale mais AVANT le
premier rendu vidéo réel, capture quelques images de chaque scène
directement depuis la fenêtre de rendu (pas de ré-encodage ffmpeg, voir
FrameCapture.capture_frames_at — les strokes déjà en mémoire suffisent) et
demande à un LLM multimodal de juger DEUX choses indépendamment :

1) l'illustration soutient-elle suffisamment le texte de la voix off —
   si non, récupère des visual_elements supplémentaires (même vocabulaire
   JSON que la génération initiale du script) et les ajoute à la scène ;
2) la mise en page du TEXTE est-elle propre (pas de chevauchement, pas de
   dépassement du cadre, pas de texte trop long pour rester lisible) —
   problème FRÉQUENT signalé explicitement par l'utilisateur, corrigé ici
   par des layout_fixes (déplacer/raccourcir/supprimer un élément
   EXISTANT, référencé par son index) plutôt qu'un simple ajout.

Les deux catégories de correction re-mettent la scène "en attente" pour
re-capturer/re-juger à l'itération suivante — jusqu'à convergence (plus
rien à ajouter ni à corriger) ou MAX_CRITIQUE_ITERATIONS.

Optionnel (voir Pipeline.run_visual_critique/GenerationRequest.auto_critique)
: coûte un appel LLM vision + une capture par scène encore en attente et
par itération, en plus du coût de génération normal — jamais activé par
défaut, décision explicite de l'utilisateur à chaque génération.

Limitation assumée, pas cachée : les éléments AJOUTÉS (missing_elements)
ne passent PAS par un resolve_overlaps conscient du contenu DÉJÀ placé sur
la scène (strokes_from_visual_elements ne résout les chevauchements
qu'ENTRE les éléments d'un même appel, voir app/scenes/schema.py) — la
seule protection contre un chevauchement avec l'existant est l'instruction
donnée au LLM de choisir un emplacement visiblement libre sur les images
fournies. C'est justement ce que les layout_fixes de l'itération SUIVANTE
peuvent rattraper (le modèle voit alors le résultat réel et peut proposer
de déplacer un texte devenu mal placé) — une des raisons de faire tourner
ces deux mécanismes dans la MÊME boucle plutôt que deux passes séparées."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

from app.llm.base import LLMJsonError, LLMProvider
from app.llm.prompts import ANIMATION_LIST, ICON_LIST
from app.scenes.schema import ORBIT_MAX_BODIES, Scene, strokes_from_visual_elements

if TYPE_CHECKING:
    from app.render.capture import FrameCapture
    from app.scenes.schema import Project

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str, float], None]]

# Décision explicite de l'utilisateur (voir docs/architecture.md) : un
# plafond dur et volontairement bas — chaque itération coûte un vrai appel
# LLM vision et une capture par scène encore en attente, pas juste un
# calcul local.
MAX_CRITIQUE_ITERATIONS = 2

# Fractions de la durée de la scène échantillonnées pour le jugement — ni
# pile au début (une pose "appear" de la mascotte ou un fondu d'image peut
# encore être en transition) ni pile à la fin, pour capturer l'état
# "établi" de la scène plutôt qu'un instant de transition.
SAMPLE_FRACTIONS = (0.35, 0.75)

# move/shorten_text ne s'appliquent qu'à du texte (voir apply_layout_fixes)
# — un icône/diagramme/image a une taille FIXE choisie à la génération
# (ICON_SIZE, dimensions du diagramme...), jamais variable ailleurs dans le
# moteur ; introduire un déplacement/redimensionnement pour ces kinds ici
# créerait un axe de variation inédit, hors de la demande explicite de
# l'utilisateur ("problèmes de mise en page des TEXTES"). "remove" reste
# disponible pour n'importe quel kind (opération toujours bien définie,
# utile si le modèle juge un élément entièrement redondant/cassé).
_TEXT_ONLY_FIX_ACTIONS = {"move", "shorten_text"}

CRITIQUE_SYSTEM_PROMPT = f"""Tu es un critique pédagogique qui examine une scène déjà produite d'une
vidéo explicative façon tableau noir (craie/feutre). On te donne le texte
de la voix off de cette scène, la liste des éléments ACTUELLEMENT sur le
tableau (avec leur index, pour pouvoir en désigner un précisément), et des
captures d'écran RÉELLES du tableau à différents instants de cette scène
(le contenu actuel y est déjà dessiné, ce n'est pas un aperçu vide).

Tu juges DEUX choses, indépendamment l'une de l'autre :

1) L'ILLUSTRATION est-elle suffisante ? Est-ce que ce qui est dessiné
   illustre suffisamment ce que dit la voix off pour qu'un élève
   comprenne le concept rien qu'en regardant, sans avoir besoin
   d'entendre le son ? Une scène uniquement en texte, ou avec un texte
   long sans aucune icône/schéma/animation pour l'accompagner, n'est PAS
   suffisante — juge sévèrement.

2) La MISE EN PAGE DU TEXTE est-elle propre ? C'est un problème FRÉQUENT,
   cherche-le activement sur les images fournies :
   - un texte qui dépasse du cadre visible du tableau (trop près d'un
     bord, ou carrément coupé)
   - un texte qui chevauche un autre élément (une icône, un schéma, un
     autre texte) au point de devenir illisible
   - un texte visiblement trop long pour rester lisible à cette taille et
     cet endroit

Si l'illustration manque, propose des éléments À AJOUTER (jamais à
retirer ce qui existe) dans "missing_elements", avec EXACTEMENT le même
format que la génération initiale d'une vidéo :
- texte : {{"type": "text", "content": "Mot ou courte phrase", "x": 50, "y": 30}}
- icône (name DOIT être choisi exactement dans cette liste) :
  {{"type": "icon", "name": "sun", "x": 50, "y": 30}}
{ICON_LIST}
- animation (name DOIT être choisi exactement dans cette liste : {ANIMATION_LIST}) :
  {{"type": "animation", "name": "falling_rain", "x": 50, "y": 30}}
- animation "orbit" (jusqu'à {ORBIT_MAX_BODIES} corps qui tournent autour d'un centre) :
  {{"type": "animation", "name": "orbit", "x": 50, "y": 50,
    "center_icon": "sun", "center_size_pct": 8,
    "bodies": [{{"icon": "world", "radius_pct": 12, "period_s": 4, "size_pct": 3, "phase_deg": 0}}],
    "draw_orbit_rings": true}}
- diagramme (schéma géométrique/structurel simple, généré puis vectorisé) :
  {{"type": "diagram", "description": "...", "x": 50, "y": 55, "width": 35, "height": 35}}
x/y/width/height sont des pourcentages (0-100) de la taille du tableau ;
0,0 = coin haut-gauche. Choisis des positions dans une zone visiblement
LIBRE sur les images fournies — ne place jamais un nouvel élément par-
dessus ce qui est déjà dessiné.

Si la mise en page du texte pose problème, propose des corrections dans
"layout_fixes" — chaque correction cible un élément EXISTANT par son
"stroke_index" (voir la liste fournie), une seule action par correction :
- déplacer un texte : {{"stroke_index": 2, "action": "move", "x": 15, "y": 60}}
  (x/y = nouvelle position, mêmes pourcentages que ci-dessus)
- raccourcir un texte trop long (garde le sens, coupe à une fin de phrase
  ou de groupe de mots plutôt qu'au milieu d'un mot) :
  {{"stroke_index": 2, "action": "shorten_text", "text": "Nouveau texte plus court"}}
- supprimer un élément devenu redondant ou cassé :
  {{"stroke_index": 5, "action": "remove"}}
Ne propose une correction QUE pour un problème que tu peux réellement voir
sur les images fournies — jamais de correction préventive sans preuve
visuelle du problème.

Renvoie UNIQUEMENT du JSON, exactement ce schéma :
{{
  "sufficient": true ou false,
  "reason": "une phrase expliquant ton jugement (illustration ET mise en page)",
  "missing_elements": [ ... liste au format ci-dessus, vide si rien à ajouter ... ],
  "layout_fixes": [ ... liste au format ci-dessus, vide si rien à corriger ... ]
}}
"""


@dataclass
class CritiqueVerdict:
    scene_id: str
    sufficient: bool
    missing_elements: list[dict] = field(default_factory=list)
    layout_fixes: list[dict] = field(default_factory=list)
    reason: str = ""


def _sample_timestamps(scene: Scene) -> list[float]:
    return [max(0.0, min(scene.duration_sec, scene.duration_sec * f)) for f in SAMPLE_FRACTIONS]


def _describe_current_elements(scene: Scene, canvas_width: float, canvas_height: float) -> list[dict[str, Any]]:
    """Liste compacte et INDEXÉE des strokes actuels de la scène, donnée en
    plus des images au modèle — sans elle, il ne peut désigner AUCUN
    élément existant à corriger (une image seule permet de dire "ajoute
    quelque chose ici", jamais "corrige le stroke n°3"). L'index correspond
    exactement à la position dans scene.strokes, relu tel quel par
    apply_layout_fixes."""
    described = []
    for i, stroke in enumerate(scene.strokes):
        if not stroke.points:
            continue
        anchor = stroke.points[0]
        entry: dict[str, Any] = {
            "index": i, "kind": stroke.kind,
            "x": round(anchor.x / canvas_width * 100, 1),
            "y": round(anchor.y / canvas_height * 100, 1),
        }
        if stroke.kind == "text":
            entry["content"] = stroke.text
        elif stroke.kind in ("icon", "animation"):
            entry["name"] = stroke.text
        described.append(entry)
    return described


def analyze_scene_illustration(llm: LLMProvider, scene: Scene, frames: list[bytes],
                                canvas_width: float, canvas_height: float) -> CritiqueVerdict:
    """Un appel LLM vision par scène (pas un seul appel groupé pour tout le
    projet) : isole les échecs (une scène dont l'appel échoue n'affecte pas
    le jugement des autres) et évite de faire raisonner le modèle sur
    plusieurs scènes à la fois dans une seule réponse JSON, plus fragile à
    parser correctement à grande échelle."""
    elements_json = json.dumps(_describe_current_elements(scene, canvas_width, canvas_height), ensure_ascii=False)
    user_prompt = (
        f'Voix off de cette scène : "{scene.voice_over}"\n\n'
        f"Éléments actuellement sur le tableau (index utilisable pour une correction) :\n{elements_json}\n\n"
        f"Voici {len(frames)} image(s) réelles du tableau à différents instants de cette scène. "
        "Juge si l'illustration soutient suffisamment ce texte ET si la mise en page du texte est propre."
    )
    try:
        data = llm.complete_json_with_images(CRITIQUE_SYSTEM_PROMPT, user_prompt, frames)
    except (LLMJsonError, NotImplementedError) as exc:
        # Ne bloque JAMAIS la génération : une critique indisponible ou
        # inexploitable pour une scène équivaut à "suffisant" (dégradation
        # silencieuse vers le comportement d'avant cette fonctionnalité,
        # pas un échec de toute la génération déjà payée en TTS/rendu).
        logger.warning("Critique visuelle indisponible pour %s : %s", scene.scene_id, exc)
        return CritiqueVerdict(scene_id=scene.scene_id, sufficient=True)
    return CritiqueVerdict(
        scene_id=scene.scene_id,
        sufficient=bool(data.get("sufficient", True)),
        missing_elements=list(data.get("missing_elements") or []),
        layout_fixes=list(data.get("layout_fixes") or []),
        reason=str(data.get("reason", "")),
    )


def apply_layout_fixes(scene: Scene, fixes: list[dict[str, Any]],
                        canvas_width: float, canvas_height: float) -> bool:
    """Applique les corrections de mise en page proposées par la critique à
    des strokes EXISTANTS (déplacer/raccourcir un texte, supprimer
    n'importe quel élément), référencés par leur index dans scene.strokes
    (voir _describe_current_elements). Renvoie True si au moins une
    correction a réellement été appliquée.

    Défensif par construction, pas juste par confort : un index hors
    limites, une action incompatible avec le kind ciblé (move/shorten_text
    sur autre chose que du texte), ou des champs manquants sont ignorés
    silencieusement plutôt que de lever une exception — une correction
    imparfaite ne doit jamais faire planter la boucle ni la génération.

    Les suppressions sont appliquées EN DERNIER, par index décroissant :
    les appliquer au fil de l'eau décalerait les index des corrections
    suivantes dans le même lot (une suppression de l'index 2 rendrait
    l'index 5 d'une correction suivante incorrect)."""
    changed = False
    remove_indices: set[int] = set()

    for fix in fixes:
        index = fix.get("stroke_index")
        action = fix.get("action")
        if not isinstance(index, int) or not (0 <= index < len(scene.strokes)):
            continue
        if action == "remove":
            remove_indices.add(index)
            continue
        if action not in _TEXT_ONLY_FIX_ACTIONS:
            continue
        stroke = scene.strokes[index]
        if stroke.kind != "text":
            continue
        if action == "move" and stroke.points:
            x_pct, y_pct = fix.get("x"), fix.get("y")
            if x_pct is None or y_pct is None:
                continue
            stroke.points[0].x = max(0.0, min(100.0, float(x_pct))) / 100.0 * canvas_width
            stroke.points[0].y = max(0.0, min(100.0, float(y_pct))) / 100.0 * canvas_height
            changed = True
        elif action == "shorten_text":
            new_text = str(fix.get("text", "")).strip()
            if new_text and len(new_text) < len(stroke.text or ""):
                stroke.text = new_text
                changed = True

    for index in sorted(remove_indices, reverse=True):
        scene.strokes.pop(index)
        changed = True

    return changed


def run_critique_loop(llm: LLMProvider, project: "Project", capture: "FrameCapture",
                       on_progress: ProgressCallback = None) -> list[str]:
    """Retourne les scene_id encore en attente (illustration insuffisante
    OU mise en page à corriger) après MAX_CRITIQUE_ITERATIONS —
    informationnel, n'empêche jamais la suite du pipeline (une amélioration
    imparfaite/incomplète vaut mieux qu'une génération bloquée). Une scène
    pour laquelle rien n'a été ajouté NI corrigé à une itération n'est
    JAMAIS ré-analysée aux itérations suivantes (coût déjà justifié une
    fois, pas la peine de le repayer)."""
    pending = list(project.scenes)
    canvas_width, canvas_height = project.canvas_size
    for iteration in range(MAX_CRITIQUE_ITERATIONS):
        if not pending:
            break
        still_pending = []
        for scene in pending:
            frames = capture.capture_frames_at(
                scene, project.theme, canvas_width, canvas_height, _sample_timestamps(scene),
            )
            verdict = analyze_scene_illustration(llm, scene, frames, canvas_width, canvas_height)

            changed = False
            if verdict.missing_elements:
                new_strokes = strokes_from_visual_elements(
                    verdict.missing_elements, project.theme, canvas_width, canvas_height,
                )
                scene.strokes.extend(new_strokes)
                changed = True
            if verdict.layout_fixes and apply_layout_fixes(scene, verdict.layout_fixes, canvas_width, canvas_height):
                changed = True

            if changed:
                still_pending.append(scene)
        pending = still_pending
        if on_progress:
            on_progress("critique", (iteration + 1) / MAX_CRITIQUE_ITERATIONS)
    return [s.scene_id for s in pending]
