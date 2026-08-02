"""Boucle d'auto-critique visuelle (app/critique/visual_critique.py,
proposition explicite de l'utilisateur — voir docs/architecture.md).
FrameCapture/le vrai appel Gemini sont entièrement simulés ici (aucune
vraie fenêtre de rendu ni appel réseau) : la logique d'orchestration
(quelles scènes restent en attente, combien d'itérations, comment les
éléments manquants deviennent de vrais strokes) est testable sans eux."""

from __future__ import annotations

import json

from app.critique.visual_critique import (
    MAX_CRITIQUE_ITERATIONS,
    analyze_scene_illustration,
    apply_layout_fixes,
    run_critique_loop,
)
from app.scenes.schema import CANVAS_HEIGHT, CANVAS_WIDTH, Point, Project, Scene, Stroke
from tests.conftest import FakeLLMProvider


class _FakeCapture:
    """Double de FrameCapture : ne dessine rien de réel, retourne des
    octets factices et enregistre chaque appel pour vérification."""

    def __init__(self):
        self.calls: list[tuple[str, list[float]]] = []

    def capture_frames_at(self, scene, theme, canvas_width, canvas_height, timestamps):
        self.calls.append((scene.scene_id, list(timestamps)))
        return [b"frame-a", b"frame-b"]


def _make_project(scene_ids):
    scenes = [
        Scene(scene_id=sid, voice_over=f"voix off de {sid}", duration_sec=10.0, visual_instruction="")
        for sid in scene_ids
    ]
    return Project(title="t", summary="s", sections=[], scenes=scenes)


def _sufficient_response():
    return json.dumps({"sufficient": True, "reason": "ok", "missing_elements": []})


def _insufficient_response_with_icon():
    return json.dumps({
        "sufficient": False, "reason": "texte seul, rien à voir",
        "missing_elements": [{"type": "icon", "name": "sun", "x": 50, "y": 50}],
    })


def test_scene_judged_sufficient_gets_no_strokes_and_stops_immediately():
    project = _make_project(["scene-001"])
    llm = FakeLLMProvider([_sufficient_response()])
    capture = _FakeCapture()

    remaining = run_critique_loop(llm, project, capture)

    assert remaining == []
    assert project.find_scene("scene-001").strokes == []
    assert len(capture.calls) == 1  # une seule capture : jamais réanalysée après "suffisant"


def test_scene_judged_insufficient_gets_missing_elements_appended():
    project = _make_project(["scene-001"])
    # Insuffisant à l'itération 1, suffisant à l'itération 2 (après l'ajout).
    llm = FakeLLMProvider([_insufficient_response_with_icon(), _sufficient_response()])
    capture = _FakeCapture()

    remaining = run_critique_loop(llm, project, capture)

    scene = project.find_scene("scene-001")
    assert remaining == []
    assert len(scene.strokes) == 1
    assert scene.strokes[0].kind == "icon"
    assert scene.strokes[0].text == "sun"
    assert len(capture.calls) == 2  # ré-analysée une fois, avec le nouvel élément


def test_loop_stops_at_max_iterations_even_if_still_insufficient():
    project = _make_project(["scene-001"])
    responses = [_insufficient_response_with_icon() for _ in range(MAX_CRITIQUE_ITERATIONS)]
    llm = FakeLLMProvider(responses)
    capture = _FakeCapture()

    remaining = run_critique_loop(llm, project, capture)

    assert remaining == ["scene-001"]
    assert len(capture.calls) == MAX_CRITIQUE_ITERATIONS
    # Un élément ajouté à CHAQUE itération insuffisante, pas juste la première.
    assert len(project.find_scene("scene-001").strokes) == MAX_CRITIQUE_ITERATIONS


def test_only_insufficient_scenes_are_reanalyzed_in_later_iterations():
    project = _make_project(["scene-001", "scene-002"])
    # scene-001 : suffisant du premier coup. scene-002 : insuffisant puis suffisant.
    llm = FakeLLMProvider([_sufficient_response(), _insufficient_response_with_icon(), _sufficient_response()])
    capture = _FakeCapture()

    remaining = run_critique_loop(llm, project, capture)

    assert remaining == []
    scene_ids_captured = [sid for sid, _ in capture.calls]
    assert scene_ids_captured.count("scene-001") == 1
    assert scene_ids_captured.count("scene-002") == 2


