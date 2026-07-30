from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.h5p.bookmarks import generate_bookmarks
from app.h5p.interactions import build_interaction
from app.h5p.packager import build_h5p
from app.llm.base import LLMProvider
from app.render.ffmpeg_wrapper import concat_scenes
from app.render.partial_render import render_all, render_scene
from app.scenes.project_file import save_project_file
from app.scenes.schema import Project
from app.tts.base import TTSProvider, VoiceProfile

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

    def __init__(self, llm: LLMProvider, tts: TTSProvider, output_dir: Path):
        self.llm = llm
        self.tts = tts
        self.output_dir = output_dir

    def generate_project(self, source_text: str, theme: str = "chalk_board",
                          on_progress: ProgressCallback = None) -> Project:
        if on_progress:
            on_progress("script", 0.0)
        project = self.llm.generate_script(source_text, theme=theme)
        if on_progress:
            on_progress("script", 1.0)
        return project

    def synthesize_voices(self, project: Project, voice_profile: VoiceProfile,
                           on_progress: ProgressCallback = None) -> None:
        total = len(project.scenes)
        for i, scene in enumerate(project.scenes):
            audio_path, duration = self.tts.synthesize(scene.voice_over, voice_profile)
            scene.audio_path = str(audio_path)
            scene.duration_sec = duration
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
        self.synthesize_voices(project, voice_profile, on_progress)
        video_path = self.render(project, on_progress)
        save_project_file(project, self.output_dir / f"{project.slug}.golpoproj")
        h5p_path = self.export_h5p(project, video_path) if export_h5p else None
        return PipelineResult(project=project, video_path=video_path, h5p_path=h5p_path)

    def rerender_scene(self, project: Project, scene_id: str) -> Path:
        return render_scene(project, scene_id)
