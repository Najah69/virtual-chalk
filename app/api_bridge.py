from __future__ import annotations

from pathlib import Path
from typing import Any

import webview

from app.ingestion.text_normalizer import normalize_source
from app.llm.deepseek import DeepSeekProvider
from app.llm.gemini import GeminiProvider
from app.llm.openrouter import OpenRouterProvider
from app.pipeline import Pipeline
from app.scenes.project_file import load_project_file
from app.settings import Settings, get_api_key
from app.tts.sapi_local import SapiLocalProvider
from app.tts.voice_profiles import list_voice_profiles


class Api:
    """Pont exposé au JS de l'assistant (ui/js/app.js) via pywebview."""

    def __init__(self):
        self.settings = Settings.load()
        self._current_project = None

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

    LLM_PROVIDERS = {
        "gemini": GeminiProvider,
        "openrouter": OpenRouterProvider,
        "deepseek": DeepSeekProvider,
    }

    def _build_pipeline(self) -> Pipeline:
        provider_key = get_api_key(self.settings.llm_provider) or ""
        provider_cls = self.LLM_PROVIDERS.get(self.settings.llm_provider, OpenRouterProvider)
        llm = provider_cls(api_key=provider_key, model=self.settings.llm_model)
        tts = SapiLocalProvider()
        return Pipeline(llm=llm, tts=tts, output_dir=Path(self.settings.default_output_dir))

    def start_pipeline(self, source: dict[str, Any], voice_profile_name: str, export_h5p: bool) -> dict[str, Any]:
        text = normalize_source(source)
        pipeline = self._build_pipeline()
        profile = next((p for p in list_voice_profiles() if p.name == voice_profile_name), None)

        def on_progress(step: str, fraction: float) -> None:
            webview.windows[0].evaluate_js(
                f"window.onPipelineProgress({step!r}, {fraction})"
            )

        result = pipeline.run(text, profile, export_h5p, on_progress=on_progress)
        self._current_project = result.project
        return {
            "video_path": str(result.video_path),
            "h5p_path": str(result.h5p_path) if result.h5p_path else None,
        }

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
