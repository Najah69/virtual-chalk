from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.render.layout import resolve_overlaps, text_width
from app.render.theme_registry import palette_for_theme, semantic_color_for_icon, text_color_for_theme

# "Paysage" (format historique, plein écran) — reste le défaut de ces deux
# constantes pour ne pas casser les appelants existants (tests, insertion
# d'image...) qui les importent directement sans connaître l'orientation
# d'un projet particulier ; voir canvas_size() pour le choix effectif fait
# à la génération, qui dépend de Project.mobile_layout.
CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
# "Portrait" (case "mise en page mobile" cochée, voir Project.mobile_layout) :
# vraie vidéo verticale 1080x1920 (pas un simple recadrage optique du
# paysage), format natif pour la lecture téléphone/réseaux sociaux.
CANVAS_WIDTH_PORTRAIT = 1080
CANVAS_HEIGHT_PORTRAIT = 1920
TEXT_STROKE_WIDTH = 90.0
ICON_SIZE = 220.0

# Bande du haut du tableau (pourcentage de la hauteur) dans laquelle un
# élément "text" est considéré comme le titre/l'accroche de la scène —
# voir strokes_from_visual_elements : le PREMIER texte que le LLM place
# dans cette bande est automatiquement recentré horizontalement et épinglé
# (resolve_overlaps ne le déplace plus jamais latéralement), pour corriger
# un retour utilisateur récurrent (titre "décalé" au lieu d'être bien au
# milieu en haut) sans dépendre de la précision du LLM sur x/y.
TITLE_TOP_BAND_PCT = 30.0


def canvas_dimensions(mobile_layout: bool) -> tuple[float, float]:
    """Dimensions du tableau pour une orientation donnée — voir
    Project.canvas_size, qui expose ceci pour un projet déjà chargé."""
    if mobile_layout:
        return CANVAS_WIDTH_PORTRAIT, CANVAS_HEIGHT_PORTRAIT
    return CANVAS_WIDTH, CANVAS_HEIGHT

# Doit rester synchronisé avec les icônes réellement converties dans
# app/render/web_template/icon_paths.js (voir docs/architecture.md pour
# la procédure de conversion depuis Feather Icons + Tabler Icons).
ICON_NAMES = {
    # Feather Icons (vocabulaire de base, meteo/UI générique)
    "sun", "cloud", "cloud-rain", "droplet", "arrow-right", "arrow-up",
    "arrow-down", "thermometer", "wind", "umbrella", "home", "book",
    "check", "refresh-cw", "map-pin", "zap",
    # Tabler Icons : nature/geographie (ajoutees pour couvrir riviere,
    # fleuve, ocean, mer, terre, montagne qui manquaient totalement)
    "mountain", "world", "beach", "anchor", "sailboat", "ship", "tree",
    "plant", "leaf", "seedling", "flower", "fish", "droplets", "ripple",
    "wave-sine", "snowflake", "moon", "stars",
    # Tabler Icons : concepts generaux reutilisables (pas specifiques a
    # un sujet), utiles pour composer des schemas dans n'importe quel domaine
    "flag", "heart", "bulb", "rocket", "clock", "calendar", "chart-bar",
    "brain", "building", "building-bank", "users", "user", "coin", "scale",
}

ANIMATION_SIZE = 220.0

# Taille par defaut d'un diagramme genere (image -> vectorisation) quand le
# LLM ne precise pas width/height : assez grand pour qu'un schema (triangle,
# cycle, carte...) reste lisible sans dominer tout le tableau.
DIAGRAM_DEFAULT_WIDTH_PCT = 32.0
DIAGRAM_DEFAULT_HEIGHT_PCT = 32.0

# Doit rester synchronisé avec window.ANIMATIONS dans
# app/render/web_template/animations.js.
ANIMATION_NAMES = {"falling_rain"}


