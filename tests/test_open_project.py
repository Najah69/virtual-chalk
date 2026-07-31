"""Ouverture d'un projet existant (.vchalk) sans repasser par l'assistant :
Api.load_project/open_project_file, et l'extension elle-même
(PROJECT_FILE_EXTENSION). Aucun vrai appel pywebview/fichier réel ici."""

from __future__ import annotations

from pathlib import Path

import app.api_bridge as api_bridge
from app.scenes.project_file import PROJECT_FILE_EXTENSION
from app.scenes.schema import Project


def test_project_file_extension_is_vchalk():
    assert PROJECT_FILE_EXTENSION == ".vchalk"


def _make_api(monkeypatch, project, tmp_path):
    api = api_bridge.Api.__new__(api_bridge.Api)
    api.settings = None
    api._current_project = None
    api._current_project_path = None
    api._current_project_dir = None
    api._current_video_path = None
    api._current_voice_profile = None
    monkeypatch.setattr(api_bridge, "load_project_file", lambda path: project)
    return api


def test_load_project_restores_video_path_when_it_exists(monkeypatch, tmp_path):
    project = Project(title="t", summary="s", sections=[], scenes=[])
    api = _make_api(monkeypatch, project, tmp_path)

    project_file = tmp_path / f"project{PROJECT_FILE_EXTENSION}"
    (tmp_path / "video.mp4").write_bytes(b"fake")

    result = api.load_project(str(project_file))

    assert result == project.to_dict()
    assert api._current_project is project
    assert api._current_project_dir == tmp_path
    assert api._current_video_path == tmp_path / "video.mp4"


def test_load_project_leaves_video_path_none_when_video_missing(monkeypatch, tmp_path):
    project = Project(title="t", summary="s", sections=[], scenes=[])
    api = _make_api(monkeypatch, project, tmp_path)

    project_file = tmp_path / f"project{PROJECT_FILE_EXTENSION}"
    result = api.load_project(str(project_file))

    assert result == project.to_dict()
    assert api._current_video_path is None


def test_open_project_file_loads_then_opens_editor(monkeypatch, tmp_path):
    project = Project(title="t", summary="s", sections=[], scenes=[])
    api = _make_api(monkeypatch, project, tmp_path)

    editor_opened = []
    monkeypatch.setattr(api_bridge.Api, "open_editor", lambda self: editor_opened.append(True))

    project_file = tmp_path / f"project{PROJECT_FILE_EXTENSION}"
    api.open_project_file(str(project_file))

    assert api._current_project is project
    assert editor_opened == [True]


def test_get_current_project_path_uses_exact_opened_file_not_a_guess(monkeypatch, tmp_path):
    """Régression : un fichier .vchalk ouvert sous un nom quelconque (pas
    "project.vchalk") doit être rechargeable par editor.js via
    get_current_project_path() — reconstruire "{dossier}/project{EXT}"
    (l'ancien comportement) pointait vers un fichier inexistant dès que
    le fichier ouvert n'avait pas ce nom exact, cassant silencieusement
    l'éditeur (scènes jamais affichées)."""
    project = Project(title="t", summary="s", sections=[], scenes=[])
    api = _make_api(monkeypatch, project, tmp_path)

    renamed_file = tmp_path / "mon_projet_perso.vchalk"
    api.load_project(str(renamed_file))

    assert api.get_current_project_path() == str(renamed_file)


def test_get_current_project_path_falls_back_to_canonical_name_for_fresh_generation(monkeypatch, tmp_path):
    """Après start_pipeline (pas load_project), _current_project_path
    n'est jamais renseigné : le repli sur le nom canonique reste correct
    puisque Pipeline.run sauvegarde toujours à cet emplacement."""
    api = _make_api(monkeypatch, None, tmp_path)
    api._current_project_dir = tmp_path

    assert api.get_current_project_path() == str(tmp_path / f"project{PROJECT_FILE_EXTENSION}")


def test_save_after_edit_writes_back_to_the_exact_opened_file(monkeypatch, tmp_path):
    """Régression : éditer un projet ouvert sous un nom personnalisé ne
    doit pas silencieusement créer un "project.vchalk" à côté — les
    modifications doivent être sauvegardées dans le fichier réellement
    ouvert."""
    project = Project(title="t", summary="s", sections=[], scenes=[])
    api = _make_api(monkeypatch, project, tmp_path)

    renamed_file = tmp_path / "mon_projet_perso.vchalk"
    api.load_project(str(renamed_file))

    assert api._current_project_save_path() == renamed_file
