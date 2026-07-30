from __future__ import annotations

from pathlib import Path
from typing import Any

import webview

import uuid

from app.edit.nl_commands import apply_nl_edit_command
from app.h5p.packager import build_h5p
from app.ingestion.text_normalizer import normalize_source
from app.llm.deepseek import DeepSeekProvider
from app.llm.gemini import GeminiProvider
from app.llm.openrouter import OpenRouterProvider
from app.llm.prompts import DEFAULT_VIDEO_PROFILE, VIDEO_PROFILES
from app.paths import UI_DIR
from app.pipeline import GenerationRequest, Pipeline
from app.scenes.project_file import load_project_file, save_project_file
from app.scenes.schema import Exercise
from app.settings import Settings, get_api_key
from app.tts.base import TTSProvider, VoiceProfile
from app.tts.gemini_tts import GeminiTTSProvider
from app.tts.sapi_local import SapiLocalProvider
from app.tts.voice_profiles import list_voice_profiles

# Repli utilise quand aucun profil de voix n'a ete choisi dans cette session
# (ex: projet charge depuis un .golpoproj sans etre repasse par
# start_pipeline) — gratuit et local, jamais d'appel reseau surprise.
_DEFAULT_VOICE_PROFILE = VoiceProfile(name="Voix Windows par défaut", provider="sapi_local")


