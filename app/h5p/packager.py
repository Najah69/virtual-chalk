from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.h5p.library_selection import libraries_for_project

H5P_LIBRARIES_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "h5p_libraries"


def _interactive_video_version() -> tuple[int, int]:
    """Lit la version réellement embarquée dans resources/h5p_libraries/
    plutôt que de la figer en dur, pour ne jamais désynchroniser h5p.json
    de ce qui est effectivement présent dans le zip (Moodle rejette un
    .h5p qui déclare une version de librairie absente du paquet)."""
    matches = sorted(H5P_LIBRARIES_DIR.glob("H5P.InteractiveVideo-*"))
    if not matches:
        raise FileNotFoundError(
            f"H5P.InteractiveVideo introuvable dans {H5P_LIBRARIES_DIR} — "
            "voir resources/h5p_libraries/README.txt"
        )
    library_json = json.loads((matches[0] / "library.json").read_text(encoding="utf-8"))
    return library_json["majorVersion"], library_json["minorVersion"]


def _h5p_json(title: str) -> dict:
    major, minor = _interactive_video_version()
    return {
        "title": title,
        "mainLibrary": "H5P.InteractiveVideo",
        "language": "und",
        "preloadedDependencies": [
            {"machineName": "H5P.InteractiveVideo", "majorVersion": major, "minorVersion": minor},
        ],
    }


def _content_json(video_filename: str, bookmarks: list[dict], interactions: list[dict]) -> dict:
    # bookmarks ET interactions vivent tous les deux sous assets, pas comme
    # champs directs de interactiveVideo (vérifié dans semantics.json —
    # les y mettre à plat les rend silencieusement ignorés par Moodle).
    return {
        "interactiveVideo": {
            "video": {"files": [{"path": video_filename, "mime": "video/mp4"}]},
            "assets": {
                "interactions": interactions,
                "bookmarks": bookmarks,
            },
        }
    }


def build_h5p(video_path: Path, bookmarks: list[dict], out_path: Path,
              interactions: list[dict] | None = None, exercise_types: set[str] | None = None) -> Path:
    """Construit un .h5p autour du MP4 rendu, avec les librairies
    H5P.InteractiveVideo embarquées localement (pas de téléchargement).
    N'embarque que les librairies d'exercice réellement utilisées par ce
    projet (exercise_types), pas les 4 types systématiquement."""
    interactions = interactions or []
    needed_folders = libraries_for_project(exercise_types or set())

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("h5p.json", json.dumps(_h5p_json(video_path.stem), indent=2))
        zf.writestr("content/content.json", json.dumps(_content_json("video.mp4", bookmarks, interactions), indent=2))
        zf.write(video_path, "content/video.mp4")

        for folder_name in needed_folders:
            folder = H5P_LIBRARIES_DIR / folder_name
            if not folder.exists():
                raise FileNotFoundError(f"Librairie H5P manquante: {folder}")
            for lib_file in folder.rglob("*"):
                if lib_file.is_file():
                    zf.write(lib_file, f"libraries/{lib_file.relative_to(H5P_LIBRARIES_DIR)}")

    return out_path
