"""Tâche H : timeline déterministe de la mascotte animée
(app/scenes/schema.py) et intégration à l'édition NL (toggle_mascot)."""

from __future__ import annotations

import json

from app.edit.nl_commands import apply_nl_edit_command
from app.render.partial_render import _hash_scene
from app.scenes.schema import (
    Point,
    Project,
    Scene,
    Stroke,
    add_mascot_timeline,
    default_mascot_timeline,
    remove_mascot_timeline,
)
from tests.conftest import FakeLLMProvider


def _make_scene(scene_id="s0", duration=10.0, strokes=None) -> Scene:
    return Scene(
        scene_id=scene_id, voice_over="v", duration_sec=duration,
        visual_instruction="", strokes=strokes or [],
    )


def test_default_mascot_timeline_starts_at_zero_and_ends_at_scene_duration():
    scene = _make_scene(duration=8.0)
    timeline = default_mascot_timeline(scene)
    assert timeline[0].action_type == "appear"
    assert timeline[0].start_sec == 0.0
    assert timeline[-1].action_type == "disappear"
    assert timeline[-1].end_sec == 8.0
    # Les phases se suivent sans recouvrement ni trou.
    for prev, nxt in zip(timeline, timeline[1:]):
        assert prev.end_sec == nxt.start_sec


def test_default_mascot_timeline_greet_adds_wave_after_appear():
    scene = _make_scene(duration=8.0)
    timeline = default_mascot_timeline(scene, greet=True)
    assert timeline[1].action_type == "wave"

    timeline_no_greet = default_mascot_timeline(scene, greet=False)
    assert "wave" not in [a.action_type for a in timeline_no_greet]


def test_default_mascot_timeline_points_at_first_non_text_element():
    icon_stroke = Stroke(points=[Point(500, 300)], color="#fff", width=220.0, kind="icon", text="sun")
    scene = _make_scene(duration=10.0, strokes=[icon_stroke])
    timeline = default_mascot_timeline(scene)
    point_actions = [a for a in timeline if a.action_type == "point"]
    assert len(point_actions) == 1
    assert point_actions[0].target_x == 500
    assert point_actions[0].target_y == 300


def test_default_mascot_timeline_no_point_when_only_text_elements():
    text_stroke = Stroke(points=[Point(500, 300)], color="#fff", width=90.0, kind="text", text="Bonjour")
    scene = _make_scene(duration=10.0, strokes=[text_stroke])
    timeline = default_mascot_timeline(scene)
    assert "point" not in [a.action_type for a in timeline]


def test_default_mascot_timeline_short_scene_skips_wave_and_point():
    scene = _make_scene(duration=0.8)
    timeline = default_mascot_timeline(scene, greet=True)
    # Trop court pour saluer ou pointer (fenêtre minimale non atteinte) :
    # seules les phases apparition/attente/disparition restent.
    assert [a.action_type for a in timeline] == ["appear", "idle", "disappear"]


def test_add_and_remove_mascot_timeline_round_trip():
    project = Project(
        title="t", summary="s", sections=[],
        scenes=[_make_scene("s0"), _make_scene("s1")],
    )
    assert project.mascot_enabled is False

    add_mascot_timeline(project)
    assert project.mascot_enabled is True
    assert project.scenes[0].mascot_timeline[1].action_type == "wave"  # première scène = greet
    assert all(scene.mascot_timeline for scene in project.scenes)

    remove_mascot_timeline(project)
    assert project.mascot_enabled is False
    assert all(scene.mascot_timeline == [] for scene in project.scenes)


def test_mascot_timeline_changes_scene_content_hash():
    scene_off = _make_scene("s0")
    hash_off = _hash_scene(scene_off)

    scene_on = _make_scene("s0")
    scene_on.mascot_timeline = default_mascot_timeline(scene_on)
    hash_on = _hash_scene(scene_on)

    assert hash_off != hash_on


def test_toggle_mascot_nl_action_enables_and_marks_all_scenes_changed():
    project = Project(
        title="t", summary="s", sections=[],
        scenes=[_make_scene("s0"), _make_scene("s1")],
    )
    llm = FakeLLMProvider([json.dumps({"actions": [{"action": "toggle_mascot", "enabled": True}]})])

    result = apply_nl_edit_command(project, "ajoute une mascotte", llm)

    assert result.error is None
    assert project.mascot_enabled is True
    assert set(result.changed_scene_ids) == {"s0", "s1"}
    assert all(scene.mascot_timeline for scene in project.scenes)


def test_toggle_mascot_nl_action_is_noop_when_already_in_requested_state():
    project = Project(
        title="t", summary="s", sections=[],
        scenes=[_make_scene("s0")],
    )
    llm = FakeLLMProvider([json.dumps({"actions": [{"action": "toggle_mascot", "enabled": False}]})])

    result = apply_nl_edit_command(project, "désactive la mascotte", llm)

    assert result.error is None
    assert result.changed_scene_ids == []
    assert project.mascot_enabled is False


def test_insert_scene_gets_mascot_timeline_when_project_mascot_enabled():
    project = Project(
        title="t", summary="s", sections=[],
        scenes=[_make_scene("s0")],
    )
    add_mascot_timeline(project)
    actions = {"actions": [{"action": "insert_scene", "before_index": 1, "voice_over": "Nouvelle scène"}]}
    llm = FakeLLMProvider([json.dumps(actions)])

    result = apply_nl_edit_command(project, "ajoute une scène à la fin", llm)

    assert result.error is None
    new_scene = project.scenes[1]
    assert new_scene.mascot_timeline
    # La scène insérée n'est jamais "greet" (réservé à la toute première scène).
    assert "wave" not in [a.action_type for a in new_scene.mascot_timeline]
