"""Backend de l'éditeur WYSIWYG (ui/editor/editor_canvas.js) :
Api.update_scene_strokes (persiste l'état édité côté client avant un
re-rendu) et Api.rerender_scene (doit désormais sauvegarder le projet,
bug préexistant trouvé en construisant cette fonctionnalité — la vidéo
se mettait à jour mais pas le .vchalk). Aucun vrai appel
pywebview/fichier/rendu réel ici."""

from __future__ import annotations

from pathlib import Path

import app.api_bridge as api_bridge
from app.scenes.schema import Point, Project, Scene, Stroke


def _make_scene(scene_id="s0") -> Scene:
    return Scene(scene_id=scene_id, voice_over="v", duration_sec=6.0, visual_instruction="")


class _FakePipeline:
    def __init__(self):
        self.rerendered_scene_id = None
        self.resynthesized_scene = None

    def rerender_scene(self, project, scene_id, out_dir):
        self.rerendered_scene_id = scene_id
        return Path("video.mp4")

    def render(self, project, out_dir):
        self.rendered_project = project
        return Path("video.mp4")

    def resynthesize_scene(self, scene, voice_profile):
        self.resynthesized_scene = scene
        scene.audio_path = "/fake/audio.wav"
        scene.duration_sec = len(scene.voice_over) * 0.1  # durée factice mais déterministe


def _make_api(monkeypatch, project, tmp_path, project_path=None):
    api = api_bridge.Api.__new__(api_bridge.Api)
    api.settings = None
    api._current_project = project
    api._current_project_path = project_path
    api._current_project_dir = tmp_path
    api._current_video_path = None
    api._current_voice_profile = None

    fake_pipeline = _FakePipeline()
    monkeypatch.setattr(api_bridge.Api, "_build_pipeline", lambda self, voice_profile=None: fake_pipeline)
    return api, fake_pipeline


def test_update_scene_strokes_replaces_scene_strokes(monkeypatch, tmp_path):
    scene = _make_scene()
    scene.strokes = [Stroke(points=[Point(0, 0)], color="#fff", width=10.0, kind="shape")]
    project = Project(title="t", summary="s", sections=[], scenes=[scene])
    api, _ = _make_api(monkeypatch, project, tmp_path)

    new_strokes = [
        {"points": [{"x": 100, "y": 200}], "color": "#ffe66d", "width": 90.0, "kind": "text", "text": "Bonjour"},
        {"points": [{"x": 10, "y": 20}, {"x": 30, "y": 40, "penUp": True}], "color": "#fff", "width": 5.0, "kind": "shape"},
    ]

    api.update_scene_strokes("s0", new_strokes)

    result_strokes = api._current_project.find_scene("s0").strokes
    assert len(result_strokes) == 2
    assert result_strokes[0].kind == "text"
    assert result_strokes[0].text == "Bonjour"
    assert result_strokes[0].points[0].x == 100
    assert result_strokes[0].points[0].y == 200
    assert result_strokes[1].points[1].penUp is True


def test_update_scene_strokes_raises_for_unknown_scene(monkeypatch, tmp_path):
    project = Project(title="t", summary="s", sections=[], scenes=[_make_scene("s0")])
    api, _ = _make_api(monkeypatch, project, tmp_path)

    try:
        api.update_scene_strokes("does-not-exist", [])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_rerender_scene_saves_the_project_file(monkeypatch, tmp_path):
    """Régression : rerender_scene ne sauvegardait jamais le .vchalk — la
    vidéo se mettait à jour mais toute édition (WYSIWYG ou champ de
    propriété) semblait perdue à la prochaine ouverture du projet."""
    project = Project(title="t", summary="s", sections=[], scenes=[_make_scene("s0")])
    api, fake_pipeline = _make_api(monkeypatch, project, tmp_path)

    saved = []
    monkeypatch.setattr(api_bridge, "save_project_file", lambda proj, path: saved.append((proj, path)))

    video_path = api.rerender_scene("s0")

    assert video_path == "video.mp4"
    assert fake_pipeline.rerendered_scene_id == "s0"
    assert len(saved) == 1
    assert saved[0][0] is project
    assert saved[0][1] == tmp_path / "project.vchalk"


def test_rerender_scene_saves_to_exact_opened_path_when_renamed(monkeypatch, tmp_path):
    project = Project(title="t", summary="s", sections=[], scenes=[_make_scene("s0")])
    renamed_path = tmp_path / "mon_projet.vchalk"
    api, _ = _make_api(monkeypatch, project, tmp_path, project_path=renamed_path)

    saved = []
    monkeypatch.setattr(api_bridge, "save_project_file", lambda proj, path: saved.append(path))

    api.rerender_scene("s0")

    assert saved == [renamed_path]


def test_update_scene_voice_over_resynthesizes_and_updates_duration(monkeypatch, tmp_path):
    project = Project(title="t", summary="s", sections=[], scenes=[_make_scene("s0")])
    api, fake_pipeline = _make_api(monkeypatch, project, tmp_path)

    result = api.update_scene_voice_over("s0", "Un nouveau texte de narration plus long.")

    scene = api._current_project.find_scene("s0")
    assert scene.voice_over == "Un nouveau texte de narration plus long."
    assert fake_pipeline.resynthesized_scene is scene
    assert result["duration_sec"] == scene.duration_sec
    assert scene.duration_sec != 6.0  # la durée d'origine a bien été recalculée


def test_update_scene_voice_over_raises_for_unknown_scene(monkeypatch, tmp_path):
    project = Project(title="t", summary="s", sections=[], scenes=[_make_scene("s0")])
    api, _ = _make_api(monkeypatch, project, tmp_path)

    try:
        api.update_scene_voice_over("does-not-exist", "x")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_rerender_all_uses_pipeline_render_not_per_scene_loop(monkeypatch, tmp_path):
    """rerender_all doit passer par Pipeline.render (cache par
    content_hash, ne ré-encode que ce qui a changé) plutôt que de forcer
    un ré-encodage de chaque scène une par une."""
    project = Project(title="t", summary="s", sections=[], scenes=[_make_scene("s0"), _make_scene("s1")])
    api, fake_pipeline = _make_api(monkeypatch, project, tmp_path)

    saved = []
    monkeypatch.setattr(api_bridge, "save_project_file", lambda proj, path: saved.append(path))

    video_path = api.rerender_all()

    assert video_path == "video.mp4"
    assert fake_pipeline.rendered_project is project
    assert fake_pipeline.rerendered_scene_id is None  # rerender_scene jamais appelé
    assert len(saved) == 1
