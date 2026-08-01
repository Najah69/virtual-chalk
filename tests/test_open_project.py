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


def test_pick_project_file_filter_is_valid_for_pywebview(monkeypatch):
    """Régression : pywebview valide les libellés de filtre de fichier
    côté Python avec une regex qui n'autorise ni tiret ni accent avant la
    parenthèse (webview.util.parse_file_type, `^([\\w ]+)\\(...`). Un
    libellé du type "Projets Virtual-Chalk (*.vchalk)" (tiret) levait une
    ValueError non rattrapée avant même l'ouverture de la boîte de
    dialogue — le bouton "Ouvrir un projet" ne faisait alors
    silencieusement rien, aucune erreur visible côté UI. On capture les
    file_types réellement passés par Api.pick_project_file et on les fait
    valider par le vrai parseur de pywebview plutôt que de dupliquer sa
    regex, pour rester vrai si elle change un jour."""
    from webview.util import parse_file_type

    captured = {}

    class FakeWindow:
        def create_file_dialog(self, dialog_type, file_types=()):
            captured["file_types"] = file_types
            return None

    monkeypatch.setattr(api_bridge.webview, "windows", [FakeWindow()])

    api = api_bridge.Api.__new__(api_bridge.Api)
    api.pick_project_file()

    assert captured["file_types"], "aucun file_types capté"
    for file_type in captured["file_types"]:
        parse_file_type(file_type)  # ne doit lever aucune ValueError


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


def test_load_project_restores_video_path_from_legacy_generic_name(monkeypatch, tmp_path):
    """Repli sur l'ancien nom générique "video.mp4" pour les projets
    générés avant le passage au nommage par slug (voir Pipeline.render)."""
    project = Project(title="t", summary="s", sections=[], scenes=[])
    api = _make_api(monkeypatch, project, tmp_path)

    project_file = tmp_path / f"project{PROJECT_FILE_EXTENSION}"
    (tmp_path / "video.mp4").write_bytes(b"fake")

    result = api.load_project(str(project_file))

    assert result == project.to_dict()
    assert api._current_project is project
    assert api._current_project_dir == tmp_path
    assert api._current_video_path == tmp_path / "video.mp4"


def test_load_project_prefers_slug_named_video_over_legacy(monkeypatch, tmp_path):
    project = Project(title="Mon Super Projet", summary="s", sections=[], scenes=[])
    api = _make_api(monkeypatch, project, tmp_path)

    project_file = tmp_path / f"project{PROJECT_FILE_EXTENSION}"
    (tmp_path / "video.mp4").write_bytes(b"legacy")
    (tmp_path / f"{project.slug}.mp4").write_bytes(b"named")

    api.load_project(str(project_file))

    assert api._current_video_path == tmp_path / f"{project.slug}.mp4"


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
