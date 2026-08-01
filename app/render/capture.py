from __future__ import annotations

import base64
import json
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import webview

from app.scenes.schema import Scene

FPS = 30
TEMPLATE_URL = "web_template/index.html"

# Un stroke kind="image" décode son image de façon asynchrone côté JS
# (voir web_template/index.html::loadScene — même un data URI n'est pas
# garanti synchrone, et evaluate_js ne résout pas correctement une Promise
# renvoyée, testé empiriquement). Délai maximal d'attente avant de rendre
# quand même (mieux vaut une image manquante sur une frame qu'un pipeline
# qui reste bloqué indéfiniment sur un décodage qui ne se termine jamais).
IMAGE_DECODE_TIMEOUT_SEC = 5.0
IMAGE_DECODE_POLL_INTERVAL_SEC = 0.05

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

    def render_scene_frames(self, scene: Scene, theme: str,
                             canvas_width: float, canvas_height: float) -> Path:
        out_dir = Path(tempfile.mkdtemp(prefix=f"vc_{scene.scene_id}_"))
        frame_count = max(1, int(scene.duration_sec * FPS))

        # canvas_width/height (voir Project.canvas_size) redimensionnent le
        # <canvas> AVANT le dessin du fond (window.loadScene) : un canvas
        # HTML n'a pas de taille "par défaut" liée à la fenêtre qui le
        # contient, son backing store (et donc toDataURL()) suit toujours
        # ses attributs width/height, indépendamment de la taille de la
        # fenêtre pywebview (cachée) qui l'héberge.
        self.window.evaluate_js(
            f"window.loadScene({json.dumps(asdict(scene))}, {json.dumps(theme)}, "
            f"{canvas_width}, {canvas_height})"
        )
        self._wait_for_images_ready()

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

    def _wait_for_images_ready(self) -> None:
        """No-op immédiat si la scène n'a aucun stroke "image" (voir
        window.allImagesReady). Sinon, laisse le moteur JS quelques
        allers-retours pour terminer le décodage avant de commencer à
        capturer des frames — sans quoi les premières frames dessineraient
        une image absente (rien à drawImage) même si elle finit par être
        prête un peu plus tard."""
        deadline = time.monotonic() + IMAGE_DECODE_TIMEOUT_SEC
        while not self.window.evaluate_js("window.allImagesReady()"):
            if time.monotonic() >= deadline:
                break
            time.sleep(IMAGE_DECODE_POLL_INTERVAL_SEC)
