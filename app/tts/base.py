from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VoiceProfile:
    name: str
    provider: str  # "sapi_local" | "cloud_clone" | "cloud_standard"
    voice_id: str = ""
    config: dict | None = None


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, profile: VoiceProfile) -> tuple[Path, float]:
        """Retourne (chemin_audio, durée_secondes réelle)."""
