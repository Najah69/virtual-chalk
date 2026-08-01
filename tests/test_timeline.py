"""Tâche 1 du blueprint "Timeline éditable & Anime.js" (voir docs/
architecture.md) : TimelineJSON intermédiaire + conversion Project <->
Timeline. Deux décisions actées avant d'écrire ce code : glisser un bloc
de scène pour le raccourcir réutilise EXACTEMENT la sémantique de la
commande NL "raccourcis la scène à Xs" (voir aussi test_nl_commands.py),
et cette fonction ne déclenche jamais elle-même de resynthèse/rendu —
seulement l'appelant futur (Api.update_timeline, Tâche 3, pas encore
écrite)."""

from __future__ import annotations

from app.scenes.schema import MascotAction, Point, Project, Scene, Stroke
from app.scenes.timeline import project_to_timeline, timeline_to_project


def _make_project():
    scenes = [
        Scene(
            scene_id="scene-001", voice_over="Bonjour et bienvenue.", duration_sec=5.0,
            visual_instruction="",
            strokes=[
                Stroke(points=[Point(100, 100)], color="#fff", width=90.0, kind="text",
                       text="Titre", start_sec=0.0, end_sec=1.0),
                Stroke(points=[Point(200, 200)], color="", width=300.0, height=150.0, kind="image",
                       image_data="data:...", start_sec=1.0, end_sec=2.0),
            ],
            mascot_timeline=[
                MascotAction(action_type="appear", start_sec=0.0, end_sec=0.6),
                MascotAction(action_type="wave", start_sec=0.6, end_sec=1.2),
            ],
        ),
        Scene(scene_id="scene-002", voice_over="Deuxième scène, un peu plus longue que la première.",
              duration_sec=8.0, visual_instruction=""),
    ]
    return Project(title="t", summary="s", sections=[], scenes=scenes)


def test_project_to_timeline_scene_entries_have_absolute_start():
    timeline = project_to_timeline(_make_project())
    assert timeline["scenes"] == [
        {"scene_id": "scene-001", "start": 0.0, "duration": 5.0},
        {"scene_id": "scene-002", "start": 5.0, "duration": 8.0},
    ]


def test_project_to_timeline_mascot_track_has_index_and_fields():
    timeline = project_to_timeline(_make_project())
    mascot = timeline["tracks"]["mascot"]
    assert len(mascot) == 2
    assert mascot[0] == {
        "scene_id": "scene-001", "index": 0, "start": 0.0, "end": 0.6,
        "action": "appear", "target_x": 0.0, "target_y": 0.0,
    }
    assert mascot[1]["index"] == 1
    assert mascot[1]["action"] == "wave"


def test_project_to_timeline_images_track_only_includes_image_strokes():
    timeline = project_to_timeline(_make_project())
    images = timeline["tracks"]["images"]
    assert len(images) == 1
    # index=1 : la 2e stroke de scene-001 (la 1ere est kind="text", exclue)
    assert images[0] == {"scene_id": "scene-001", "index": 1, "start": 1.0, "end": 2.0}


def test_project_to_timeline_empty_project_produces_empty_lists():
    empty = Project(title="t", summary="s", sections=[], scenes=[])
    timeline = project_to_timeline(empty)
    assert timeline == {"scenes": [], "tracks": {"mascot": [], "images": []}}


def test_timeline_to_project_reorders_scenes():
    project = _make_project()
    timeline = {"scenes": [{"scene_id": "scene-002"}, {"scene_id": "scene-001"}]}

    result = timeline_to_project(timeline, project)

    assert [s.scene_id for s in project.scenes] == ["scene-002", "scene-001"]
    assert result.reordered is True
    assert result.project is project  # mutation en place, pas une copie


def test_timeline_to_project_ignores_reorder_if_scene_set_does_not_match():
    """Defensif : un TimelineJSON qui ne référence pas TOUTES les scènes
    du projet actuel (périmé, ou scène supprimée par ailleurs entre-temps)
    ne doit jamais faire disparaître silencieusement une scène."""
    project = _make_project()
    original_order = [s.scene_id for s in project.scenes]
    timeline = {"scenes": [{"scene_id": "scene-002"}]}  # scene-001 manquante

    result = timeline_to_project(timeline, project)

    assert [s.scene_id for s in project.scenes] == original_order
    assert result.reordered is False


def test_timeline_to_project_shortens_duration_using_the_shared_truncation_heuristic():
    project = _make_project()
    scene = project.find_scene("scene-002")
    original_text = scene.voice_over
    timeline = {"scenes": [{"scene_id": "scene-002", "duration": 2.0}]}

    result = timeline_to_project(timeline, project)

    assert scene.duration_sec == 2.0
    assert scene.voice_over != original_text
    assert len(scene.voice_over) < len(original_text)
    assert result.changed_scene_ids == ["scene-002"]
    assert result.voice_changed_scene_ids == ["scene-002"]


