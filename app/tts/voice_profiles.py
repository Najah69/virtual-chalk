from __future__ import annotations

import json

from app.settings import config_dir
from app.tts.base import VoiceProfile

PROFILES_FILE = "voice_profiles.json"


def _profiles_path():
    return config_dir() / PROFILES_FILE


def list_voice_profiles() -> list[VoiceProfile]:
    """Le premier profil de la liste est celui sélectionné par défaut dans
    l'assistant (ui/js/app.js prend la première <option>) — la voix Gemini
    passe donc en tête maintenant qu'une clé API pérenne est configurée,
    la voix Windows locale restant disponible en repli gratuit/hors-ligne."""
    path = _profiles_path()
    if not path.exists():
        return [
            VoiceProfile(name="Voix Gemini (Sulafat, chaleureuse)", provider="gemini_tts", voice_id="Sulafat"),
            VoiceProfile(name="Voix Windows par défaut", provider="sapi_local"),
        ]
    data = json.loads(path.read_text(encoding="utf-8"))
    return [VoiceProfile(**item) for item in data]


def save_voice_profile(profile: VoiceProfile) -> None:
    profiles = [p for p in list_voice_profiles() if p.name != profile.name]
    profiles.append(profile)
    _profiles_path().write_text(
        json.dumps([p.__dict__ for p in profiles], indent=2), encoding="utf-8"
    )


def delete_voice_profile(name: str) -> None:
    profiles = [p for p in list_voice_profiles() if p.name != name]
    _profiles_path().write_text(
        json.dumps([p.__dict__ for p in profiles], indent=2), encoding="utf-8"
    )
