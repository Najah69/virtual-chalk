"""Résolution de chemins cohérente entre exécution depuis les sources et
exécution figée (PyInstaller).

Le script `__main__` figé par PyInstaller n'a pas son `__file__` résolu
relativement à `_MEIPASS`/`_internal` comme les modules importés normalement
(voir `app/main.py`) — centralisé ici pour que tout module ayant besoin
d'ouvrir une fenêtre UI (main.py, api_bridge.py...) reste cohérent plutôt
que de dupliquer cette logique déjà sujette à bug une fois."""

from __future__ import annotations

import sys
from pathlib import Path


def base_dir() -> Path:
    """Racine du projet (contient `app/`, `ui/`, `resources/`) — `_internal`
    en exécution figée, racine du dépôt en développement."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


UI_DIR = base_dir() / "ui"
APP_DIR = base_dir() / "app"
RESOURCES_DIR = base_dir() / "resources"