@dataclass
class Point:
    x: float
    y: float
    # Marque le debut d'un sous-tracé disjoint (ex: le 2e côté d'un
    # triangle, une lettre suivante) : chalk.js/marker_veleda.js sautent le
    # segment entre ce point et le précédent plutôt que de les relier.
    # Toujours False pour texte/icône (points recalculés côté JS de toute
    # façon), n'a de sens que pour les strokes "shape" issus d'un diagramme.
    penUp: bool = False


@dataclass
class Stroke:
    """Unité vectorielle éditable : un tracé (texte converti en contour, ou
    dessin libre). La texture (grain craie, brillance feutre) est calculée
    au rendu à partir de ces données, jamais stockée."""

    points: list[Point]
    color: str
    width: float
    kind: Literal["text", "shape", "icon", "animation", "diagram", "image"] = "shape"
    text: str = ""
    height: float = 0.0
    start_sec: float = 0.0
    end_sec: float = 0.0
    # Uniquement pour kind="image" : l'image (bitmap ou SVG) encodée en
    # data URI base64, jamais un chemin de fichier — le canvas de rendu
    # (web_template/index.html) est chargé en file://, et y dessiner une
    # image chargée depuis un AUTRE file:// le "tainte" (origine distincte
    # pour Chromium), cassant canvas.toDataURL() — donc la capture de
    # toutes les frames suivantes — pour le reste du rendu (voir
    # docs/architecture.md, section Mascotte/Images). points[0] sert
    # d'ancrage haut-gauche (même convention que icon/diagram),
    # width/height la taille d'affichage en pixels canvas.
    image_data: str = ""


@dataclass
class MascotAction:
    """Une phase du comportement de la mascotte animée pendant une scène —
    voir default_mascot_timeline() pour comment un Scene.mascot_timeline
    complet est construit. target_x/target_y sont en pixels canvas (même
    convention que Point.x/y, PAS un pourcentage — voir
    strokes_from_visual_elements qui convertit déjà le pourcentage reçu du
    LLM en pixels avant de construire les Stroke/Point) ; ne sont utilisés
    que par action_type "point", ignorés sinon."""

    action_type: Literal["appear", "wave", "point", "idle", "disappear"]
    start_sec: float
    end_sec: float
    target_x: float = 0.0
    target_y: float = 0.0


@dataclass
class Scene:
    scene_id: str
    voice_over: str
    duration_sec: float
    visual_instruction: str
    notes: str = ""
    strokes: list[Stroke] = field(default_factory=list)
    audio_path: str = ""
    content_hash: str = ""
    # Vide si la mascotte est désactivée pour ce projet (voir
    # Project.mascot_enabled) — jamais rempli par le LLM de génération de
    # script, toujours calculé déterministiquement par
    # default_mascot_timeline() une fois la scène connue (durée, éléments
    # visuels déjà placés).
    mascot_timeline: list[MascotAction] = field(default_factory=list)


@dataclass
class Section:
    title: str
    paragraphs: list[str]


@dataclass
class Exercise:
    """Un exercice H5P (QCM, vrai/faux, texte a trous, glisser les mots)
    positionne a un instant du montage final. `payload` contient les
    champs propres au type (voir app/h5p/interactions.py) ; `time_sec`
    est le temps absolu dans la video concatenee finale, pas relatif a
    une scene."""

    exercise_id: str
    exercise_type: Literal["true_false", "multi_choice", "blanks", "drag_text"]
    time_sec: float
    title: str
    payload: dict[str, Any]


