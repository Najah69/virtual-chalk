"""Tâche 6 : bibliothèque personnelle d'éléments vectorisés
(app/library/asset_library.py) — stockage GLOBAL (config_dir(), voir
app/settings.py), pas embarqué par projet. normalize_points est la partie
la plus sensible (même convention que icon_to_path.js::iconToPoints, un
point normalisé doit se replacer correctement à n'importe quelle taille) :
couverte séparément de add_asset/load_library/remove_asset (I/O disque,
isolée via monkeypatch de config_dir sur un tmp_path)."""

from __future__ import annotations

import app.library.asset_library as asset_library
from app.library.asset_library import (
    LIBRARY_NATIVE_WIDTH,
    add_asset,
    load_library,
    normalize_points,
    remove_asset,
)


def test_normalize_points_maps_bbox_top_left_to_origin():
    bbox = {"x": 100.0, "y": 200.0, "w": 48.0, "h": 24.0}
    points = [{"x": 100.0, "y": 200.0, "penUp": False}]

    native_points, native_height = normalize_points(points, bbox)

    assert native_points[0].x == 0.0
    assert native_points[0].y == 0.0
    assert native_points[0].pen_up is False


def test_normalize_points_scales_width_to_the_native_reference():
    bbox = {"x": 0.0, "y": 0.0, "w": 48.0, "h": 24.0}
    points = [{"x": 48.0, "y": 24.0, "penUp": False}]  # coin bas-droit de la bbox

    native_points, native_height = normalize_points(points, bbox)

    assert native_points[0].x == LIBRARY_NATIVE_WIDTH  # 48px -> largeur native (24)
    assert native_height == LIBRARY_NATIVE_WIDTH / 2  # aspect 2:1 préservé (48x24 -> 24x12)


def test_normalize_points_preserves_pen_up():
    bbox = {"x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0}
    points = [{"x": 0.0, "y": 0.0, "penUp": False}, {"x": 5.0, "y": 5.0, "penUp": True}]

    native_points, _ = normalize_points(points, bbox)

    assert native_points[0].pen_up is False
    assert native_points[1].pen_up is True


def test_normalize_points_round_trip_places_back_at_original_pixel_position():
    """Le point de la formule inverse (voir library.js::assetToPoints côté
    JS) doit retomber EXACTEMENT sur la position d'origine si on replace
    l'élément à sa taille/position d'origine."""
    bbox = {"x": 300.0, "y": 150.0, "w": 60.0, "h": 30.0}
    points = [{"x": 330.0, "y": 165.0, "penUp": False}]  # centre de la bbox

    native_points, native_height = normalize_points(points, bbox)
    scale = bbox["w"] / LIBRARY_NATIVE_WIDTH
    placed_x = bbox["x"] + native_points[0].x * scale
    placed_y = bbox["y"] + native_points[0].y * scale

    assert abs(placed_x - 330.0) < 1e-9
    assert abs(placed_y - 165.0) < 1e-9


def _use_tmp_config_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_library, "config_dir", lambda: tmp_path)


def test_add_asset_rejects_ineligible_kind(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    bbox = {"x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0}

    try:
        add_asset("Mon icône", "icon", "#fff", [{"x": 0.0, "y": 0.0}], bbox)
        raise AssertionError("expected ValueError for ineligible kind")
    except ValueError:
        pass


def test_add_asset_persists_and_load_library_round_trips(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    bbox = {"x": 0.0, "y": 0.0, "w": 20.0, "h": 20.0}
    points = [{"x": 0.0, "y": 0.0, "penUp": False}, {"x": 20.0, "y": 20.0, "penUp": False}]

    saved = add_asset("Mon tracé", "shape", "#ffe66d", points, bbox)
    reloaded = load_library()

    assert len(reloaded) == 1
    assert reloaded[0].asset_id == saved.asset_id
    assert reloaded[0].name == "Mon tracé"
    assert reloaded[0].kind == "shape"
    assert reloaded[0].color == "#ffe66d"
    assert len(reloaded[0].points) == 2


def test_add_asset_falls_back_to_untitled_when_name_is_blank(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    bbox = {"x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0}

    saved = add_asset("   ", "shape", "#fff", [{"x": 0.0, "y": 0.0}], bbox)

    assert saved.name == "Sans titre"


def test_remove_asset_deletes_only_the_matching_entry(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    bbox = {"x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0}
    kept = add_asset("Garde-moi", "shape", "#fff", [{"x": 0.0, "y": 0.0}], bbox)
    removed = add_asset("Supprime-moi", "shape", "#fff", [{"x": 0.0, "y": 0.0}], bbox)

    remove_asset(removed.asset_id)

    remaining = load_library()
    assert [a.asset_id for a in remaining] == [kept.asset_id]


def test_load_library_returns_empty_list_when_no_file_exists(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)

    assert load_library() == []
