from __future__ import annotations

import tempfile
import threading
import wave
from pathlib import Path

import pyttsx3

from app.tts.base import TTSProvider, VoiceProfile

# SAPI (via pyttsx3/comtypes) peut se bloquer indéfiniment sur
# engine.runAndWait() — bug connu et largement documenté de pyttsx3 sous
# Windows (event sinks COM qui s'accumulent au fil des appels répétés à
# pyttsx3.init(), un par scène). Constaté en pratique : l'application
# entière restait figée sur la barre de progression, sans aucune erreur
# visible, pendant plus d'une heure sur une génération à plusieurs scènes
# (jamais reproduit sur les scripts courts utilisés en test). Un délai
# maximal transforme ce blocage silencieux en une erreur explicite que
# Pipeline/Api peuvent rattraper et remonter à l'UI, plutôt que de geler
# tout le pipeline (et donc toute l'app, aucune autre requête JS<->Python
# ne peut progresser tant que celle-ci n'est pas retournée) indéfiniment.
SYNTHESIS_TIMEOUT_SEC = 60.0


class SapiLocalProvider(TTSProvider):
    """Voix Windows intégrée (SAPI5) — gratuite, fonctionne hors-ligne."""

    def synthesize(self, text: str, profile: VoiceProfile) -> tuple[Path, float]:
        engine = pyttsx3.init()
        if profile and profile.voice_id:
            engine.setProperty("voice", profile.voice_id)

        out_path = Path(tempfile.mktemp(suffix=".wav"))
        errors: list[BaseException] = []

        def _run() -> None:
            try:
                engine.save_to_file(text, str(out_path))
                engine.runAndWait()
            except BaseException as exc:  # noqa: BLE001 - relayé au thread appelant ci-dessous
                errors.append(exc)

        # Exécuté dans un thread à part (jetable, "daemon" : si SAPI est
        # bien bloqué pour de bon, ce thread ne se terminera jamais tout
        # seul, mais ne doit pas empêcher le process de quitter) plutôt
        # que directement dans ce thread-ci : .join(timeout) est le seul
        # moyen de reprendre la main sur un appel COM synchrone qui ne
        # respecte aucun timeout qu'on pourrait lui passer nous-mêmes.
        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(SYNTHESIS_TIMEOUT_SEC)
        if worker.is_alive():
            raise TimeoutError(
                f"La synthèse vocale Windows (SAPI) ne répond plus après "
                f"{SYNTHESIS_TIMEOUT_SEC:.0f}s — problème connu du moteur de "
                "voix intégré à Windows. Réessayez, ou choisissez une autre "
                "voix dans les réglages."
            )
        if errors:
            raise errors[0]

        with wave.open(str(out_path), "rb") as wav_file:
            duration = wav_file.getnframes() / float(wav_file.getframerate())

        return out_path, duration

    @staticmethod
    def list_system_voices() -> list[VoiceProfile]:
        engine = pyttsx3.init()
        return [
            VoiceProfile(name=v.name, provider="sapi_local", voice_id=v.id)
            for v in engine.getProperty("voices")
        ]
