"""Pipeline.generate_library_diagrams : pré-génère des schémas vectorisés
directement dans la Bibliothèque personnelle (app/library/asset_library.py),
HORS de tout Project (voir docs/architecture.md, section "Pré-génération de
schémas vers la bibliothèque"). Isolé de la vraie bibliothèque de
l'utilisateur via config_dir monkeypatché sur tmp_path (même technique que
tests/test_asset_library.py) — add_asset/normalize_points réels sont donc
exercés ici, pas remplacés par un double."""

from __future__ import annotations

import app.library.asset_library as asset_library
import app.pipeline as pipeline_module
from app.library.asset_library import load_library
from app.pipeline import Pipeline
from app.render.theme_registry import palette_for_theme
from app.scenes.schema import Point


def _make_pipeline(tmp_path, monkeypatch, diagram_api_key="fake-gemini-key"):
    monkeypatch.setattr(asset_library, "config_dir", lambda: tmp_path)
    return Pipeline(llm=None, tts=None, output_dir=tmp_path, diagram_api_key=diagram_api_key)


def _fake_generate_diagram_points(calls):
    def _fake(description, api_key, x, y, width, height):
        calls.append(description)
        if description == "trigger-empty":
            return []
        if description == "trigger-error":
            raise RuntimeError("panne réseau simulée")
        return [Point(x=0.0, y=0.0), Point(x=10.0, y=6.0)]

    return _fake


def test_generate_library_diagrams_adds_successful_descriptions_to_library(monkeypatch, tmp_path):
    pipeline = _make_pipeline(tmp_path, monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(pipeline_module, "generate_diagram_points", _fake_generate_diagram_points(calls))

    result = pipeline.generate_library_diagrams(["molécule de sucre"])

    assert result["failed_count"] == 0
    assert len(result["added"]) == 1
    assert result["added"][0]["name"] == "molécule de sucre"
    assert result["added"][0]["kind"] == "shape"
    assert result["added"][0]["color"] == palette_for_theme("chalk_board")[0]

    persisted = load_library()
    assert len(persisted) == 1
    assert persisted[0].name == "molécule de sucre"


def test_generate_library_diagrams_partial_failure_does_not_abort_the_batch(monkeypatch, tmp_path):
    pipeline = _make_pipeline(tmp_path, monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(pipeline_module, "generate_diagram_points", _fake_generate_diagram_points(calls))

    result = pipeline.generate_library_diagrams(["molécule de sucre", "trigger-empty", "trigger-error"])

    assert calls == ["molécule de sucre", "trigger-empty", "trigger-error"]
    assert result["failed_count"] == 2
    assert len(result["added"]) == 1
    assert load_library() and load_library()[0].name == "molécule de sucre"


def test_generate_library_diagrams_reports_progress_per_item(monkeypatch, tmp_path):
    pipeline = _make_pipeline(tmp_path, monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(pipeline_module, "generate_diagram_points", _fake_generate_diagram_points(calls))
    progress: list[tuple[str, float]] = []

    pipeline.generate_library_diagrams(["a", "b"], on_progress=lambda step, frac: progress.append((step, frac)))

    assert progress == [("library_diagram", 0.5), ("library_diagram", 1.0)]


def test_generate_library_diagrams_with_empty_list_is_a_noop(monkeypatch, tmp_path):
    pipeline = _make_pipeline(tmp_path, monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(pipeline_module, "generate_diagram_points", _fake_generate_diagram_points(calls))

    result = pipeline.generate_library_diagrams([])

    assert result == {"added": [], "failed_count": 0}
    assert calls == []


def test_generate_library_diagrams_raises_without_api_key(monkeypatch, tmp_path):
    pipeline = _make_pipeline(tmp_path, monkeypatch, diagram_api_key=None)

    try:
        pipeline.generate_library_diagrams(["molécule de sucre"])
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "cle API Gemini" in str(exc)
