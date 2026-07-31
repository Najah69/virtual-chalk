"""Tâche I : Stroke kind="image" (insertion d'images bitmap/vector).

Le rendu réel (décodage du data URI, dessin sur le canvas, capture de
frames) est vérifié manuellement via un script de fumée qui pilote la
vraie fenêtre de rendu (voir la session de développement) — non
reproductible ici sans webview. Ces tests couvrent la partie Python pure :
sérialisation, hash de cache, et l'orchestration de Api.insert_image."""

from __future__ import annotations

from pathlib import Path

import app.api_bridge as api_bridge
from app.render.partial_render import _hash_scene
from app.scenes.schema import CANVAS_HEIGHT, CANVAS_WIDTH, Point, Project, Scene, Stroke

TINY_PNG_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
    "2mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _make_scene(scene_id="s0") -> Scene:
    return Scene(scene_id=scene_id, voice_over="v", duration_sec=6.0, visual_instruction="")


def test_image_stroke_round_trips_through_to_dict_from_dict():
    stroke = Stroke(
        points=[Point(100, 200)], color="", width=300.0, height=150.0,
        kind="image", image_data=TINY_PNG_DATA_URI,
    )
    project = Project(title="t", summary="s", sections=[], scenes=[Scene(
        scene_id="s0", voice_over="v", duration_sec=6.0, visual_instruction="", strokes=[stroke],
    )])

    restored = Project.from_dict(project.to_dict())

    restored_stroke = restored.scenes[0].strokes[0]
    assert restored_stroke.kind == "image"
    assert restored_stroke.image_data == TINY_PNG_DATA_URI
    assert restored_stroke.height == 150.0
    assert restored_stroke.width == 300.0


def test_image_stroke_changes_scene_content_hash():
    scene_without = _make_scene()
    hash_without = _hash_scene(scene_without)

    scene_with = _make_scene()
    scene_with.strokes.append(Stroke(
        points=[Point(0, 0)], color="", width=100.0, height=100.0,
        kind="image", image_data=TINY_PNG_DATA_URI,
    ))
    hash_with = _hash_scene(scene_with)

    assert hash_without != hash_with


class _FakePipeline:
    def __init__(self):
        self.rerendered_scene_id = None

    def rerender_scene(self, project, scene_id, out_dir):
        self.rerendered_scene_id = scene_id
        return Path("video.mp4")


def _make_api(monkeypatch, project, project_dir):
    api = api_bridge.Api.__new__(api_bridge.Api)
    api.settings = None
    api._current_project = project
    api._current_project_path = None
    api._current_project_dir = project_dir
    api._current_video_path = None
    api._current_voice_profile = None

    fake_pipeline = _FakePipeline()
    monkeypatch.setattr(api_bridge.Api, "_build_pipeline", lambda self, voice_profile=None: fake_pipeline)
    monkeypatch.setattr(api_bridge, "save_project_file", lambda project, path: None)
    return api, fake_pipeline


def test_insert_image_appends_stroke_with_correct_pixel_conversion(monkeypatch, tmp_path):
    project = Project(title="t", summary="s", sections=[], scenes=[_make_scene("s0")])
    api, fake_pipeline = _make_api(monkeypatch, project, tmp_path)

    result = api.insert_image("s0", TINY_PNG_DATA_URI, x_pct=25.0, y_pct=50.0, width_pct=20.0, height_pct=10.0)

    stroke = project.scenes[0].strokes[-1]
    assert stroke.kind == "image"
    assert stroke.image_data == TINY_PNG_DATA_URI
    assert stroke.points[0].x == 0.25 * CANVAS_WIDTH
    assert stroke.points[0].y == 0.50 * CANVAS_HEIGHT
    assert stroke.width == 0.20 * CANVAS_WIDTH
    assert stroke.height == 0.10 * CANVAS_HEIGHT
    assert fake_pipeline.rerendered_scene_id == "s0"
    assert result["project"]["scenes"][0]["strokes"][-1]["kind"] == "image"


def test_insert_image_raises_for_unknown_scene(monkeypatch, tmp_path):
    project = Project(title="t", summary="s", sections=[], scenes=[_make_scene("s0")])
    api, _ = _make_api(monkeypatch, project, tmp_path)

    try:
        api.insert_image("does-not-exist", TINY_PNG_DATA_URI, 0, 0, 10, 10)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
