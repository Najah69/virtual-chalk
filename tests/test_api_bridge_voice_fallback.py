"""Tâche C : Api.start_pipeline retombe explicitement sur un profil de
voix valide (_DEFAULT_VOICE_PROFILE) si voice_profile_name ne correspond à
aucun profil connu, plutôt que de laisser None se propager silencieusement
jusqu'au TTSProvider. Pipeline.run est entièrement simulé — aucun vrai
appel LLM/TTS/rendu ici."""

from __future__ import annotations

from pathlib import Path

import app.api_bridge as api_bridge
from app.pipeline import PipelineResult
from app.scenes.schema import Project
from app.tts.base import VoiceProfile


class _FakePipeline:
    def __init__(self):
        self.received_request = None

    def run(self, request, on_progress=None):
        self.received_request = request
        project = Project(title="t", summary="s", sections=[], scenes=[])
        return PipelineResult(
            project=project, project_dir=Path("."), video_path=Path("video.mp4"), h5p_path=None,
        )


def _make_api(monkeypatch, known_profiles):
    api = api_bridge.Api.__new__(api_bridge.Api)  # évite Settings.load() (I/O disque)
    api.settings = None
    api._current_project = None
    api._current_project_dir = None
    api._current_video_path = None
    api._current_voice_profile = None

    fake_pipeline = _FakePipeline()
    monkeypatch.setattr(api_bridge, "list_voice_profiles", lambda: known_profiles)
    monkeypatch.setattr(api_bridge.Api, "_build_pipeline", lambda self, voice_profile=None: fake_pipeline)
    monkeypatch.setattr(api_bridge, "normalize_source", lambda source: "texte source")
    return api, fake_pipeline


def test_start_pipeline_uses_matching_profile_when_known(monkeypatch):
    profile = VoiceProfile(name="Voix FR", provider="sapi_local", voice_id="fr-1")
    api, fake_pipeline = _make_api(monkeypatch, [profile])

    api.start_pipeline({"type": "text", "content": "x"}, "Voix FR", export_h5p=False)

    assert fake_pipeline.received_request.voice_profile is profile


def test_start_pipeline_falls_back_to_default_profile_when_name_unknown(monkeypatch, caplog):
    api, fake_pipeline = _make_api(monkeypatch, [VoiceProfile(name="Voix FR", provider="sapi_local")])

    with caplog.at_level("WARNING"):
        api.start_pipeline({"type": "text", "content": "x"}, "Voix disparue", export_h5p=False)

    used_profile = fake_pipeline.received_request.voice_profile
    assert used_profile is api_bridge._DEFAULT_VOICE_PROFILE
    assert used_profile is not None
    assert any("introuvable" in r.message for r in caplog.records)


def test_start_pipeline_falls_back_to_default_profile_when_no_profiles_known(monkeypatch):
    api, fake_pipeline = _make_api(monkeypatch, [])

    api.start_pipeline({"type": "text", "content": "x"}, "Peu importe", export_h5p=False)

    assert fake_pipeline.received_request.voice_profile is api_bridge._DEFAULT_VOICE_PROFILE
