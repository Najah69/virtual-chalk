from __future__ import annotations

import webview

from app.api_bridge import Api
from app.paths import APP_DIR, UI_DIR
from app.render.window_registry import set_render_window

UI_INDEX = UI_DIR / "index.html"
RENDER_TEMPLATE = APP_DIR / "render" / "web_template" / "index.html"


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
