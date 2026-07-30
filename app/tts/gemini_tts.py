from __future__ import annotations

import base64
import tempfile
import wave
from pathlib import Path

import requests

from app.tts.base import TTSProvider, VoiceProfile

GEMINI_TTS_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Modele TTS le mieux documente/etabli au moment de l'integration (un
# "gemini-3.1-flash-tts-preview" plus recent existe mais son comportement
# reel de quota/tarification n'a pas ete verifie avant de faire depenser
# du credit reel a l'utilisateur — a reevaluer plus tard si besoin).
DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"

# Choisie comme voix par defaut : feminine, chaleureuse ("Warm"), adaptee
# a un ton d'enseignant bienveillant plutot qu'un ton froid/factuel.
DEFAULT_VOICE = "Sulafat"

# Sortie audio Gemini TTS : PCM brut 24kHz mono 16 bits, sans conteneur —
# il faut reconstruire un WAV nous-memes pour que wave.open() (duree
# reelle, voir Pipeline.synthesize_voices) et ffmpeg puissent le lire.
SAMPLE_RATE = 24000
SAMPLE_WIDTH = 2
CHANNELS = 1


class GeminiTTSProvider(TTSProvider):
    """Voix Gemini (cloud, payant) : meme cle API que la generation de
    script (app/llm/gemini.py), un seul fournisseur/une seule cle a gerer.
    La langue est detectee automatiquement depuis le texte envoye (pas de
    parametre de langue dans l'API) ; le nom de la voix vient de
    VoiceProfile.voice_id (ex: "Sulafat"), voir la liste complete des voix
    dans docs/architecture.md."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model

    def synthesize(self, text: str, profile: VoiceProfile) -> tuple[Path, float]:
        voice_name = (profile.voice_id if profile else "") or DEFAULT_VOICE
        response = requests.post(
            GEMINI_TTS_URL_TEMPLATE.format(model=self.model),
            params={"key": self.api_key},
            json={
                "contents": [{"parts": [{"text": text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}
                    },
                },
            },
            timeout=120,
        )
        response.raise_for_status()
        b64_audio = response.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        pcm_bytes = base64.b64decode(b64_audio)

        out_path = Path(tempfile.mktemp(suffix=".wav"))
        with wave.open(str(out_path), "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm_bytes)

        duration = len(pcm_bytes) / (SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS)
        return out_path, duration
