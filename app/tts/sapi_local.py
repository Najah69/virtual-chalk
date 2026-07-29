from __future__ import annotations

import tempfile
import wave
from pathlib import Path

import pyttsx3

from app.tts.base import TTSProvider, VoiceProfile


class SapiLocalProvider(TTSProvider):
    """Voix Windows intégrée (SAPI5) — gratuite, fonctionne hors-ligne."""

    def synthesize(self, text: str, profile: VoiceProfile) -> tuple[Path, float]:
        engine = pyttsx3.init()
        if profile and profile.voice_id:
            engine.setProperty("voice", profile.voice_id)

        out_path = Path(tempfile.mktemp(suffix=".wav"))
        engine.save_to_file(text, str(out_path))
        engine.runAndWait()

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