def strokes_from_visual_elements(elements: list[dict[str, Any]], theme: str,
                                  canvas_width: float = CANVAS_WIDTH,
                                  canvas_height: float = CANVAS_HEIGHT) -> list[Stroke]:
    """Convertit les éléments visuels générés par le LLM (mots/courtes
    phrases ou icônes, positionnés en pourcentage du tableau) en Stroke.
    Le tracé réel (contour de lettres/icône) est calculé côté JS au rendu
    (text_to_path.js / icon_to_path.js) — ici on ne fixe que le point
    d'ancrage. Les icônes hors vocabulaire connu (ICON_NAMES) sont
    ignorées plutôt que de planter le rendu sur une sortie LLM imprévue.
    `canvas_width`/`canvas_height` déterminent l'échelle des pourcentages
    reçus — voir Project.canvas_size (dépend de Project.mobile_layout).

    Le LLM choisit x/y en pourcentage sans connaître les dimensions
    réelles de ce qu'il place (largeur du texte selon son contenu,
    empreinte d'une icône/animation) : rien ne garantit qu'un texte ne
    recouvre pas un dessin, ce qu'un professeur ne fait jamais au tableau.
    `resolve_overlaps` écarte donc les éléments dont la boîte englobante
    se chevauche avant de figer leur position finale dans les Stroke.

    Le PREMIER texte placé par le LLM dans la bande du haut
    (TITLE_TOP_BAND_PCT) est traité comme le titre/l'accroche de la
    scène : recentré horizontalement (son ancre, en ligne de base à
    gauche, est décalée de sa largeur estimée / 2) et épinglé
    (`pinned_x`) pour que resolve_overlaps ne le recale jamais
    latéralement — corrige un retour utilisateur ("titre décalé") plutôt
    que d'espérer que le LLM choisisse x=50 de façon fiable."""
    palette = palette_for_theme(theme)
    planned: list[dict[str, Any]] = []
    text_index = 0
    title_assigned = False
    for i, el in enumerate(elements):
        el_type = el.get("type")
        x_pct = float(el.get("x", 50))
        y_pct = float(el.get("y", 50))
        x = (x_pct / 100.0) * canvas_width
        y = (y_pct / 100.0) * canvas_height
        color = palette[i % len(palette)]

        if el_type == "text":
            content = str(el.get("content", "")).strip()
            if not content:
                continue
            text_color = text_color_for_theme(theme, text_index)
            text_index += 1
            entry = {"kind": "text", "x": x, "y": y, "size": TEXT_STROKE_WIDTH, "content": content, "name": "", "color": text_color}
            if not title_assigned and y_pct <= TITLE_TOP_BAND_PCT:
                entry["x"] = canvas_width / 2.0 - text_width(content, TEXT_STROKE_WIDTH) / 2.0
                entry["pinned_x"] = True
                title_assigned = True
            planned.append(entry)
        elif el_type == "icon":
            name = str(el.get("name", "")).strip()
            if name not in ICON_NAMES:
                continue
            icon_color = semantic_color_for_icon(name, theme) or color
            planned.append({"kind": "icon", "x": x, "y": y, "size": ICON_SIZE, "content": "", "name": name, "color": icon_color})
        elif el_type == "animation":
            name = str(el.get("name", "")).strip()
            if name not in ANIMATION_NAMES:
                continue
            anim_color = semantic_color_for_icon(name, theme) or color
            planned.append({"kind": "animation", "x": x, "y": y, "size": ANIMATION_SIZE, "content": "", "name": name, "color": anim_color})
        elif el_type == "diagram":
            description = str(el.get("description", "")).strip()
            if not description:
                continue
            width_px = (float(el.get("width", DIAGRAM_DEFAULT_WIDTH_PCT)) / 100.0) * canvas_width
            height_px = (float(el.get("height", DIAGRAM_DEFAULT_HEIGHT_PCT)) / 100.0) * canvas_height
            planned.append({"kind": "diagram", "x": x, "y": y, "size": width_px, "height": height_px,
                             "content": description, "name": "", "color": color})

    resolve_overlaps(planned, canvas_width, canvas_height)

    return [
        Stroke(points=[Point(el["x"], el["y"])], color=el["color"], width=el["size"],
               height=el.get("height", 0.0), kind=el["kind"],
               text=el["content"] if el["kind"] in ("text", "diagram") else el["name"])
        for el in planned
    ]


# Durée (s) de chaque phase d'entrée/sortie de la mascotte — assez courte
# pour ne pas manger le temps utile d'une scène courte, mais perceptible.
MASCOT_TRANSITION_SEC = 0.6
# Durée minimale (s) qu'il doit rester après la phase d'apparition pour
# que la mascotte tente de désigner un élément ("point") ; en dessous, la
# scène est trop courte pour que ce geste soit lisible, elle reste en idle.
MASCOT_MIN_POINT_WINDOW_SEC = 1.0


