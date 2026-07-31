from __future__ import annotations

import logging
import sys

import webview

from app.api_bridge import Api
from app.paths import APP_DIR, UI_DIR
from app.render.window_registry import set_render_window
from app.scenes.project_file import PROJECT_FILE_EXTENSION

UI_INDEX = UI_DIR / "index.html"
RENDER_TEMPLATE = APP_DIR / "render" / "web_template" / "index.html"

logger = logging.getLogger(__name__)


def main() -> None:
    api = Api()
    webview.create_window(
        "Virtual-Chalk",
        url=str(UI_INDEX),
        js_api=api,
        width=1100,
        height=760,
        min_size=(900, 620),
    )
    render_window = webview.create_window(
        "Virtual-Chalk Render Surface",
        url=str(RENDER_TEMPLATE),
        width=1920,
        height=1080,
        hidden=True,
    )
    set_render_window(render_window)

    # Lancement par double-clic sur un fichier projet (association de
    # fichier .vchalk, voir build/installer.iss) : Windows passe son
    # chemin en premier argument — ouvre directement l'éditeur dessus
    # plutôt que de forcer l'utilisateur à repasser par "Ouvrir un projet"
    # dans l'assistant. Le chemin peut contenir des espaces (déjà géré par
    # Windows/PyInstaller côté découpage des arguments) mais reste un seul
    # sys.argv[1].
    project_path = sys.argv[1] if len(sys.argv) > 1 else None
    if project_path and project_path.lower().endswith(PROJECT_FILE_EXTENSION):
        try:
            api.open_project_file(project_path)
        except Exception:
            logger.exception("Échec de l'ouverture du projet passé en argument : %r", project_path)

    webview.start()


if __name__ == "__main__":
    main()
