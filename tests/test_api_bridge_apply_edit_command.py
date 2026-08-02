"""Bug rencontré en pratique (retour utilisateur) : une commande NL du type
"dessine la molécule Sucre+CO2" affichait "Modifications appliquées et
scènes concernées re-rendues" mais ne changeait rien à l'écran ni sur
disque. Deux causes distinctes, corrigées ensemble :

1. Api.apply_edit_command n'appelait jamais Pipeline.generate_diagrams —
   un stroke kind="diagram" ajouté par replace_scene_content/insert_scene
   restait un simple point d'ancrage, jamais vectorisé, donc invisible au
   rendu (voir app/pipeline.py::finish_generation, qui appelle
   generate_diagrams après generate_script mais AVANT tout rendu — la voie
   d'édition NL en était dépourvue).
2. _apply_replace_scene_content (app/edit/nl_commands.py) marquait la scène
   "changée" même quand ni voice_over ni visual_elements n'étaient présents
   dans l'action produite par le LLM — un no-op se faisait donc passer pour
   un succès.

Pipeline entièrement simulé — aucun vrai appel LLM/TTS/ffmpeg/Gemini ici."""

from __future__ import annotations

import json
from pathlib import Path

import app.api_bridge as api_bridge
from app.scenes.schema import Point, Project, Scene, Stroke
from tests.conftest import FakeLLMProvider


class _FakePipeline:
    def __init__(self, llm):
        self.llm = llm
        self.generate_diagrams_calls = 0
        self.resynthesized_scene_ids: list[str] = []
        self.render_calls = 0

    def generate_diagrams(self, project, on_progress=None):
        self.generate_diagrams_calls += 1
        # Simule une vectorisation réussie (ce que fait en pratique
        # generate_diagram_points côté Gemini) : un diagram inerte à 1
        # point devient une forme réellement tracée.
        for scene in project.scenes:
            for stroke in scene.strokes:
                if stroke.kind == "diagram":
                    stroke.points = [Point(0, 0), Point(10, 10)]
                    stroke.kind = "shape"

    def resynthesize_scene(self, scene, voice_profile):
        self.resynthesized_scene_ids.append(scene.scene_id)

    def render(self, project, out_dir, on_progress=None):
        self.render_calls += 1
        return Path("video.mp4")


def _make_api(monkeypatch, scenes, llm_responses):
    api = api_bridge.Api.__new__(api_bridge.Api)  # évite Settings.load() (I/O disque)
    api._current_project = Project(title="t", summary="s", sections=[], scenes=scenes)
    api._current_project_dir = Path(".")
    api._current_project_path = None
    api._current_video_path = None
    api._current_voice_profile = None

    fake_pipeline = _FakePipeline(FakeLLMProvider(llm_responses))
    monkeypatch.setattr(api_bridge.Api, "_build_pipeline", lambda self, voice_profile=None: fake_pipeline)
    monkeypatch.setattr(api_bridge, "save_project_file", lambda project, path: None)
    return api, fake_pipeline


def _scene():
    return Scene(scene_id="scene-001", voice_over="La photosynthèse.", duration_sec=5.0, visual_instruction="")


def test_apply_edit_command_vectorizes_new_diagram_before_rendering(monkeypatch):
    actions = {
        "actions": [{
            "action": "replace_scene_content",
            "scene_index": 0,
            "visual_elements": [
                {"type": "diagram", "description": "molécule de sucre + CO2", "x": 50, "y": 50, "width": 30, "height": 30},
            ],
        }],
    }
    api, fake_pipeline = _make_api(monkeypatch, [_scene()], [json.dumps(actions)])

    result = api.apply_edit_command("dessine la molécule Sucre+CO2")

    assert result["error"] is None
    assert fake_pipeline.generate_diagrams_calls == 1
    assert fake_pipeline.render_calls == 1
    scene = api._current_project.find_scene("scene-001")
    assert scene.strokes[0].kind == "shape"
    assert len(scene.strokes[0].points) == 2


def test_apply_edit_command_calls_generate_diagrams_even_with_no_diagram_pending(monkeypatch):
    """generate_diagrams est un no-op bon marché quand rien n'est en
    attente (voir Pipeline.generate_diagrams) : on peut donc l'appeler sans
    condition à chaque édition plutôt que de détecter nous-mêmes si une
    action en a posé un."""
    actions = {"actions": [{"action": "set_theme", "theme": "whiteboard_marker"}]}
    api, fake_pipeline = _make_api(monkeypatch, [_scene()], [json.dumps(actions)])

    api.apply_edit_command("change de thème")

    assert fake_pipeline.generate_diagrams_calls == 1


def test_apply_edit_command_empty_replace_scene_content_is_skipped_not_a_false_success(monkeypatch):
    """Régression : le LLM peut renvoyer replace_scene_content sans
    voice_over ni visual_elements (ex: mauvaise compréhension de la
    commande) — ne doit plus être compté comme une modification réussie."""
    actions = {"actions": [{"action": "replace_scene_content", "scene_index": 0}]}
    api, fake_pipeline = _make_api(monkeypatch, [_scene()], [json.dumps(actions)])

    result = api.apply_edit_command("dessine quelque chose")

    assert result["error"] is None
    assert result["changed_scene_ids"] == []
    assert len(result["skipped_actions"]) == 1
    assert fake_pipeline.render_calls == 0