class Api:
    """Pont exposé au JS de l'assistant (ui/js/app.js) via pywebview."""

    def __init__(self):
        self.settings = Settings.load()
        self._current_project = None
        self._current_video_path: Path | None = None
        self._current_voice_profile: VoiceProfile | None = None

    def pick_file(self) -> str | None:
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("Documents (*.pdf;*.docx;*.md;*.txt)", "Tous les fichiers (*.*)"),
        )
        return result[0] if result else None

    def pick_output_folder(self) -> str | None:
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

    def get_settings(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self.settings)

    def save_settings(self, data: dict[str, Any]) -> None:
        self.settings = Settings(**{**self.settings.__dict__, **data})
        self.settings.save()

    def list_voice_profiles(self) -> list[dict[str, Any]]:
        return [p.__dict__ for p in list_voice_profiles()]

    def list_video_profiles(self) -> list[dict[str, Any]]:
        return [{"key": key, "label": info["label"]} for key, info in VIDEO_PROFILES.items()]

    LLM_PROVIDERS = {
        "gemini": GeminiProvider,
        "openrouter": OpenRouterProvider,
        "deepseek": DeepSeekProvider,
    }

    def _build_tts(self, voice_profile: VoiceProfile | None) -> TTSProvider:
        if voice_profile and voice_profile.provider == "gemini_tts":
            return GeminiTTSProvider(api_key=get_api_key("gemini") or "")
        return SapiLocalProvider()

    def _build_pipeline(self, voice_profile: VoiceProfile | None = None) -> Pipeline:
        provider_key = get_api_key(self.settings.llm_provider) or ""
        provider_cls = self.LLM_PROVIDERS.get(self.settings.llm_provider, OpenRouterProvider)
        llm = provider_cls(api_key=provider_key, model=self.settings.llm_model)
        tts = self._build_tts(voice_profile)
        return Pipeline(llm=llm, tts=tts, output_dir=Path(self.settings.default_output_dir),
                         diagram_api_key=get_api_key("gemini"))

    def start_pipeline(self, source: dict[str, Any], voice_profile_name: str, export_h5p: bool,
                        theme: str = "chalk_board", script_profile: str = DEFAULT_VIDEO_PROFILE,
                        github_content_kind: str | None = None) -> dict[str, Any]:
        text = normalize_source(source)
        profile = next((p for p in list_voice_profiles() if p.name == voice_profile_name), None)
        pipeline = self._build_pipeline(profile)
        content_kind = github_content_kind if source.get("type") == "github" else None

        def on_progress(step: str, fraction: float) -> None:
            webview.windows[0].evaluate_js(
                f"window.onPipelineProgress({step!r}, {fraction})"
            )

        request = GenerationRequest(
            source_text=text, voice_profile=profile, theme=theme, script_profile=script_profile,
            github_content_kind=content_kind, export_h5p=export_h5p,
        )
        result = pipeline.run(request, on_progress=on_progress)
        self._current_project = result.project
        self._current_video_path = result.video_path
        self._current_voice_profile = profile
        return {
            "video_path": str(result.video_path),
            "h5p_path": str(result.h5p_path) if result.h5p_path else None,
        }

    def scene_start_times(self) -> dict[str, float]:
        if not self._current_project:
            return {}
        return self._current_project.scene_start_times()

    def list_exercises(self) -> list[dict[str, Any]]:
        if not self._current_project:
            return []
        return [ex.__dict__ for ex in self._current_project.exercises]

    def add_exercise(self, exercise_type: str, time_sec: float, title: str, payload: dict[str, Any]) -> str:
        exercise_id = str(uuid.uuid4())
        self._current_project.exercises.append(
            Exercise(exercise_id=exercise_id, exercise_type=exercise_type,
                     time_sec=time_sec, title=title, payload=payload)
        )
        return exercise_id

    def remove_exercise(self, exercise_id: str) -> None:
        self._current_project.exercises = [
            ex for ex in self._current_project.exercises if ex.exercise_id != exercise_id
        ]

    def export_h5p_now(self) -> str:
        """Ré-exporte le .h5p avec les exercices actuels, sans re-rendre la
        vidéo (déjà générée) — ajouter un exercice ne coûte donc aucun
        appel LLM/TTS ni re-rendu."""
        from app.h5p.bookmarks import generate_bookmarks
        from app.h5p.interactions import build_interaction

        project = self._current_project
        bookmarks = generate_bookmarks(project.scenes)
        interactions = [build_interaction(ex) for ex in project.exercises]
        exercise_types = {ex.exercise_type for ex in project.exercises}
        h5p_path = Path(self.settings.default_output_dir) / f"{project.slug}.h5p"
        build_h5p(self._current_video_path, bookmarks, h5p_path,
                  interactions=interactions, exercise_types=exercise_types)
        return str(h5p_path)

    def open_output_folder(self) -> None:
        import subprocess
        subprocess.Popen(["explorer", self.settings.default_output_dir])

    def load_project(self, path: str) -> dict[str, Any]:
        project = load_project_file(Path(path))
        self._current_project = project
        return project.to_dict()

    def rerender_scene(self, scene_id: str) -> str:
        pipeline = self._build_pipeline()
        return str(pipeline.rerender_scene(self._current_project, scene_id))

    def open_editor(self) -> None:
        """Ouvre l'écran Éditeur (ui/editor/) dans une nouvelle fenêtre.
        Le projet à charger n'est pas passé en query string sur l'URL
        file:// (WebView2 échoue à la résoudre — testé, ERR_FILE_NOT_FOUND)
        mais lu par editor.js via get_current_project_path() une fois la
        fenêtre prête, comme le reste des échanges JS<->Python."""
        if not self._current_project:
            raise RuntimeError("Aucun projet à éditer")
        editor_url = UI_DIR / "editor" / "editor.html"
        webview.create_window("Virtual-Chalk — Éditeur", url=editor_url.as_uri(), js_api=self, width=1200, height=760)

    def get_current_project_path(self) -> str | None:
        if not self._current_project:
            return None
        return str(Path(self.settings.default_output_dir) / f"{self._current_project.slug}.golpoproj")

    def apply_edit_command(self, command_text: str) -> dict[str, Any]:
        """Traduit et applique une instruction d'édition en langage naturel
        (app/edit/nl_commands.py), puis ne re-synthétise/re-rend que les
        scènes réellement modifiées — pas de rappel LLM pour le script, pas
        de re-rendu des scènes inchangées."""
        if not self._current_project:
            raise RuntimeError("Aucun projet à éditer")

        pipeline = self._build_pipeline(self._current_voice_profile)
        result = apply_nl_edit_command(self._current_project, command_text, pipeline.llm)
        self._current_project = result.project

        voice_profile = self._current_voice_profile or _DEFAULT_VOICE_PROFILE
        for scene_id in result.voice_changed_scene_ids:
            scene = next(s for s in self._current_project.scenes if s.scene_id == scene_id)
            pipeline.resynthesize_scene(scene, voice_profile)

        scenes_to_rerender = (
            [s.scene_id for s in self._current_project.scenes]
            if result.theme_changed
            else result.changed_scene_ids
        )
        for scene_id in scenes_to_rerender:
            pipeline.rerender_scene(self._current_project, scene_id)

        project_path = Path(self.settings.default_output_dir) / f"{self._current_project.slug}.golpoproj"
        save_project_file(self._current_project, project_path)

        return {
            "project": self._current_project.to_dict(),
            "changed_scene_ids": result.changed_scene_ids,
            "theme_changed": result.theme_changed,
            "skipped_actions": result.skipped_actions,
        }
