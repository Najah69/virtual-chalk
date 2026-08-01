"""Pipeline.render/export_h5p nomment le fichier de sortie d'après le
slug du projet (pas "video.mp4"/"video.h5p" génériques, voir docs/
architecture.md) — aucun vrai appel ffmpeg/H5P ici, concat_scenes et
build_h5p sont simulés."""

from __future__ import annotations

import app.pipeline as pipeline_module
from app.pipeline import Pipeline
from app.scenes.schema import Project


def _make_project(title="Mon Super Projet"):
    return Project(title=title, summary="s", sections=[], scenes=[])


def test_render_names_output_after_project_slug(monkeypatch, tmp_path):
    project = _make_project()
    monkeypatch.setattr(pipeline_module, "render_all", lambda project, scenes_dir, on_progress=None: [])
    captured = {}
    monkeypatch.setattr(
        pipeline_module, "concat_scenes",
        lambda scene_videos, final_path: captured.setdefault("final_path", final_path),
    )

    pipeline = Pipeline.__new__(Pipeline)
    video_path = pipeline.render(project, tmp_path)

    assert video_path == tmp_path / f"{project.slug}.mp4"
    assert video_path.name != "video.mp4"
    assert captured["final_path"] == video_path


def test_export_h5p_names_output_after_project_slug(monkeypatch, tmp_path):
    project = _make_project()
    monkeypatch.setattr(pipeline_module, "generate_bookmarks", lambda scenes: [])
    captured = {}
    monkeypatch.setattr(
        pipeline_module, "build_h5p",
        lambda video_path, bookmarks, h5p_path, interactions, exercise_types: captured.setdefault("h5p_path", h5p_path),
    )

    pipeline = Pipeline.__new__(Pipeline)
    h5p_path = pipeline.export_h5p(project, tmp_path / f"{project.slug}.mp4", tmp_path)

    assert h5p_path == tmp_path / f"{project.slug}.h5p"
    assert h5p_path.name != "video.h5p"
    assert captured["h5p_path"] == h5p_path
