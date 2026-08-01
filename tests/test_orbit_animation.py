"""Premier verbe de la grammaire de mouvement (voir docs/architecture.md,
notes de brainstorm) : "orbit", N corps qui tournent autour d'un centre,
paramétrés par le LLM plutôt qu'une animation câblée par sujet. Ici :
uniquement la résolution Python (pourcentage -> pixels, validation,
bornes de sécurité) et la préservation de Stroke.params à travers les
sérialisations. Le rendu réel (mouvement effectif frame par frame) est
vérifié séparément via un script de fumée qui capture plusieurs frames
d'une vraie fenêtre webview — non reproductible en pytest pur."""

from __future__ import annotations

import app.api_bridge as api_bridge
from app.scenes.schema import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    ORBIT_MAX_BODIES,
    ORBIT_MIN_BODY_SIZE_PX,
    Project,
    Scene,
    strokes_from_visual_elements,
)


def _orbit_element(**overrides):
    el = {
        "type": "animation", "name": "orbit", "x": 50, "y": 50,
        "bodies": [
            {"icon": "world", "radius_pct": 12, "period_s": 4, "size_pct": 3, "phase_deg": 0},
            {"icon": "world", "radius_pct": 20, "period_s": 7, "size_pct": 3, "phase_deg": 120},
        ],
    }
    el.update(overrides)
    return el


def test_orbit_produces_an_animation_stroke_with_resolved_pixel_params():
    strokes = strokes_from_visual_elements([_orbit_element()], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)

    assert len(strokes) == 1
    stroke = strokes[0]
    assert stroke.kind == "animation"
    assert stroke.text == "orbit"
    assert len(stroke.params["bodies"]) == 2

    min_dim = min(CANVAS_WIDTH, CANVAS_HEIGHT)
    first = stroke.params["bodies"][0]
    assert first["icon"] == "world"
    assert first["radius"] == 0.12 * min_dim
    assert first["size"] == 0.03 * min_dim
    assert first["period_s"] == 4.0
    assert first["phase_deg"] == 0.0


def test_orbit_center_anchor_matches_x_y_like_other_elements():
    strokes = strokes_from_visual_elements([_orbit_element(x=25, y=60)], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)
    anchor = strokes[0].points[0]
    assert anchor.x == 0.25 * CANVAS_WIDTH
    assert anchor.y == 0.60 * CANVAS_HEIGHT


def test_orbit_draw_orbit_rings_defaults_to_true_but_is_configurable():
    default_on = strokes_from_visual_elements([_orbit_element()], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)
    assert default_on[0].params["draw_orbit_rings"] is True

    explicit_off = strokes_from_visual_elements(
        [_orbit_element(draw_orbit_rings=False)], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT
    )
    assert explicit_off[0].params["draw_orbit_rings"] is False


def test_orbit_body_with_unknown_icon_is_dropped_not_the_whole_stroke():
    el = _orbit_element(bodies=[
        {"icon": "world", "radius_pct": 12, "period_s": 4, "size_pct": 3},
        {"icon": "not-a-real-icon", "radius_pct": 20, "period_s": 5, "size_pct": 3},
    ])
    strokes = strokes_from_visual_elements([el], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)
    assert len(strokes) == 1
    assert len(strokes[0].params["bodies"]) == 1
    assert strokes[0].params["bodies"][0]["icon"] == "world"


def test_orbit_with_zero_valid_bodies_is_skipped_entirely():
    """Un "orbit" sans aucun corps valide (toutes les icônes inconnues, ou
    liste vide) n'a pas de sens — pas de stroke fantôme sans rien à
    animer, plutôt que de laisser le rendu planter sur des bodies vides."""
    empty = strokes_from_visual_elements([_orbit_element(bodies=[])], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)
    assert empty == []

    all_invalid = strokes_from_visual_elements(
        [_orbit_element(bodies=[{"icon": "nope", "radius_pct": 10}])], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT
    )
    assert all_invalid == []


def test_orbit_body_count_is_capped():
    many_bodies = [{"icon": "world", "radius_pct": 10 + i, "period_s": 4, "size_pct": 2} for i in range(10)]
    strokes = strokes_from_visual_elements(
        [_orbit_element(bodies=many_bodies)], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT
    )
    assert len(strokes[0].params["bodies"]) == ORBIT_MAX_BODIES


def test_orbit_body_size_has_a_readability_floor():
    el = _orbit_element(bodies=[{"icon": "world", "radius_pct": 10, "period_s": 4, "size_pct": 0.001}])
    strokes = strokes_from_visual_elements([el], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)
    assert strokes[0].params["bodies"][0]["size"] == ORBIT_MIN_BODY_SIZE_PX


