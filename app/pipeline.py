from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from app.critique.visual_critique import run_critique_loop
from app.h5p.bookmarks import generate_bookmarks
from app.h5p.interactions import build_interaction
from app.h5p.packager import build_h5p
from app.library.asset_library import add_asset
from app.llm.base import LLMProvider
from app.llm.gemini import GeminiProvider
from app.llm.prompts import DEFAULT_VIDEO_PROFILE
from app.render.capture import FrameCapture
from app.render.diagram_generator import DIAGRAM_LINE_WIDTH, generate_diagram_points
from app.render.ffmpeg_wrapper import concat_scenes
from app.render.partial_render import render_all, render_scene
from app.render.theme_registry import palette_for_theme
from app.render.window_registry import get_render_window
from app.scenes.project_file import PROJECT_FILE_EXTENSION, save_project_file
from app.scenes.schema import Project, Scene, add_mascot_timeline
from app.tts.base import TTSProvider, VoiceProfile

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str, float], None]]

# Cadre de placement neutre passe a generate_diagram_points pour une
# pre-generation vers la bibliotheque (voir Pipeline.generate_library_diagrams)
# : sans incidence sur le resultat stocke, seule la boite englobante REELLE
# des points obtenus compte une fois passee a asset_library.add_asset (qui
# normalise a partir de cette boite, pas du cadre demande a Gemini).
_LIBRARY_PLACEMENT_SIZE = 400.0


DEFAULT_LANGUAGE = "fr"


@dataclass
class PipelineResult:
    project: Project
    project_dir: Path
    video_path: Path
    h5p_path: Optional[Path]


@dataclass
class GenerationRequest:
    """Regroupe les paramètres d'une génération initiale — évite de faire
    grossir indéfiniment la signature de Pipeline.run()/generate_project()
    à chaque nouvelle option (thème, profil, angle GitHub...). Les étapes
    suivantes du pipeline (diagrammes, voix, rendu, export, édition NL)
    continuent de prendre le Project directement : elles n'ont pas besoin
    de ces paramètres d'entrée, seulement du résultat de generate_project()."""

    source_text: str
    voice_profile: VoiceProfile
    theme: str = "chalk_board"
    script_profile: str = DEFAULT_VIDEO_PROFILE
    github_content_kind: str | None = None
    export_h5p: bool = False
    mascot_enabled: bool = False
    # Format vertical 1080x1920 pour lecture téléphone (voir
    # Project.mobile_layout) — décidé à l'étape 1 de l'assistant, avant
    # l'appel LLM (generate_project), car les strokes sont figés en
    # pixels absolus dès cet instant.
    mobile_layout: bool = True
    # Boucle d'auto-critique visuelle (proposition explicite de
    # l'utilisateur, voir app/critique/visual_critique.py) : coûte un
    # appel LLM vision + une capture par scène jugée insuffisante et par
    # itération (jusqu'à MAX_CRITIQUE_ITERATIONS), en plus du coût de
    # génération normal — jamais activé par défaut.
    auto_critique: bool = False