def test_progress_callback_receives_one_call_per_iteration_actually_run():
    project = _make_project(["scene-001"])
    llm = FakeLLMProvider([_sufficient_response()])
    capture = _FakeCapture()
    progress_calls = []

    run_critique_loop(llm, project, capture, on_progress=lambda step, frac: progress_calls.append((step, frac)))

    assert progress_calls == [("critique", 1 / MAX_CRITIQUE_ITERATIONS)]


def test_provider_without_vision_support_degrades_to_sufficient_without_crashing():
    from app.llm.base import LLMProvider

    class _TextOnlyProvider(LLMProvider):
        def _complete(self, system_prompt, user_prompt):
            raise AssertionError("ne devrait jamais être appelé ici")

    project = _make_project(["scene-001"])
    provider = _TextOnlyProvider(api_key="k", model="m")
    capture = _FakeCapture()

    remaining = run_critique_loop(provider, project, capture)

    assert remaining == []
    assert project.find_scene("scene-001").strokes == []


def test_capture_timestamps_stay_within_scene_duration():
    project = _make_project(["scene-001"])
    project.find_scene("scene-001").duration_sec = 4.0
    llm = FakeLLMProvider([_sufficient_response()])
    capture = _FakeCapture()

    run_critique_loop(llm, project, capture)

    _, timestamps = capture.calls[0]
    assert all(0.0 <= t <= 4.0 for t in timestamps)
    assert len(timestamps) == 2


# --- Corrections de mise en page du texte (demande explicite de l'utilisateur) ---

def _text_stroke(x=100.0, y=100.0, content="Bonjour"):
    return Stroke(points=[Point(x, y)], color="#fff", width=90.0, kind="text", text=content)


def _icon_stroke(x=200.0, y=200.0, name="sun"):
    return Stroke(points=[Point(x, y)], color="#fff", width=220.0, kind="icon", text=name)


def test_apply_layout_fixes_moves_a_text_stroke():
    scene = Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="",
                   strokes=[_text_stroke(x=100.0, y=100.0)])

    changed = apply_layout_fixes(scene, [{"stroke_index": 0, "action": "move", "x": 25.0, "y": 60.0}],
                                  CANVAS_WIDTH, CANVAS_HEIGHT)

    assert changed is True
    assert scene.strokes[0].points[0].x == 25.0 / 100.0 * CANVAS_WIDTH
    assert scene.strokes[0].points[0].y == 60.0 / 100.0 * CANVAS_HEIGHT


def test_apply_layout_fixes_shortens_text_when_new_text_is_actually_shorter():
    scene = Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="",
                   strokes=[_text_stroke(content="Un texte beaucoup trop long pour tenir sur le tableau")])

    changed = apply_layout_fixes(
        scene, [{"stroke_index": 0, "action": "shorten_text", "text": "Texte court"}], CANVAS_WIDTH, CANVAS_HEIGHT,
    )

    assert changed is True
    assert scene.strokes[0].text == "Texte court"


def test_apply_layout_fixes_ignores_shorten_text_when_proposed_text_is_not_shorter():
    # Défensif : une "correction" qui ne raccourcit pas réellement le texte
    # n'a pas lieu d'être appliquée (le modèle a pu se tromper).
    scene = Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="",
                   strokes=[_text_stroke(content="Court")])

    changed = apply_layout_fixes(
        scene, [{"stroke_index": 0, "action": "shorten_text", "text": "Un texte en fait plus long qu'avant"}],
        CANVAS_WIDTH, CANVAS_HEIGHT,
    )

    assert changed is False
    assert scene.strokes[0].text == "Court"


def test_apply_layout_fixes_removes_any_kind_of_stroke():
    scene = Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="",
                   strokes=[_text_stroke(), _icon_stroke()])

    changed = apply_layout_fixes(scene, [{"stroke_index": 1, "action": "remove"}], CANVAS_WIDTH, CANVAS_HEIGHT)

    assert changed is True
    assert len(scene.strokes) == 1
    assert scene.strokes[0].kind == "text"


def test_apply_layout_fixes_handles_multiple_removes_without_index_shift_bugs():
    scene = Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="",
                   strokes=[_text_stroke(content="garde-0"), _icon_stroke(), _text_stroke(content="garde-2"),
                            _icon_stroke()])

    # Supprime les index 1 et 3 (dans un ordre volontairement pas trié, pour
    # vérifier que apply_layout_fixes trie lui-même par ordre décroissant).
    changed = apply_layout_fixes(
        scene, [{"stroke_index": 1, "action": "remove"}, {"stroke_index": 3, "action": "remove"}],
        CANVAS_WIDTH, CANVAS_HEIGHT,
    )

    assert changed is True
    assert [s.text for s in scene.strokes] == ["garde-0", "garde-2"]


