from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

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


def _content_json(video_filename: str, bookmarks: list[dict]) -> dict:
    return {
        "interactiveVideo": {
            "video": {"files": [{"path": video_filename, "mime": "video/mp4"}]},
            "bookmarks": bookmarks,
            "assets": [],
        }
    }


def build_h5p(video_path: Path, bookmarks: list[dict], out_path: Path) -> Path:
    """Construit un .h5p autour du MP4 rendu, avec les librairies
    H5P.InteractiveVideo embarquées localement (pas de téléchargement)."""
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("h5p.json", json.dumps(_h5p_json(video_path.stem), indent=2))
        zf.writestr("content/content.json", json.dumps(_content_json("video.mp4", bookmarks), indent=2))
        zf.write(video_path, "content/video.mp4")

        if H5P_LIBRARIES_DIR.exists():
            for lib_file in H5P_LIBRARIES_DIR.rglob("*"):
                if lib_file.is_file():
                    zf.write(lib_file, f"libraries/{lib_file.relative_to(H5P_LIBRARIES_DIR)}")

    return out_path