class Pipeline:
    """Orchestre le flux complet : ingestion -> script -> voix -> rendu -> export.

    Ne fait qu'un seul appel LLM par génération de script ; les étapes
    suivantes ne consomment aucun token (édition locale, re-rendu ciblé).
    """

    def __init__(self, llm: LLMProvider, tts: TTSProvider, output_dir: Path,
                 diagram_api_key: str | None = None):
        self.llm = llm
        self.tts = tts
        self.output_dir = output_dir
        # Les diagrammes passent toujours par Gemini (generation d'image),
        # independamment du fournisseur LLM choisi pour le script — meme
        # logique que _build_tts pour la voix Gemini dans api_bridge.py.
        self.diagram_api_key = diagram_api_key

    def generate_project(self, request: GenerationRequest, on_progress: ProgressCallback = None) -> Project:
        if on_progress:
            on_progress("script", 0.0)
        project = self.llm.generate_script(
            request.source_text, theme=request.theme, script_profile=request.script_profile,
            github_content_kind=request.github_content_kind, mobile_layout=request.mobile_layout,
        )
        if on_progress:
            on_progress("script", 1.0)
        return project

    def generate_diagrams(self, project: Project, on_progress: ProgressCallback = None) -> None:
        """Resout les strokes 'diagram' (description en langage naturel,
        posee par le LLM du script) en vrai trace vectoriel : genere une
        image via Gemini puis la vectorise en contours (voir
        app/render/diagram_generator.py). Sans cle API Gemini configuree,
        ou si un appel echoue pour une scene donnee, le diagramme concerne
        est simplement retire plutot que de faire echouer toute la
        generation — un schema manquant sur une scene reste moins grave
        qu'une video qui ne se termine pas."""
        pending = [
            (scene, stroke) for scene in project.scenes for stroke in scene.strokes
            if stroke.kind == "diagram"
        ]
        if not pending:
            return
        for i, (scene, stroke) in enumerate(pending):
            try:
                if not self.diagram_api_key:
                    raise RuntimeError("Pas de cle API Gemini configuree pour les diagrammes")
                anchor = stroke.points[0]
                points = generate_diagram_points(
                    stroke.text, self.diagram_api_key, anchor.x, anchor.y, stroke.width, stroke.height,
                )
                if points:
                    stroke.points = points
                    # stroke.width/height portaient le cadre de placement
                    # (pixels du tableau) pour la vectorisation ci-dessus ;
                    # on les remet a une epaisseur de trait normale avant
                    # que le stroke ne passe en kind="shape" et soit dessine
                    # tel quel par chalk.js/marker_veleda.js.
                    stroke.width = DIAGRAM_LINE_WIDTH
                    stroke.height = 0.0
                    stroke.kind = "shape"
                else:
                    scene.strokes.remove(stroke)
            except Exception:
                logger.exception("Echec de generation du diagramme %r", stroke.text)
                scene.strokes.remove(stroke)
            if on_progress:
                on_progress("diagram", (i + 1) / len(pending))

    def generate_library_diagrams(self, descriptions: list[str],
                                   on_progress: ProgressCallback = None) -> dict[str, Any]:
        """Pré-génère des schémas vectorisés directement dans la
        Bibliothèque personnelle (app/library/asset_library.py), HORS de
        tout Project — action explicite de l'utilisateur (voir
        Api.pregenerate_library_diagrams), jamais appelée depuis
        generate_project/finish_generation. `descriptions` vient de
        app/library/diagram_suggestions.py, déjà relue/filtrée par
        l'utilisateur avant cet appel.

        Couleur fixée sur la palette craie (thème provisoire, même logique
        que generate_script avant que le vrai thème ne soit choisi à
        l'étape 3 de l'assistant) — l'utilisateur peut recolorer
        manuellement une fois l'élément placé dans une scène.

        Dégradation gracieuse PAR description, même logique que
        generate_diagrams : un échec individuel (réseau, vectorisation
        vide...) ne doit jamais interrompre le reste du lot déjà payé en
        appels Gemini."""
        if not self.diagram_api_key:
            raise RuntimeError("Pas de cle API Gemini configuree pour les diagrammes")
        color = palette_for_theme("chalk_board")[0]
        added: list[dict[str, Any]] = []
        failed_count = 0
        for i, description in enumerate(descriptions):
            try:
                points = generate_diagram_points(
                    description, self.diagram_api_key,
                    0.0, 0.0, _LIBRARY_PLACEMENT_SIZE, _LIBRARY_PLACEMENT_SIZE,
                )
                if not points:
                    raise RuntimeError("Vectorisation vide")
                xs = [p.x for p in points]
                ys = [p.y for p in points]
                bbox = {"x": min(xs), "y": min(ys), "w": max(xs) - min(xs), "h": max(ys) - min(ys)}
                raw_points = [{"x": p.x, "y": p.y, "penUp": p.penUp} for p in points]
                asset = add_asset(description, "shape", color, raw_points, bbox)
                added.append(asset.to_dict())
            except Exception:
                logger.exception("Echec de pre-generation du schema %r", description)
                failed_count += 1
            if on_progress:
                on_progress("library_diagram", (i + 1) / len(descriptions))
        return {"added": added, "failed_count": failed_count}

    def resynthesize_scene(self, scene: Scene, voice_profile: VoiceProfile) -> None:
        """Re-synthétise la voix d'UNE scène (contrairement à
        synthesize_voices, qui traite tout le projet) — utilisé par
        l'édition NL (app/edit/nl_commands.py) et le mode brouillon/final,
        pour ne payer/attendre que ce qui a réellement changé plutôt que de
        rappeler le TTS sur des scènes inchangées."""
        audio_path, duration = self.tts.synthesize(scene.voice_over, voice_profile)
        scene.audio_path = str(audio_path)
        scene.duration_sec = duration

    def synthesize_voices(self, project: Project, voice_profile: VoiceProfile,
                           on_progress: ProgressCallback = None) -> None:
        total = len(project.scenes)
        for i, scene in enumerate(project.scenes):
            self.resynthesize_scene(scene, voice_profile)
            if on_progress:
                on_progress("voice", (i + 1) / total)

    def run_visual_critique(self, project: Project, on_progress: ProgressCallback = None) -> list[str]:
        """Boucle d'auto-critique visuelle optionnelle (voir
        GenerationRequest.auto_critique, app/critique/visual_critique.py) —
        placée entre la synthèse vocale et le premier rendu réel dans
        finish_generation : les éléments visuels ajoutés ici sont donc déjà
        inclus dans le TOUT PREMIER encodage ffmpeg, pas besoin de
        ré-encoder après coup une fois la boucle terminée.

        Utilise TOUJOURS Gemini pour l'analyse d'image (self.diagram_api_key),
        indépendamment du fournisseur LLM choisi pour le script — même
        logique que generate_diagrams : la vision multimodale n'est pas
        disponible sur tous les fournisseurs (voir
        LLMProvider._complete_with_images), et la clé Gemini est de toute
        façon déjà requise pour les diagrammes, donc ne pas en redemander
        une deuxième distincte pour cette fonctionnalité."""
        if not self.diagram_api_key:
            logger.warning("Auto-critique visuelle ignorée : pas de clé API Gemini configurée")
            return []
        vision_llm = GeminiProvider(api_key=self.diagram_api_key, model="")
        capture = FrameCapture(get_render_window())
        return run_critique_loop(vision_llm, project, capture, on_progress)

    def project_dir(self, slug: str, lang: str = DEFAULT_LANGUAGE) -> Path:
        """Répertoire de sortie d'un projet pour une langue donnée : un
        dossier par projet, un sous-dossier par langue à l'intérieur
        (`{output_dir}/{slug}/{lang}/`) — évite que toutes les vidéos
        générées (et leurs traductions) se retrouvent mélangées à plat
        dans un seul dossier."""
        path = self.output_dir / slug / lang
        path.mkdir(parents=True, exist_ok=True)
        return path

    def render(self, project: Project, out_dir: Path, on_progress: ProgressCallback = None) -> Path:
        scene_videos = render_all(project, out_dir / "scenes", on_progress=on_progress)
        # Nommé d'après le slug du projet (pas "video.mp4" générique) : le
        # dossier de sortie porte déjà ce nom (voir project_dir), mais le
        # fichier lui-même doit rester identifiable une fois déplacé/
        # partagé isolément, hors de son dossier.
        final_path = out_dir / f"{project.slug}.mp4"
        concat_scenes(scene_videos, final_path)
        return final_path

    def export_h5p(self, project: Project, video_path: Path, out_dir: Path) -> Path:
        bookmarks = generate_bookmarks(project.scenes)
        interactions = [build_interaction(ex) for ex in project.exercises]
        exercise_types = {ex.exercise_type for ex in project.exercises}
        h5p_path = out_dir / f"{project.slug}.h5p"
        build_h5p(video_path, bookmarks, h5p_path, interactions=interactions, exercise_types=exercise_types)
        return h5p_path

    def run(self, request: GenerationRequest, on_progress: ProgressCallback = None) -> PipelineResult:
        project = self.generate_project(request, on_progress)
        return self.finish_generation(project, request, on_progress)

    def finish_generation(self, project: Project, request: GenerationRequest,
                           on_progress: ProgressCallback = None) -> PipelineResult:
        """Termine une génération à partir d'un script déjà produit
        (diagrammes, mascotte, voix, rendu, export) — scindé de `run` pour
        permettre de revoir/éditer le script (voir Api.generate_script,
        étape "2. Script" de l'assistant) entre la génération du texte et
        le reste, coûteux (TTS + rendu), sans avoir à tout régénérer.
        `request.source_text`/`script_profile`/`github_content_kind` ne
        sont pas relus ici (déjà consommés par generate_project)."""
        self.generate_diagrams(project, on_progress)
        if request.mascot_enabled:
            # Après generate_diagrams (et non avant) : un diagramme retiré
            # faute de génération réussie (voir generate_diagrams) ne doit
            # pas être choisi comme cible de "point" par la mascotte.
            add_mascot_timeline(project)
        self.synthesize_voices(project, request.voice_profile, on_progress)
        if request.auto_critique:
            # AVANT le rendu (pas après) : les éléments ajoutés ici sont
            # inclus dès le premier encodage ffmpeg, voir run_visual_critique.
            self.run_visual_critique(project, on_progress)
        out_dir = self.project_dir(project.slug, DEFAULT_LANGUAGE)
        video_path = self.render(project, out_dir, on_progress)
        save_project_file(project, out_dir / f"project{PROJECT_FILE_EXTENSION}")
        h5p_path = self.export_h5p(project, video_path, out_dir) if request.export_h5p else None
        return PipelineResult(project=project, project_dir=out_dir, video_path=video_path, h5p_path=h5p_path)

    def rerender_scene(self, project: Project, scene_id: str, out_dir: Path) -> Path:
        """Force le re-rendu d'UNE scène (ignore son cache) puis reconstruit
        la vidéo finale complète à partir de toutes les scènes (`render`
        réutilise le cache pour celles qui n'ont pas changé) — corrige un
        comportement précédent où le clip re-rendu n'était jamais réintégré
        au montage final, qui restait donc périmé après un re-rendu ciblé."""
        render_scene(project, scene_id, out_dir / "scenes")
        return self.render(project, out_dir)
