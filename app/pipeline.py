from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.h5p.bookmarks import generate_bookmarks
from app.h5p.interactions import build_interaction
from app.h5p.packager import build_h5p
from app.llm.base import LLMProvider
from app.render.diagram_generator import DIAGRAM_LINE_WIDTH, generate_diagram_points
from app.render.ffmpeg_wrapper import concat_scenes
from app.render.partial_render import render_all, render_scene
from app.scenes.project_file import save_project_file
from app.scenes.schema import Project, Scene
from app.tts.base import TTSProvider, VoiceProfile

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str, float], None]]


@dataclass
class PipelineResult:
    project: Project
    video_path: Path
    h5p_path: Optional[Path]


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

    def generate_project(self, source_text: str, theme: str = "chalk_board",
                          on_progress: ProgressCallback = None) -> Project:
        if on_progress:
            on_progress("script", 0.0)
        project = self.llm.generate_script(source_text, theme=theme)
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

    def render(self, project: Project, on_progress: ProgressCallback = None) -> Path:
        scene_videos = render_all(project, on_progress=on_progress)
        final_path = self.output_dir / f"{project.slug}.mp4"
        concat_scenes(scene_videos, final_path)
        return final_path

    def export_h5p(self, project: Project, video_path: Path) -> Path:
        bookmarks = generate_bookmarks(project.scenes)
        interactions = [build_interaction(ex) for ex in project.exercises]
        exercise_types = {ex.exercise_type for ex in project.exercises}
        h5p_path = self.output_dir / f"{project.slug}.h5p"
        build_h5p(video_path, bookmarks, h5p_path, interactions=interactions, exercise_types=exercise_types)
        return h5p_path

    def run(self, source_text: str, voice_profile: VoiceProfile, export_h5p: bool,
            theme: str = "chalk_board", on_progress: ProgressCallback = None) -> PipelineResult:
        project = self.generate_project(source_text, theme, on_progress)
        self.generate_diagrams(project, on_progress)
        self.synthesize_voices(project, voice_profile, on_progress)
        video_path = self.render(project, on_progress)
        save_project_file(project, self.output_dir / f"{project.slug}.golpoproj")
        h5p_path = self.export_h5p(project, video_path) if export_h5p else None
        return PipelineResult(project=project, video_path=video_path, h5p_path=h5p_path)

    def rerender_scene(self, project: Project, scene_id: str) -> Path:
        return render_scene(project, scene_id)