def default_mascot_timeline(scene: Scene, greet: bool = False) -> list[MascotAction]:
    """Construit un enchaînement de phases (apparition, salut ou pointage
    vers un élément déjà placé, attente, disparition) déterministe à
    partir de ce qui est déjà connu de la scène (durée, éléments visuels
    déjà positionnés) — jamais d'appel LLM supplémentaire : la mascotte
    n'invente aucun contenu, elle ne fait que réagir à ce qui existe déjà.

    `greet` distingue la toute première scène du projet (salut de
    bienvenue) des suivantes (comportement neutre)."""
    duration = max(scene.duration_sec, 0.1)
    appear_end = min(MASCOT_TRANSITION_SEC, duration * 0.25)
    disappear_start = max(appear_end, duration - min(MASCOT_TRANSITION_SEC, duration * 0.25))

    timeline = [MascotAction(action_type="appear", start_sec=0.0, end_sec=appear_end)]

    cursor = appear_end
    if greet and disappear_start - cursor > MASCOT_MIN_POINT_WINDOW_SEC:
        wave_end = min(cursor + MASCOT_TRANSITION_SEC * 1.5, disappear_start)
        timeline.append(MascotAction(action_type="wave", start_sec=cursor, end_sec=wave_end))
        cursor = wave_end

    # Pointe vers le premier élément visuel non textuel déjà positionné
    # (icône, animation, diagramme) : ancrage direct sur son point d'ancrage
    # (déjà en pourcentage du tableau, même convention que MascotAction).
    target = next((s for s in scene.strokes if s.kind in ("icon", "animation", "diagram")), None)
    if target is not None and disappear_start - cursor > MASCOT_MIN_POINT_WINDOW_SEC:
        point_end = cursor + (disappear_start - cursor) * 0.5
        anchor = target.points[0]
        timeline.append(MascotAction(
            action_type="point", start_sec=cursor, end_sec=point_end,
            target_x=anchor.x, target_y=anchor.y,
        ))
        cursor = point_end

    if disappear_start > cursor:
        timeline.append(MascotAction(action_type="idle", start_sec=cursor, end_sec=disappear_start))

    timeline.append(MascotAction(action_type="disappear", start_sec=disappear_start, end_sec=duration))
    return timeline


def add_mascot_timeline(project: "Project") -> None:
    """Calcule et affecte scene.mascot_timeline pour CHAQUE scène du
    projet (écrase un éventuel timeline existant) — appelé une fois à la
    génération initiale si mascot_enabled, ou par l'action d'édition NL
    "toggle_mascot" pour (ré)activer la mascotte après coup. Idempotent :
    rappelable sans effet de bord cumulatif."""
    for i, scene in enumerate(project.scenes):
        scene.mascot_timeline = default_mascot_timeline(scene, greet=(i == 0))
    project.mascot_enabled = True


def remove_mascot_timeline(project: "Project") -> None:
    """Inverse de add_mascot_timeline : vide le timeline de chaque scène
    plutôt que de les laisser en place désactivés — un timeline non vide
    mais ignoré au rendu serait un état incohérent à faire vivre dans le
    .vchalk."""
    for scene in project.scenes:
        scene.mascot_timeline = []
    project.mascot_enabled = False


