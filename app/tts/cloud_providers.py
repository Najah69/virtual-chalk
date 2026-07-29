from __future__ import annotations

from pathlib import Path

from app.tts.base import TTSProvider, VoiceProfile

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_CLONE_URL = "https://api.elevenlabs.io/v1/voices/add"


class ElevenLabsProvider(TTSProvider):
    """Option payante, opt-in : nécessaire pour un vrai clonage de voix
    (impossible correctement en local sur une machine modeste)."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def synthesize(self, text: str, profile: VoiceProfile) -> tuple[Path, float]:
        raise NotImplementedError("TODO: appel API ElevenLabs text-to-speech")

    def clone_voice(self, name: str, sample_audio_paths: list[Path]) -> VoiceProfile:
        raise NotImplementedError("TODO: appel API ElevenLabs voice cloning")
