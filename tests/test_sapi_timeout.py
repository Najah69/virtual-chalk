"""Régression : app/tts/sapi_local.py::SapiLocalProvider.synthesize se
bloquait indéfiniment si le moteur SAPI (via pyttsx3/comtypes) ne
retournait jamais de engine.runAndWait() — bug connu de pyttsx3 sous
Windows, constaté en pratique sur une génération réelle à plusieurs
scènes (l'app entière restait figée plus d'une heure, sans erreur
visible). Aucun vrai appel SAPI ici : pyttsx3.init() est simulé."""

from __future__ import annotations

import time
import wave

import pytest

import app.tts.sapi_local as sapi_local_module
from app.tts.base import VoiceProfile
from app.tts.sapi_local import SapiLocalProvider


class _FakeEngineCompletesNormally:
    def setProperty(self, name, value):
        pass

    def save_to_file(self, text, path):
        self._path = path

    def runAndWait(self):
        with wave.open(self._path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 1600)  # 0.1s de silence


class _FakeEngineHangsForever:
    def setProperty(self, name, value):
        pass

    def save_to_file(self, text, path):
        pass

    def runAndWait(self):
        # Simule un engine.runAndWait() qui ne retourne jamais (SAPI
        # bloqué) — le thread reste "vivant" indéfiniment, exactement
        # comme le cas réel observé.
        time.sleep(3600)


class _FakeEngineRaises:
    def setProperty(self, name, value):
        pass

    def save_to_file(self, text, path):
        pass

    def runAndWait(self):
        raise RuntimeError("SAPI a explicitement échoué")


def test_synthesize_completes_normally_when_engine_responds(monkeypatch, tmp_path):
    monkeypatch.setattr(sapi_local_module.pyttsx3, "init", lambda: _FakeEngineCompletesNormally())

    provider = SapiLocalProvider()
    audio_path, duration = provider.synthesize("Bonjour", VoiceProfile(name="v", provider="sapi_local"))

    assert audio_path.exists()
    assert duration > 0


def test_synthesize_raises_timeout_error_instead_of_hanging_forever(monkeypatch):
    monkeypatch.setattr(sapi_local_module.pyttsx3, "init", lambda: _FakeEngineHangsForever())
    # Timeout raccourci pour que le test lui-même reste rapide (pas de
    # vraie attente de 60s) — ne change que la CONSTANTE, pas le
    # mécanisme testé (thread + .join(timeout)).
    monkeypatch.setattr(sapi_local_module, "SYNTHESIS_TIMEOUT_SEC", 0.2)

    provider = SapiLocalProvider()
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        provider.synthesize("Bonjour", VoiceProfile(name="v", provider="sapi_local"))
    elapsed = time.monotonic() - start

    # La preuve que ça n'attend PAS indéfiniment : le test lui-même doit
    # se terminer vite, borné par le timeout raccourci (avec une marge
    # généreuse pour la lenteur d'une machine de CI).
    assert elapsed < 5.0


def test_synthesize_propagates_exceptions_raised_inside_the_worker_thread(monkeypatch):
    monkeypatch.setattr(sapi_local_module.pyttsx3, "init", lambda: _FakeEngineRaises())

    provider = SapiLocalProvider()
    with pytest.raises(RuntimeError, match="SAPI a explicitement échoué"):
        provider.synthesize("Bonjour", VoiceProfile(name="v", provider="sapi_local"))
