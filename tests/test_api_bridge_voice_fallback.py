"""Tâche C : Api.start_pipeline_from_script retombe explicitement sur un
profil de voix valide (_DEFAULT_VOICE_PROFILE) si voice_profile_name ne
correspond à aucun profil connu, plutôt que de laisser None se propager
silencieusement jusqu'au TTSProvider. Pipeline.finish_generation est
entièrement simulé — aucun vrai appel LLM/TTS/rendu ici."""

from __future__ import annotations

from pathlib import Path

import app.api_bridge as api_bridge
from app.pipeline import PipelineResult
from app.scenes.schema import Project, Scene
from app.tts.base import VoiceProfile


class _FakePipeline:
    def __init__(self):
        self.received_request = None

    def finish_generation(self, project, request, on_progress=None):
        self.received_request = request
        return PipelineResult(
            project=project, project_dir=Path("."), video_path=Path("video.mp4"), h5p_path=None,
        )


def _make_api(monkeypatch, known_profiles):
    api = api_bridge.Api.__new__(api_bridge.Api)  # évite Settings.load() (I/O disque)
    api.settings = None
    api._current_project = None
    api._current_project_path = None
    api._current_project_dir = None
    api._current_video_path = None
    api._current_voice_profile = None
    api._pending_script_project = Project(
        title="t", summary="s", sections=[], scenes=[Scene(scene_id="s0", voice_over="v", duration_sec=5, visual_instruction="")],
    )

    fake_pipeline = _FakePipeline()
    monkeypatch.setattr(api_bridge, "list_voice_profiles", lambda: known_profiles)
    monkeypatch.setattr(api_bridge.Api, "_build_pipeline", lambda self, voice_profile=None: fake_pipeline)
    return api, fake_pipeline


def test_start_pipeline_from_script_uses_matching_profile_when_known(monkeypatch):
    profile = VoiceProfile(name="Voix FR", provider="sapi_local", voice_id="fr-1")
    api, fake_pipeline = _make_api(monkeypatch, [profile])

    api.start_pipeline_from_script([], "Voix FR", export_h5p=False)

    assert fake_pipeline.received_request.voice_profile is profile


def test_start_pipeline_from_script_falls_back_to_default_profile_when_name_unknown(monkeypatch, caplog):
    api, fake_pipeline = _make_api(monkeypatch, [VoiceProfile(name="Voix FR", provider="sapi_local")])

    with caplog.at_level("WARNING"):
        api.start_pipeline_from_script([], "Voix disparue", export_h5p=False)

    used_profile = fake_pipeline.received_request.voice_profile
    assert used_profile is api_bridge._DEFAULT_VOICE_PROFILE
    assert used_profile is not None
    assert any("introuvable" in r.message for r in caplog.records)


def test_start_pipeline_from_script_falls_back_to_default_profile_when_no_profiles_known(monkeypatch):
    api, fake_pipeline = _make_api(monkeypatch, [])

    api.start_pipeline_from_script([], "Peu importe", export_h5p=False)

    assert fake_pipeline.received_request.voice_profile is api_bridge._DEFAULT_VOICE_PROFILE


def test_start_pipeline_from_script_raises_without_pending_script(monkeypatch):
    api, _ = _make_api(monkeypatch, [])
    api._pending_script_project = None

    try:
        api.start_pipeline_from_script([], "Peu importe", export_h5p=False)
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def test_start_pipeline_from_script_applies_edited_voice_over(monkeypatch):
    api, fake_pipeline = _make_api(monkeypatch, [])

    api.start_pipeline_from_script(
        [{"scene_id": "s0", "voice_over": "Texte édité à l'étape 2"}], "Peu importe", export_h5p=False,
    )

    edited_scene = fake_pipeline.received_request is not None and api._current_project.find_scene("s0")
    assert edited_scene.voice_over == "Texte édité à l'étape 2"


def test_start_pipeline_from_script_clears_pending_script_on_success(monkeypatch):
    api, _ = _make_api(monkeypatch, [])

    api.start_pipeline_from_script([], "Peu importe", export_h5p=False)

    assert api._pending_script_project is None