def test_apply_layout_fixes_ignores_move_on_non_text_stroke():
    scene = Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="",
                   strokes=[_icon_stroke(x=200.0, y=200.0)])

    changed = apply_layout_fixes(scene, [{"stroke_index": 0, "action": "move", "x": 10.0, "y": 10.0}],
                                  CANVAS_WIDTH, CANVAS_HEIGHT)

    assert changed is False
    assert scene.strokes[0].points[0].x == 200.0  # inchangé


def test_apply_layout_fixes_ignores_out_of_range_index():
    scene = Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="",
                   strokes=[_text_stroke()])

    changed = apply_layout_fixes(scene, [{"stroke_index": 99, "action": "remove"}], CANVAS_WIDTH, CANVAS_HEIGHT)

    assert changed is False
    assert len(scene.strokes) == 1


def test_apply_layout_fixes_ignores_malformed_fix_entries():
    scene = Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="",
                   strokes=[_text_stroke()])

    # Pas d'index, pas d'action reconnue, index non entier : aucun ne doit
    # planter ni être appliqué.
    changed = apply_layout_fixes(
        scene,
        [{"action": "move", "x": 1, "y": 1}, {"stroke_index": "0", "action": "remove"}, {}],
        CANVAS_WIDTH, CANVAS_HEIGHT,
    )

    assert changed is False
    assert len(scene.strokes) == 1


def test_run_critique_loop_applies_layout_fix_and_keeps_scene_pending():
    project = _make_project(["scene-001"])
    project.find_scene("scene-001").strokes = [_text_stroke(x=1800.0, y=100.0, content="Déborde du cadre")]
    fix_response = json.dumps({
        "sufficient": False, "reason": "texte hors cadre",
        "missing_elements": [],
        "layout_fixes": [{"stroke_index": 0, "action": "move", "x": 50.0, "y": 20.0}],
    })
    llm = FakeLLMProvider([fix_response, _sufficient_response()])
    capture = _FakeCapture()

    remaining = run_critique_loop(llm, project, capture)

    scene = project.find_scene("scene-001")
    canvas_width, _ = project.canvas_size
    assert remaining == []
    assert scene.strokes[0].points[0].x == 50.0 / 100.0 * canvas_width
    assert len(capture.calls) == 2  # ré-analysée après la correction de mise en page


def test_run_critique_loop_stops_when_layout_fix_list_is_empty_even_if_missing_elements_absent():
    project = _make_project(["scene-001"])
    llm = FakeLLMProvider([json.dumps({
        "sufficient": True, "reason": "ok", "missing_elements": [], "layout_fixes": [],
    })])
    capture = _FakeCapture()

    remaining = run_critique_loop(llm, project, capture)

    assert remaining == []
    assert len(capture.calls) == 1


def test_analyze_scene_illustration_parses_layout_fixes_field():
    scene = Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="",
                   strokes=[_text_stroke()])
    llm = FakeLLMProvider([json.dumps({
        "sufficient": False, "reason": "mal placé",
        "missing_elements": [],
        "layout_fixes": [{"stroke_index": 0, "action": "move", "x": 10, "y": 10}],
    })])

    verdict = analyze_scene_illustration(llm, scene, [b"frame"], CANVAS_WIDTH, CANVAS_HEIGHT)

    assert verdict.layout_fixes == [{"stroke_index": 0, "action": "move", "x": 10, "y": 10}]


def test_analyze_scene_illustration_sends_indexed_current_elements_in_prompt():
    scene = Scene(scene_id="s0", voice_over="v", duration_sec=5.0, visual_instruction="",
                   strokes=[_text_stroke(content="Titre"), _icon_stroke(name="sun")])
    llm = FakeLLMProvider([_sufficient_response()])

    analyze_scene_illustration(llm, scene, [b"frame"], CANVAS_WIDTH, CANVAS_HEIGHT)

    _, user_prompt, _ = llm.image_calls[0]
    assert '"index": 0' in user_prompt
    assert '"content": "Titre"' in user_prompt
    assert '"index": 1' in user_prompt
    assert '"name": "sun"' in user_prompt
