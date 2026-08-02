"""Bug rencontré en pratique (retour utilisateur, capture d'écran) : un
encodage de scène a échoué avec un code de sortie opaque (3752568763, soit
0xDFABA7BB une fois en hexadécimal — une valeur système sans rapport avec
ffmpeg lui-même) et l'UI n'affichait que ce nombre, sans le moindre indice
sur la cause réelle. En rejouant la commande manuellement, la cause s'est
révélée être "Cannot allocate memory" dans le filtre `scale` (mémoire
système épuisée en cours d'encodage) — visible dans stderr, jamais capturé
par l'ancien subprocess.run(cmd, check=True).

encode_scene/concat_scenes utilisent maintenant _run(), qui capture stderr
et lève FFmpegError avec les dernières lignes utiles plutôt que de laisser
remonter un CalledProcessError sans contexte."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.render.ffmpeg_wrapper import FFmpegError, _run


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stderr: str):
        self.returncode = returncode
        self.stderr = stderr


def test_run_raises_ffmpeg_error_with_stderr_tail_on_failure(monkeypatch):
    stderr = "\n".join(f"frame={i}" for i in range(30)) + "\n[vf#0:0] Error while filtering: Cannot allocate memory"
    monkeypatch.setattr(
        "app.render.ffmpeg_wrapper.subprocess.run",
        lambda cmd, capture_output, text: _FakeCompletedProcess(1, stderr),
    )

    with pytest.raises(FFmpegError) as exc_info:
        _run(["ffmpeg", "-y"])

    message = str(exc_info.value)
    assert "Cannot allocate memory" in message
    assert "frame=0" not in message  # tronqué aux dernières lignes seulement


def test_run_does_not_raise_on_success(monkeypatch):
    monkeypatch.setattr(
        "app.render.ffmpeg_wrapper.subprocess.run",
        lambda cmd, capture_output, text: _FakeCompletedProcess(0, ""),
    )

    _run(["ffmpeg", "-y"])  # ne doit lever aucune exception


def test_run_reports_real_returncode(monkeypatch):
    monkeypatch.setattr(
        "app.render.ffmpeg_wrapper.subprocess.run",
        lambda cmd, capture_output, text: _FakeCompletedProcess(3752568763, "erreur système opaque"),
    )

    with pytest.raises(FFmpegError, match="3752568763"):
        _run(["ffmpeg", "-y"])
