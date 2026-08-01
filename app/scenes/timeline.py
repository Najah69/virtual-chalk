"""TimelineJSON : vue dérivée d'un Project pour une timeline visuelle
éditable (Timeliner — voir docs/architecture.md, section "Timeline
éditable & Anime.js"), et la fonction inverse pour réappliquer des
modifications faites sur cette vue au Project.

Pas un nouveau modèle de données persisté : les timestamps/l'ordre
existent déjà dans Project/Scene/MascotAction/Stroke, ce module ne fait
que les reprojeter dans une forme adaptée à l'affichage/l'édition sur une
piste temporelle, puis les réappliquer. Reste volontairement au niveau
scène + quelques événements — pas de micro-keyframes toutes les 100 ms
(voir project_to_timeline)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.scenes.schema import Project, truncate_voice_over_to_duration

# Tolérance flottante pour décider si une durée cible diffère réellement
# de la durée actuelle — évite de déclencher une resynthèse vocale pour
# un bruit d'arrondi négligeable (ex: 4.999999 vs 5.0, lors d'un
# aller-retour JSON).
_DURATION_EPSILON_SEC = 0.05


def project_to_timeline(project: Project) -> dict[str, Any]:
    """Vue dérivée de `project` pour une timeline visuelle :
    - "scenes" : une entrée par scène (`scene_id`, `start`, `duration`) ;
      `start` = position ABSOLUE dans le montage final (voir
      `Project.scene_start_times`), pas relative à la scène.
    - "tracks.mascot" : une entrée par `MascotAction`, avec un `index`
      (position dans `scene.mascot_timeline`) pour la retrouver sans
      ambiguïté dans `timeline_to_project` — plusieurs phases peuvent
      partager le même `action_type` (ex: deux `"idle"`).
    - "tracks.images" : une entrée par `Stroke` de `kind="image"`, même
      convention `index` (position dans `scene.strokes`). Ne couvre QUE
      le moment où l'image apparaît (`start`/`end`, même fondu que le
      reste du moteur) — il n'existe aujourd'hui aucun mécanisme de
      disparition ni de zoom pour une image déjà posée ("la craie posée
      ne bouge plus"), contrairement à ce qu'envisage le document source
      de cette fonctionnalité ; ajouter ces capacités est un chantier à
      part, pas couvert ici.

    Note : `scene_id` est une chaîne (ex: "scene-001") dans le schéma
    réel, pas un entier — une des corrections faites par rapport au
    document d'origine avant intégration."""
    scene_starts = project.scene_start_times()
    scenes = [
        {"scene_id": scene.scene_id, "start": scene_starts[scene.scene_id], "duration": scene.duration_sec}
        for scene in project.scenes
    ]

    mascot_track = [
        {
            "scene_id": scene.scene_id, "index": i,
            "start": action.start_sec, "end": action.end_sec,
            "action": action.action_type,
            "target_x": action.target_x, "target_y": action.target_y,
        }
        for scene in project.scenes
        for i, action in enumerate(scene.mascot_timeline)
    ]

    images_track = [
        {"scene_id": scene.scene_id, "index": i, "start": stroke.start_sec, "end": stroke.end_sec}
        for scene in project.scenes
        for i, stroke in enumerate(scene.strokes)
        if stroke.kind == "image"
    ]

    return {"scenes": scenes, "tracks": {"mascot": mascot_track, "images": images_track}}


@dataclass
class TimelineApplyResult:
    """Résultat de `timeline_to_project` — quelles scènes ont besoin d'un
    aller-retour coûteux (resynthèse vocale, re-rendu), jamais déclenché
    par cette fonction elle-même (aucun appel LLM/TTS/rendu ici) : même
    séparation que `apply_nl_edit_command`/`EditResult` — l'appelant (un
    futur `Api.update_timeline`) orchestre la suite une fois ce résultat
    connu, pour que ce module reste testable sans dépendances réseau."""

    project: Project
    reordered: bool = False
    changed_scene_ids: list[str] = field(default_factory=list)
    voice_changed_scene_ids: list[str] = field(default_factory=list)


def timeline_to_project(timeline: dict[str, Any], project: Project) -> TimelineApplyResult:
    """Applique un TimelineJSON (voir `project_to_timeline`) à `project`,
    EN PLACE (même convention que `apply_nl_edit_command` : le `Project`
    du résultat est le même objet, pas une copie). `scene_id`/`index`
    inconnus ou périmés (le projet a changé depuis la génération du
    TimelineJSON affiché — ex: une scène supprimée entre-temps par ailleurs)
    sont ignorés silencieusement plutôt que de lever une exception."""
    scenes_by_id = {scene.scene_id: scene for scene in project.scenes}
    result = TimelineApplyResult(project=project)

    timeline_scenes = timeline.get("scenes", [])

    # 1) Ordre des scènes : la liste "scenes" du TimelineJSON dicte le
    # nouvel ordre. N'applique le réordonnancement que si l'ensemble des
    # scènes référencées correspond EXACTEMENT à celui du projet — un
    # sous-ensemble (scène manquante dans le JSON reçu) ne doit jamais
    # silencieusement faire disparaître des scènes.
    new_order = [ts["scene_id"] for ts in timeline_scenes if ts.get("scene_id") in scenes_by_id]
    current_order = [scene.scene_id for scene in project.scenes]
    if new_order != current_order and set(new_order) == set(current_order):
        project.scenes = [scenes_by_id[sid] for sid in new_order]
        result.reordered = True

    # 2) Durée : glisser un bloc de scène = même sémantique que la
    # commande NL "raccourcis la scène à Xs" (décision explicite, voir
    # docs/architecture.md) — troncature du texte + durée provisoire, la
    # durée RÉELLE nécessite une resynthèse ultérieure (voir
    # voice_changed_scene_ids ci-dessous, jamais déclenchée ici).
    for ts in timeline_scenes:
        scene = scenes_by_id.get(ts.get("scene_id"))
        if scene is None or ts.get("duration") is None:
            continue
        target_duration = float(ts["duration"])
        if abs(target_duration - scene.duration_sec) <= _DURATION_EPSILON_SEC:
            continue
        truncate_voice_over_to_duration(scene, target_duration)
        result.changed_scene_ids.append(scene.scene_id)
        result.voice_changed_scene_ids.append(scene.scene_id)

    # 3) Mascotte : réapplique les horaires/la cible par (scene_id, index)
    # — n'ajoute ni ne retire de phase (voir add_mascot_timeline/
    # remove_mascot_timeline pour ça), seulement les timestamps.
    for entry in timeline.get("tracks", {}).get("mascot", []):
        scene = scenes_by_id.get(entry.get("scene_id"))
        index = entry.get("index")
        if scene is None or index is None or not (0 <= index < len(scene.mascot_timeline)):
            continue
        action = scene.mascot_timeline[index]
        new_start = float(entry.get("start", action.start_sec))
        new_end = float(entry.get("end", action.end_sec))
        new_x = float(entry["target_x"]) if "target_x" in entry else action.target_x
        new_y = float(entry["target_y"]) if "target_y" in entry else action.target_y
        # Ne marque la scène "changée" que si une valeur diffère
        # réellement — sans quoi un aller-retour project_to_timeline ->
        # timeline_to_project SANS aucune édition rapporterait à tort des
        # scènes changées (cassant l'idempotence attendue).
        if (new_start, new_end, new_x, new_y) != (action.start_sec, action.end_sec, action.target_x, action.target_y):
            action.start_sec, action.end_sec, action.target_x, action.target_y = new_start, new_end, new_x, new_y
            if scene.scene_id not in result.changed_scene_ids:
                result.changed_scene_ids.append(scene.scene_id)

    # 4) Images : réapplique start_sec/end_sec par (scene_id, index).
    for entry in timeline.get("tracks", {}).get("images", []):
        scene = scenes_by_id.get(entry.get("scene_id"))
        index = entry.get("index")
        if scene is None or index is None or not (0 <= index < len(scene.strokes)):
            continue
        stroke = scene.strokes[index]
        if stroke.kind != "image":
            continue  # l'index ne pointe plus vers une image (strokes modifiés entre-temps)
        new_start = float(entry.get("start", stroke.start_sec))
        new_end = float(entry.get("end", stroke.end_sec))
        if (new_start, new_end) != (stroke.start_sec, stroke.end_sec):
            stroke.start_sec, stroke.end_sec = new_start, new_end
            if scene.scene_id not in result.changed_scene_ids:
                result.changed_scene_ids.append(scene.scene_id)

    return result
