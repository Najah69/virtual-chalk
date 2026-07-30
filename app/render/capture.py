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

# Nombre de frames rendues et capturées en un seul aller-retour JS<->Python.
# Un evaluate_js par frame individuelle mesure ~300ms/frame (surcoût d'IPC,
# pas de calcul) ; regrouper par lots ramène ce surcoût à une fraction de
# ce qu'il serait sinon, sans pour autant faire transiter toute une scène
# (plusieurs Mo de PNG en base64) en un seul appel.
BATCH_SIZE = 30


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

        n = 0
        while n < frame_count:
            batch = min(BATCH_SIZE, frame_count - n)
            start_t = n / FPS
            data_urls = self.window.evaluate_js(
                f"window.renderFrames({start_t}, {batch}, {FPS})"
            )
            for i, data_url in enumerate(data_urls):
                jpg_bytes = base64.b64decode(data_url.split(",", 1)[1])
                (out_dir / f"frame_{n + i:05d}.jpg").write_bytes(jpg_bytes)
            n += batch

        return out_dir