def test_orbit_bounding_box_size_covers_the_farthest_body():
    strokes = strokes_from_visual_elements([_orbit_element()], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)
    stroke = strokes[0]
    farthest = max(b["radius"] + b["size"] / 2 for b in stroke.params["bodies"])
    assert stroke.width == farthest


def test_orbit_draws_its_own_center_icon_rather_than_relying_on_a_separate_element():
    """Régression : la première version demandait au LLM de placer une
    icône statique séparée au même x/y que le centre — resolve_overlaps
    ne savait pas que les deux devaient rester co-localisées et écartait
    l'icône du vrai centre de rotation (constaté à l'écran : le "soleil"
    se retrouvait décalé des anneaux). "orbit" dessine maintenant son
    propre corps central, réglé par center_icon/center_size_pct."""
    el = _orbit_element(center_icon="sun", center_size_pct=8)
    strokes = strokes_from_visual_elements([el], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)

    stroke = strokes[0]
    min_dim = min(CANVAS_WIDTH, CANVAS_HEIGHT)
    assert stroke.params["center_icon"] == "sun"
    assert stroke.params["center_size"] == 0.08 * min_dim
    # Un seul stroke produit -- pas de second élément "icône" séparé qui
    # pourrait être écarté du centre par resolve_overlaps.
    assert len(strokes) == 1


def test_orbit_center_icon_omitted_or_unknown_disables_center_drawing():
    without_center = strokes_from_visual_elements([_orbit_element()], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)
    assert without_center[0].params["center_icon"] == ""
    assert without_center[0].params["center_size"] == 0.0

    unknown_icon = strokes_from_visual_elements(
        [_orbit_element(center_icon="not-a-real-icon")], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT
    )
    assert unknown_icon[0].params["center_icon"] == ""


def test_orbit_bounding_box_accounts_for_a_center_larger_than_the_bodies_reach():
    el = _orbit_element(
        center_icon="sun", center_size_pct=50,  # delibérément énorme, plus large que la portée des corps
        bodies=[{"icon": "world", "radius_pct": 5, "period_s": 4, "size_pct": 1}],
    )
    strokes = strokes_from_visual_elements([el], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)
    stroke = strokes[0]
    min_dim = min(CANVAS_WIDTH, CANVAS_HEIGHT)
    body_reach = stroke.params["bodies"][0]["radius"] + stroke.params["bodies"][0]["size"] / 2
    assert stroke.params["center_size"] / 2 > body_reach  # confirme la prémisse du test
    assert stroke.width == stroke.params["center_size"] / 2


def test_orbit_params_survive_project_to_dict_from_dict_round_trip():
    strokes = strokes_from_visual_elements([_orbit_element()], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)
    project = Project(title="t", summary="s", sections=[], scenes=[
        Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="", strokes=strokes)
    ])

    restored = Project.from_dict(project.to_dict())

    restored_stroke = restored.scenes[0].strokes[0]
    assert restored_stroke.kind == "animation"
    assert restored_stroke.text == "orbit"
    assert len(restored_stroke.params["bodies"]) == 2
    assert restored_stroke.params["bodies"][0]["icon"] == "world"


def test_legacy_vchalk_without_params_field_loads_with_empty_params():
    """Un .vchalk enregistré avant l'ajout de Stroke.params n'a pas cette
    clé — doit se charger avec params={} plutôt que planter."""
    data = {
        "title": "t", "summary": "s", "sections": [],
        "scenes": [{
            "scene_id": "s0", "voice_over": "v", "duration_sec": 5.0, "visual_instruction": "",
            "strokes": [{"points": [{"x": 0, "y": 0}], "color": "#fff", "width": 10.0, "kind": "shape"}],
        }],
    }
    restored = Project.from_dict(data)
    assert restored.scenes[0].strokes[0].params == {}


def test_api_update_scene_strokes_preserves_orbit_params_from_editor_payload(monkeypatch, tmp_path):
    """Simule le round-trip éditeur : editor_canvas.js::serializeStrokesForSave
    envoie params tel quel, Api.update_scene_strokes doit le conserver
    (pas encore d'UI pour le MODIFIER, mais ne doit jamais le perdre)."""
    project = Project(title="t", summary="s", sections=[], scenes=[
        Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="")
    ])
    api = api_bridge.Api.__new__(api_bridge.Api)
    api.settings = None
    api._current_project = project

    payload = [{
        "points": [{"x": 960, "y": 540, "penUp": False}],
        "color": "#ffe66d", "width": 130.0, "kind": "animation", "text": "orbit",
        "params": {"bodies": [{"icon": "world", "radius": 130.0, "size": 32.4, "period_s": 4.0, "phase_deg": 0.0}],
                   "draw_orbit_rings": True},
    }]

    api.update_scene_strokes("s0", payload)

    saved = project.find_scene("s0").strokes[0]
    assert saved.params["bodies"][0]["icon"] == "world"
    assert saved.params["draw_orbit_rings"] is True
