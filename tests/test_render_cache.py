"""app/render/partial_render.py : logique de cache de render_all (ne
re-rend que les scènes dont le content_hash a changé, mais retourne
TOUJOURS le chemin de toutes les scènes dans l'ordre — bug historique
corrigé pendant cette session, voir docs/architecture.md) et résolution
sûre de scene_id dans render_scene (Tâche B). Aucun vrai rendu/capture
d'écran/ffmpeg ici : render_scene est entièrement simulé."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.render import partial_render
from app.scenes.schema import Project, Scene


def _make_project() -> Project:
    scenes = [
        Scene(scene_id="s0", voice_over="Zéro", duration_sec=5, visual_instruction=""),
        Scene(scene_id="s1", voice_over="Un", duration_sec=5, visual_instruction=""),
        Scene(scene_id="s2", voice_over="Deux", duration_sec=5, visual_instruction=""),
    ]
    return Project(title="t", summary="s", sections=[], scenes=scenes, theme="chalk_board")


def test_render_scene_raises_value_error_for_unknown_scene_id(tmp_path):
    project = _make_project()
    with pytest.raises(ValueError, match="introuvable"):
        partial_render.render_scene(project, "does-not-exist", tmp_path)


def test_render_all_returns_every_scene_path_in_order(tmp_path, monkeypatch):
    project = _make_project()
    rendered_calls = []

    def fake_render_scene(project, scene_id, scenes_dir):
        rendered_calls.append(scene_id)
        path = scenes_dir / f"{scene_id}.mp4"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake video")
        project.find_scene(scene_id).content_hash = partial_render._hash_scene(
            project.find_scene(scene_id)
        )
        return path

    monkeypatch.setattr(partial_render, "render_scene", fake_render_scene)

    paths = partial_render.render_all(project, tmp_path)

    assert rendered_calls == ["s0", "s1", "s2"]
    assert [p.name for p in paths] == ["s0.mp4", "s1.mp4", "s2.mp4"]


def test_render_all_skips_unchanged_scenes_but_still_returns_their_path(tmp_path, monkeypatch):
    project = _make_project()

    def fake_render_scene(project, scene_id, scenes_dir):
        scenes_dir.mkdir(parents=True, exist_ok=True)
        path = scenes_dir / f"{scene_id}.mp4"
        path.write_bytes(b"fake video")
        project.find_scene(scene_id).content_hash = partial_render._hash_scene(
            project.find_scene(scene_id)
        )
        return path

    monkeypatch.setattr(partial_render, "render_scene", fake_render_scene)

    # Premier rendu complet : les 3 scènes sont (fake-)rendues et cachées.
    first_paths = partial_render.render_all(project, tmp_path)
    assert len(first_paths) == 3

    # On modifie le contenu d'une seule scène (s1) sans toucher aux autres.
    project.scenes[1].voice_over = "Un — modifié"

    render_calls = []
    original = fake_render_scene

    def counting_render_scene(project, scene_id, scenes_dir):
        render_calls.append(scene_id)
        return original(project, scene_id, scenes_dir)

    monkeypatch.setattr(partial_render, "render_scene", counting_render_scene)

    second_paths = partial_render.render_all(project, tmp_path)

    # Seule s1 (modifiée) doit être re-rendue...
    assert render_calls == ["s1"]
    # ...mais le résultat contient bien les 3 scènes, dans l'ordre — c'est
    # le bug historique (scènes inchangées silencieusement absentes du
    # montage final) que ce test verrouille.
    assert [p.name for p in second_paths] == ["s0.mp4", "s1.mp4", "s2.mp4"]


def test_render_all_rerenders_scene_whose_cached_file_was_deleted(tmp_path, monkeypatch):
    project = _make_project()

    def fake_render_scene(project, scene_id, scenes_dir):
        scenes_dir.mkdir(parents=True, exist_ok=True)
        path = scenes_dir / f"{scene_id}.mp4"
        path.write_bytes(b"fake video")
        project.find_scene(scene_id).content_hash = partial_render._hash_scene(
            project.find_scene(scene_id)
        )
        return path

    monkeypatch.setattr(partial_render, "render_scene", fake_render_scene)
    partial_render.render_all(project, tmp_path)

    (tmp_path / "s1.mp4").unlink()

    render_calls = []
    original = fake_render_scene

    def counting_render_scene(project, scene_id, scenes_dir):
        render_calls.append(scene_id)
        return original(project, scene_id, scenes_dir)

    monkeypatch.setattr(partial_render, "render_scene", counting_render_scene)
    partial_render.render_all(project, tmp_path)

    assert render_calls == ["s1"]
