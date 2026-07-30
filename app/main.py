from __future__ import annotations

import sys
from pathlib import Path

import webview

from app.api_bridge import Api
from app.render.window_registry import set_render_window

if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys._MEIPASS)
    _APP_DIR = _BASE_DIR / "app"
else:
    _APP_DIR = Path(__file__).resolve().parent
    _BASE_DIR = _APP_DIR.parent

UI_INDEX = _BASE_DIR / "ui" / "index.html"
RENDER_TEMPLATE = _APP_DIR / "render" / "web_template" / "index.html"


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
    webview.start()


if __name__ == "__main__":
    main()
