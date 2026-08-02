"""Tâche B (résolution sûre de scene_id / index) et Tâche D (hiérarchie de
recoloration par kind de stroke) de app/edit/nl_commands.py."""

from __future__ import annotations

import json

from app.edit.nl_commands import (
    EditCommandError,
    EditResult,
    _apply_add_visual_elements,
    _apply_replace_scene_content,
    _recolor_strokes_for_theme,
    apply_nl_edit_command,
)
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


def test_apply_nl_edit_command_update_scene_duration_truncates_and_reports_voice_change():
    """Comblait un vrai trou de couverture : update_scene_duration n'avait
    aucun test avant l'extraction de sa logique en fonction partagée
    (truncate_voice_over_to_duration, voir app/scenes/timeline.py)."""
    project = _make_project()
    project.scenes[0].voice_over = "Une phrase assez longue pour dépasser le budget alloué à la scène."
    actions = {"actions": [{"action": "update_scene_duration", "scene_index": 0, "max_duration": 2.0}]}
    llm = FakeLLMProvider([json.dumps(actions)])

    result = apply_nl_edit_command(project, "raccourcis la scène 1 à 2 secondes", llm)

    assert result.error is None
    assert project.scenes[0].duration_sec == 2.0
    assert len(project.scenes[0].voice_over) < len("Une phrase assez longue pour dépasser le budget alloué à la scène.")
    assert result.changed_scene_ids == ["s0"]
    assert result.voice_changed_scene_ids == ["s0"]


def test_apply_replace_scene_content_without_voice_over_or_visual_elements_raises():
    """Régression : le LLM peut renvoyer une action replace_scene_content
    ne portant ni voice_over ni visual_elements (ex: mauvaise compréhension
    de la commande "dessine la molécule Sucre+CO2") -- doit être traitée
    comme invalide (EditCommandError), pas comme un succès silencieux."""
    project = _make_project()
    result = EditResult(project=project)
    try:
        _apply_replace_scene_content(project, {"scene_index": 0}, result)
        raise AssertionError("expected EditCommandError")
    except EditCommandError:
        pass
    assert result.changed_scene_ids == []


def test_apply_nl_edit_command_replace_scene_content_noop_action_is_skipped_not_fatal():
    project = _make_project()
    actions = {"actions": [{"action": "replace_scene_content", "scene_index": 0}]}
    llm = FakeLLMProvider([json.dumps(actions)])

    result = apply_nl_edit_command(project, "dessine quelque chose", llm)

    assert result.error is None
    assert result.changed_scene_ids == []
    assert len(result.skipped_actions) == 1


def test_apply_replace_scene_content_with_visual_elements_marks_scene_changed():
    project = _make_project()
    result = EditResult(project=project)
    action = {
        "scene_index": 0,
        "visual_elements": [{"type": "diagram", "description": "molécule", "x": 10, "y": 10, "width": 5, "height": 5}],
    }

    _apply_replace_scene_content(project, action, result)

    assert result.changed_scene_ids == ["s0"]
    assert project.scenes[0].strokes[0].kind == "diagram"


def test_apply_add_visual_elements_appends_without_touching_existing_strokes():
    """Corrige le blocage réel rencontré après coup : replace_scene_content
    refusait à raison de "deviner" le contenu existant d'une scène pour y
    ajouter un schéma -- add_visual_elements ajoute sans y toucher."""
    project = _make_project()
    project.scenes[0].strokes = [Stroke(points=[Point(0, 0)], color="#fff", width=10.0, kind="text", text="Déjà là")]
    result = EditResult(project=project)
    action = {
        "scene_index": 0,
        "visual_elements": [{"type": "diagram", "description": "molécule", "x": 50, "y": 55, "width": 35, "height": 35}],
    }

    _apply_add_visual_elements(project, action, result)

    assert result.changed_scene_ids == ["s0"]
    assert len(project.scenes[0].strokes) == 2
    assert project.scenes[0].strokes[0].text == "Déjà là"
    assert project.scenes[0].strokes[1].kind == "diagram"


def test_apply_add_visual_elements_without_elements_raises():
    project = _make_project()
    result = EditResult(project=project)
    try:
        _apply_add_visual_elements(project, {"scene_index": 0}, result)
        raise AssertionError("expected EditCommandError")
    except EditCommandError:
        pass
    assert result.changed_scene_ids == []


def test_apply_nl_edit_command_add_visual_elements_end_to_end():
    project = _make_project()
    actions = {
        "actions": [{
            "action": "add_visual_elements",
            "scene_index": 1,
            "visual_elements": [{"type": "icon", "name": "sun", "x": 50, "y": 30}],
        }],
    }
    llm = FakeLLMProvider([json.dumps(actions)])

    result = apply_nl_edit_command(project, "ajoute un soleil sur la scène 2", llm)

    assert result.error is None
    assert result.changed_scene_ids == ["s1"]
    assert project.scenes[1].strokes[0].kind == "icon"


def test_apply_nl_edit_command_update_scene_duration_uses_the_shared_helper():
    """La commande NL doit produire EXACTEMENT le même résultat que
    l'appel direct à truncate_voice_over_to_duration -- preuve que la
    logique est vraiment partagée avec app/scenes/timeline.py, pas
    seulement similaire."""
    from app.scenes.schema import truncate_voice_over_to_duration

    project_a = _make_project()
    project_a.scenes[0].voice_over = "Une phrase assez longue pour dépasser le budget alloué à la scène."
    project_b = _make_project()
    project_b.scenes[0].voice_over = "Une phrase assez longue pour dépasser le budget alloué à la scène."

    actions = {"actions": [{"action": "update_scene_duration", "scene_index": 0, "max_duration": 2.0}]}
    apply_nl_edit_command(project_a, "raccourcis", FakeLLMProvider([json.dumps(actions)]))
    truncate_voice_over_to_duration(project_b.scenes[0], 2.0)

    assert project_a.scenes[0].voice_over == project_b.scenes[0].voice_over
    assert project_a.scenes[0].duration_sec == project_b.scenes[0].duration_sec