def test_timeline_to_project_matches_nl_command_truncation_exactly():
    """Preuve que les deux points d'entrée (commande NL, timeline)
    produisent EXACTEMENT le même résultat pour le même texte/la même
    durée cible — la sémantique est vraiment partagée, pas juste
    similaire par coïncidence."""
    from app.edit.nl_commands import EditResult, _apply_update_scene_duration

    project_a = _make_project()
    project_b = _make_project()

    timeline_to_project({"scenes": [{"scene_id": "scene-002", "duration": 3.0}]}, project_a)
    _apply_update_scene_duration(
        project_b, {"scene_index": 1, "max_duration": 3.0}, EditResult(project=project_b)
    )

    assert project_a.find_scene("scene-002").voice_over == project_b.find_scene("scene-002").voice_over
    assert project_a.find_scene("scene-002").duration_sec == project_b.find_scene("scene-002").duration_sec


def test_timeline_to_project_skips_duration_within_epsilon_of_current():
    project = _make_project()
    scene = project.find_scene("scene-001")
    original_text = scene.voice_over
    timeline = {"scenes": [{"scene_id": "scene-001", "duration": 5.001}]}

    result = timeline_to_project(timeline, project)

    assert scene.voice_over == original_text  # pas tronqué pour un ecart negligeable
    assert result.changed_scene_ids == []
    assert result.voice_changed_scene_ids == []


def test_timeline_to_project_ignores_unknown_scene_id_in_duration_entries():
    project = _make_project()
    timeline = {"scenes": [{"scene_id": "does-not-exist", "duration": 1.0}]}

    result = timeline_to_project(timeline, project)  # ne doit pas lever d'exception

    assert result.changed_scene_ids == []


def test_timeline_to_project_updates_mascot_action_by_index():
    project = _make_project()
    timeline = {
        "tracks": {"mascot": [
            {"scene_id": "scene-001", "index": 1, "start": 0.7, "end": 1.5, "target_x": 42.0, "target_y": 84.0},
        ]}
    }

    result = timeline_to_project(timeline, project)

    action = project.find_scene("scene-001").mascot_timeline[1]
    assert action.start_sec == 0.7
    assert action.end_sec == 1.5
    assert action.target_x == 42.0
    assert action.target_y == 84.0
    # La 1ere phase (index 0) n'est pas touchée.
    assert project.find_scene("scene-001").mascot_timeline[0].start_sec == 0.0
    assert result.changed_scene_ids == ["scene-001"]


def test_timeline_to_project_ignores_out_of_range_mascot_index():
    project = _make_project()
    timeline = {"tracks": {"mascot": [{"scene_id": "scene-001", "index": 99, "start": 1.0, "end": 2.0}]}}

    result = timeline_to_project(timeline, project)  # ne doit pas lever d'exception

    assert result.changed_scene_ids == []


def test_timeline_to_project_updates_image_stroke_timing_by_index():
    project = _make_project()
    timeline = {"tracks": {"images": [{"scene_id": "scene-001", "index": 1, "start": 0.5, "end": 3.0}]}}

    result = timeline_to_project(timeline, project)

    stroke = project.find_scene("scene-001").strokes[1]
    assert stroke.start_sec == 0.5
    assert stroke.end_sec == 3.0
    assert result.changed_scene_ids == ["scene-001"]


def test_timeline_to_project_ignores_image_entry_whose_index_is_no_longer_an_image():
    """Défensif : les strokes ont pu être modifiées (édition WYSIWYG)
    entre la génération du TimelineJSON affiché et son application."""
    project = _make_project()
    # index=0 est un stroke "text" dans _make_project(), pas une image.
    timeline = {"tracks": {"images": [{"scene_id": "scene-001", "index": 0, "start": 0.0, "end": 5.0}]}}

    result = timeline_to_project(timeline, project)

    text_stroke = project.find_scene("scene-001").strokes[0]
    assert text_stroke.start_sec == 0.0  # valeur d'origine, jamais touchée
    assert result.changed_scene_ids == []


def test_round_trip_with_no_edits_reports_no_changes():
    project = _make_project()
    timeline = project_to_timeline(project)

    result = timeline_to_project(timeline, project)

    assert result.reordered is False
    assert result.changed_scene_ids == []
    assert result.voice_changed_scene_ids == []
    assert [s.scene_id for s in project.scenes] == ["scene-001", "scene-002"]
