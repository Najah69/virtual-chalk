"""Tâche B (résolution sûre de scene_id / index) et Tâche D (hiérarchie de
recoloration par kind de stroke) de app/edit/nl_commands.py."""

from __future__ import annotations

import json

from app.edit.nl_commands import _recolor_strokes_for_theme, apply_nl_edit_command
from app.render.theme_registry import text_color_for_theme
from app.scenes.schema import Point, Project, Scene, Stroke
from tests.conftest import FakeLLMProvider


def _make_project(theme: str = "chalk_board") -> Project:
    scenes = [
        Scene(scene_id="s0", voice_over="Première scène", duration_sec=5, visual_instruction=""),
        Scene(scene_id="s1", voice_over="Deuxième scène", duration_sec=5, visual_instruction=""),
    ]
    return Project(title="Test", summary="Résumé", sections=[], scenes=scenes, theme=theme)


def test_apply_nl_edit_command_llm_json_error_leaves_project_untouched():
    project = _make_project()
    llm = FakeLLMProvider(["réponse illisible, pas du JSON"])
    result = apply_nl_edit_command(project, "fais quelque chose", llm)

    assert result.error is not None
    assert result.project is project
    assert result.applied_actions == []
    assert project.scenes[0].scene_id == "s0"


def test_apply_nl_edit_command_unknown_action_is_skipped_not_fatal():
    project = _make_project()
    actions = {"actions": [{"action": "does_not_exist"}, {"action": "set_theme", "theme": "whiteboard_marker"}]}
    llm = FakeLLMProvider([json.dumps(actions)])

    result = apply_nl_edit_command(project, "change de thème", llm)

    assert result.error is None
    assert len(result.skipped_actions) == 1
    assert len(result.applied_actions) == 1
    assert project.theme == "whiteboard_marker"


def test_apply_nl_edit_command_out_of_range_index_is_skipped_not_fatal():
    project = _make_project()
    actions = {"actions": [{"action": "delete_scene", "scene_index": 99}]}
    llm = FakeLLMProvider([json.dumps(actions)])

    result = apply_nl_edit_command(project, "supprime une scène improbable", llm)

    assert result.error is None
    assert len(result.skipped_actions) == 1
    assert len(project.scenes) == 2


def test_project_find_scene_returns_none_for_unknown_id():
    project = _make_project()
    assert project.find_scene("does-not-exist") is None
    assert project.find_scene("s1") is project.scenes[1]


def test_recolor_text_strokes_use_safe_theme_colors_not_cyclic_palette():
    scene = Scene(
        scene_id="s0", voice_over="v", duration_sec=5, visual_instruction="",
        strokes=[
            Stroke(points=[Point(0, 0)], color="#ffffff", width=90.0, kind="text", text="Un"),
            Stroke(points=[Point(0, 0)], color="#ffffff", width=220.0, kind="icon", text="sun"),
            Stroke(points=[Point(0, 0)], color="#ffffff", width=90.0, kind="text", text="Deux"),
        ],
    )
    project = Project(title="t", summary="s", sections=[], scenes=[scene], theme="chalk_board")

    _recolor_strokes_for_theme(project, "whiteboard_marker")

    text_strokes = [s for s in project.scenes[0].strokes if s.kind == "text"]
    assert text_strokes[0].color == text_color_for_theme("whiteboard_marker", 0)
    assert text_strokes[1].color == text_color_for_theme("whiteboard_marker", 1)
    # L'icône "sun" suit sa couleur sémantique dédiée, pas la liste de
    # couleurs de texte ni la palette cyclique.
    from app.render.theme_registry import semantic_color_for_icon
    icon_stroke = next(s for s in project.scenes[0].strokes if s.kind == "icon")
    assert icon_stroke.color == semantic_color_for_icon("sun", "whiteboard_marker")


def test_recolor_shape_strokes_use_cyclic_palette_not_text_colors():
    scene = Scene(
        scene_id="s0", voice_over="v", duration_sec=5, visual_instruction="",
        strokes=[Stroke(points=[Point(0, 0)], color="#000000", width=10.0, kind="shape", text="")],
    )
    project = Project(title="t", summary="s", sections=[], scenes=[scene], theme="chalk_board")

    _recolor_strokes_for_theme(project, "chalk_board")

    from app.render.theme_registry import palette_for_theme
    assert project.scenes[0].strokes[0].color == palette_for_theme("chalk_board")[0]
