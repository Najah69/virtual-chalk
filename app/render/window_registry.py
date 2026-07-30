from __future__ import annotations

import webview

# La capture de frames (capture.py) a besoin d'une fenêtre pywebview dédiée
# affichant web_template/index.html, distincte de la fenêtre principale qui
# affiche l'assistant (ui/index.html) — webview.windows[0] ne convient pas,
# c'est la fenêtre visible de l'assistant. Initialisée une fois dans main.py.
_render_window: webview.Window | None = None


def set_render_window(window: webview.Window) -> None:
    global _render_window
    _render_window = window


def get_render_window() -> webview.Window:
    if _render_window is None:
        raise RuntimeError("Fenêtre de rendu non initialisée — voir app/main.py")
    return _render_window
