"""FrameCapture.capture_frames_at (app/render/capture.py) : capture de
quelques images à des instants précis, en mémoire — utilisé par la boucle
d'auto-critique visuelle. Le webview.Window réel est simulé (aucune vraie
fenêtre/rendu ici) ; on vérifie seulement l'orchestration des appels
evaluate_js et le décodage base64."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

from app.render.capture import FrameCapture
from app.scenes.schema import Scene


def _fake_window(frame_bytes_by_call: list[bytes]):
    """window.evaluate_js renvoie : True pour allImagesReady, un tableau
    d'un seul data URL JPEG (base64) pour chaque appel renderFrames, dans
    l'ordre des octets fournis."""
    remaining = list(frame_bytes_by_call)

    def side_effect(js: str):
        if "allImagesReady" in js:
            return True
        if "renderFrames" in js:
            raw = remaining.pop(0)
            encoded = base64.b64encode(raw).decode("ascii")
            return [f"data:image/jpeg;base64,{encoded}"]
        return None  # loadScene

    window = MagicMock()
    window.evaluate_js.side_effect = side_effect
    return window


def _make_scene(duration_sec=10.0):
    return Scene(scene_id="s0", voice_over="v", duration_sec=duration_sec, visual_instruction="")


def test_capture_frames_at_returns_decoded_bytes_for_each_timestamp():
    window = _fake_window([b"frame-one", b"frame-two"])
    capture = FrameCapture(window)

    frames = capture.capture_frames_at(_make_scene(), "chalk_board", 1920, 1080, [1.0, 5.0])

    assert frames == [b"frame-one", b"frame-two"]


def test_capture_frames_at_loads_scene_exactly_once_before_capturing():
    window = _fake_window([b"a", b"b", b"c"])
    capture = FrameCapture(window)

    capture.capture_frames_at(_make_scene(), "chalk_board", 1920, 1080, [1.0, 2.0, 3.0])

    load_scene_calls = [c for c in window.evaluate_js.call_args_list if "loadScene" in c.args[0]]
    assert len(load_scene_calls) == 1
    # loadScene doit précéder tous les renderFrames (pas d'entrelacement).
    all_calls = [c.args[0] for c in window.evaluate_js.call_args_list]
    assert "loadScene" in all_calls[0]


def test_capture_frames_at_calls_render_frames_once_per_timestamp_with_count_one():
    window = _fake_window([b"a", b"b"])
    capture = FrameCapture(window)

    capture.capture_frames_at(_make_scene(), "chalk_board", 1920, 1080, [2.5, 7.5])

    render_calls = [c.args[0] for c in window.evaluate_js.call_args_list if "renderFrames" in c.args[0]]
    assert len(render_calls) == 2
    assert "renderFrames(2.5, 1," in render_calls[0]
    assert "renderFrames(7.5, 1," in render_calls[1]


def test_capture_frames_at_returns_empty_list_for_no_timestamps():
    window = _fake_window([])
    capture = FrameCapture(window)

    frames = capture.capture_frames_at(_make_scene(), "chalk_board", 1920, 1080, [])

    assert frames == []
