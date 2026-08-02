"""Tâche 3 du blueprint Timeline & Anime.js : Api.update_timeline orchestre
timeline_to_project (Tâche 1) — resynthèse uniquement des scènes que
voice_changed_scene_ids désigne, un seul re-rendu si quoi que ce soit a
changé (y compris un simple réordonnancement, qui ne change le hash
d'aucune scène). Pipeline entièrement simulé — aucun vrai appel LLM/TTS/
ffmpeg ici."""

from __future__ import annotations

from pathlib import Path

import app.api_bridge as api_bridge
from app.scenes.schema import Project, Scene


class _FakePipeline:
    def __init__(self):
        self.resynthesized_scene_ids: list[str] = []
        self.render_calls = 0

    def resynthesize_scene(self, scene, voice_profile):
        self.resynthesized_scene_ids.append(scene.scene_id)
        scene.duration_sec = 3.0

    def render(self, project, out_dir, on_progress=None):
        self.render_calls += 1
        return Path("video.mp4")


def _make_api(monkeypatch, scenes):
    api = api_bridge.Api.__new__(api_bridge.Api)  # évite Settings.load() (I/O disque)
    api._current_project = Project(title="t", summary="s", sections=[], scenes=scenes)
    api._current_project_dir = Path(".")
    api._current_project_path = None
    api._current_video_path = None
    api._current_voice_profile = None

    fake_pipeline = _FakePipeline()
    monkeypatch.setattr(api_bridge.Api, "_build_pipeline", lambda self, voice_profile=None: fake_pipeline)
    monkeypatch.setattr(api_bridge, "save_project_file", lambda project, path: None)
    monkeypatch.setattr(api_bridge, "serve_media", lambda path: f"http://served/{path}")
    return api, fake_pipeline


def _scenes():
    return [
        Scene(scene_id="scene-001", voice_over="Premiere phrase. Deuxieme phrase plus longue.",
              duration_sec=10.0, visual_instruction=""),
        Scene(scene_id="scene-002", voice_over="Autre scene.", duration_sec=6.0, visual_instruction=""),
    ]


def test_update_timeline_raises_without_current_project(monkeypatch):
    api, _ = _make_api(monkeypatch, _scenes())
    api._current_project = None

    try:
        api.update_timeline({"scenes": []})
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def test_update_timeline_reorder_only_renders_but_never_resynthesizes(monkeypatch):
    api, fake_pipeline = _make_api(monkeypatch, _scenes())
    timeline = {"scenes": [{"scene_id": "scene-002"}, {"scene_id": "scene-001"}]}

    result = api.update_timeline(timeline)

    assert [s.scene_id for s in api._current_project.scenes] == ["scene-002", "scene-001"]
    assert fake_pipeline.resynthesized_scene_ids == []
    assert fake_pipeline.render_calls == 1
    assert result["reordered"] is True
    assert result["video_url"] == "http://served/video.mp4"


def test_update_timeline_duration_change_resynthesizes_and_renders(monkeypatch):
    api, fake_pipeline = _make_api(monkeypatch, _scenes())
    timeline = {"scenes": [{"scene_id": "scene-001", "duration": 2.0}]}

    result = api.update_timeline(timeline)

    assert fake_pipeline.resynthesized_scene_ids == ["scene-001"]
    assert fake_pipeline.render_calls == 1
    assert result["changed_scene_ids"] == ["scene-001"]
    # La durée retournée est celle de la VRAIE resynthèse (simulée à 3.0s
    # ici), pas la valeur provisoire posée par truncate_voice_over_to_duration.
    assert api._current_project.find_scene("scene-001").duration_sec == 3.0


def test_update_timeline_no_changes_still_saves_but_never_renders(monkeypatch):
    api, fake_pipeline = _make_api(monkeypatch, _scenes())
    # Round-trip sans édition (voir test_timeline.py::test_round_trip_with_no_edits_reports_no_changes).
    from app.scenes.timeline import project_to_timeline
    timeline = project_to_timeline(api._current_project)

    result = api.update_timeline(timeline)

    assert fake_pipeline.resynthesized_scene_ids == []
    assert fake_pipeline.render_calls == 0
    assert result["changed_scene_ids"] == []
    assert result["reordered"] is False
    assert result["video_url"] is None  # jamais rendu -> _current_video_path toujours None


def test_update_timeline_returns_up_to_date_project_dict(monkeypatch):
    api, _ = _make_api(monkeypatch, _scenes())
    timeline = {"scenes": [{"scene_id": "scene-001", "duration": 2.0}]}

    result = api.update_timeline(timeline)

    assert result["project"]["scenes"][0]["scene_id"] == "scene-001"
    assert result["project"]["scenes"][0]["duration_sec"] == 3.0
