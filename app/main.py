from __future__ import annotations

import logging
import sys
import time

import webview

from app.api_bridge import Api
from app.paths import APP_DIR, RESOURCES_DIR, UI_DIR
from app.render.window_registry import set_render_window
from app.scenes.project_file import PROJECT_FILE_EXTENSION

UI_INDEX = UI_DIR / "index.html"
SPLASH_HTML = UI_DIR / "splash.html"
RENDER_TEMPLATE = APP_DIR / "render" / "web_template" / "index.html"
APP_ICON = RESOURCES_DIR / "branding" / "app_icon.ico"

# Durée minimale d'affichage du splash-screen (secondes) — sans ce délai
# artificiel, l'app démarre trop vite (aucun chargement lourd avant que la
# fenêtre principale soit prête) pour que l'image ait le temps d'être vue.
SPLASH_MIN_DISPLAY_SEC = 1.8
SPLASH_SIZE = 480

logger = logging.getLogger(__name__)


def main() -> None:
    api = Api()

    # Splash-screen (retour utilisateur : afficher la bannière en grand au
    # lancement) — fenêtre sans chrome, créée EN PREMIER pour être la
    # toute première chose visible, pendant que le reste de l'app
    # s'initialise. x/y non précisés : pywebview centre par défaut.
    splash = webview.create_window(
        "Virtual-Chalk", url=str(SPLASH_HTML),
        width=SPLASH_SIZE, height=SPLASH_SIZE, resizable=False, frameless=True, on_top=True,
    )

    # Fenêtre principale créée CACHÉE : révélée une fois le splash écoulé
    # (voir _reveal_windows ci-dessous), pour que ce soit bien le
    # splash-screen la première chose que l'utilisateur voit, pas les deux
    # superposées.
    main_window = webview.create_window(
        "Virtual-Chalk",
        url=str(UI_INDEX),
        js_api=api,
        width=1100,
        height=760,
        min_size=(900, 620),
        hidden=True,
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
    opened_project_directly = False
    if project_path and project_path.lower().endswith(PROJECT_FILE_EXTENSION):
        try:
            api.open_project_file(project_path)
            opened_project_directly = True
        except Exception:
            logger.exception("Échec de l'ouverture du projet passé en argument : %r", project_path)

    def _reveal_windows():
        time.sleep(SPLASH_MIN_DISPLAY_SEC)
        splash.destroy()
        # Si un projet a été ouvert directement, Api.open_project_file a
        # déjà fait apparaître sa propre fenêtre Éditeur — révéler EN PLUS
        # la fenêtre assistant (vide, étape 1) ne ferait qu'ajouter une
        # deuxième fenêtre sans intérêt derrière l'éditeur.
        if not opened_project_directly:
            main_window.show()

    webview.start(_reveal_windows, icon=str(APP_ICON))


if __name__ == "__main__":
    main()
