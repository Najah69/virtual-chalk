from __future__ import annotations

import base64
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import webview

from app.scenes.schema import Scene

FPS = 30
TEMPLATE_URL = "web_template/index.html"


class FrameCapture:
    """Pilote une horloge virtuelle : demande au JS de dessiner l'état exact
    à t=n/fps puis capture l'image, pour une synchro audio/vidéo parfaite
    indépendante de la vitesse de la machine (pas de perte de frame).

    La capture passe par `canvas.toDataURL()` côté JS plutôt qu'une API de
    screenshot native (non garantie selon la version de pywebview)."""

    def __init__(self, window: webview.Window):
        self.window = window

    def render_scene_frames(self, scene: Scene, theme: str) -> Path:
        out_dir = Path(tempfile.mkdtemp(prefix=f"vc_{scene.scene_id}_"))
        frame_count = max(1, int(scene.duration_sec * FPS))

        self.window.evaluate_js(
            f"window.loadScene({json.dumps(asdict(scene))}, {json.dumps(theme)})"
        )

        for n in range(frame_count):
            t = n / FPS
            self.window.evaluate_js(f"window.renderAtTime({t})")
            data_url = self.window.evaluate_js(
                "document.getElementById('stage').toDataURL('image/png')"
            )
            png_bytes = base64.b64decode(data_url.split(",", 1)[1])
            (out_dir / f"frame_{n:05d}.png").write_bytes(png_bytes)

        return out_dir