@dataclass
class Project:
    title: str
    summary: str
    sections: list[Section]
    scenes: list[Scene]
    theme: str = "chalk_board"
    exercises: list[Exercise] = field(default_factory=list)
    mascot_enabled: bool = False
    # Format vertical 1080x1920 (case "mise en page mobile" cochée par
    # défaut à l'étape 1 de l'assistant) plutôt que le paysage 1920x1080
    # historique — voir canvas_size(). Décidé une fois pour toutes à la
    # génération (from_llm_response) : les strokes sont figés en pixels
    # absolus dès cet instant (voir strokes_from_visual_elements), donc
    # changer l'orientation après coup nécessiterait de relayouter toute
    # la scène, pas juste de recolorer comme pour un changement de thème
    # (_recolor_strokes_for_theme) — contrainte assumée, cohérente avec le
    # profil de vidéo (aussi figé à l'étape 1, voir ui/index.html).
    mobile_layout: bool = True

    @property
    def slug(self) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        return base or "virtual-chalk-project"

    @property
    def canvas_size(self) -> tuple[float, float]:
        return canvas_dimensions(self.mobile_layout)

    def find_scene(self, scene_id: str) -> Scene | None:
        """Retrouve une scène par id, ou None si absente — jamais de
        StopIteration non attrapée. Utile quand le scene_id vient d'une
        source qui peut référencer une scène qui n'existe plus (ex: une
        action d'édition NL qui en supprime une après qu'une action
        précédente de la même commande l'a marquée comme modifiée)."""
        return next((s for s in self.scenes if s.scene_id == scene_id), None)

    def scene_start_times(self) -> dict[str, float]:
        """Instant absolu (dans la video concatenee finale) ou commence
        chaque scene — utilise par l'UI pour convertir un point choisi
        dans une scene en temps absolu pour un exercice."""
        starts = {}
        cursor = 0.0
        for scene in self.scenes:
            starts[scene.scene_id] = cursor
            cursor += scene.duration_sec
        return starts

    @classmethod
    def from_llm_response(cls, data: dict[str, Any], theme: str = "chalk_board",
                           mobile_layout: bool = True) -> "Project":
        canvas_width, canvas_height = canvas_dimensions(mobile_layout)
        sections = [Section(**s) for s in data.get("sections", [])]
        scenes = [
            Scene(
                scene_id=s["scene_id"],
                voice_over=s["voice_over"],
                duration_sec=float(s.get("duration_sec", 10)),
                visual_instruction=s.get("visual_instruction", ""),
                notes=s.get("notes", ""),
                strokes=strokes_from_visual_elements(s.get("visual_elements", []), theme, canvas_width, canvas_height),
            )
            for s in data.get("script", [])
        ]
        title = (data.get("summary", "")[:60] or "Projet Virtual-Chalk").strip()
        return cls(title=title, summary=data.get("summary", ""), sections=sections, scenes=scenes, theme=theme,
                    mobile_layout=mobile_layout)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        sections = [Section(**s) for s in data.get("sections", [])]
        scenes = []
        for s in data.get("scenes", []):
            strokes = [
                Stroke(points=[Point(**p) for p in st["points"]], color=st["color"],
                       width=st["width"], kind=st.get("kind", "shape"), text=st.get("text", ""),
                       height=st.get("height", 0.0), start_sec=st.get("start_sec", 0.0),
                       end_sec=st.get("end_sec", 0.0), image_data=st.get("image_data", ""))
                for st in s.get("strokes", [])
            ]
            mascot_timeline = [MascotAction(**m) for m in s.get("mascot_timeline", [])]
            scenes.append(Scene(**{**s, "strokes": strokes, "mascot_timeline": mascot_timeline}))
        exercises = [Exercise(**ex) for ex in data.get("exercises", [])]
        return cls(
            title=data["title"], summary=data["summary"], sections=sections,
            scenes=scenes, theme=data.get("theme", "chalk_board"), exercises=exercises,
            mascot_enabled=data.get("mascot_enabled", False),
            # Un .vchalk enregistré avant cette fonctionnalité n'a pas ce
            # champ — ses strokes ont été figés en pixels absolus pour le
            # SEUL format qui existait alors (paysage 1920x1080, voir
            # CANVAS_WIDTH/HEIGHT), donc le repli doit être False, pas le
            # défaut True utilisé pour une NOUVELLE génération
            # (from_llm_response) : réinterpréter ces strokes en portrait
            # sans les relayouter les ferait déborder du nouveau cadre.
            mobile_layout=data.get("mobile_layout", False),
        )
