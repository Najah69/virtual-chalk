from __future__ import annotations

from pathlib import Path

import webview

from app.api_bridge import Api

UI_INDEX = Path(__file__).resolve().parent.parent / "ui" / "index.html"


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
    webview.start()


if __name__ == "__main__":
    main()
