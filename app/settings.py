from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import keyring

APP_NAME = "VirtualChalk"
KEYRING_SERVICE = "virtual-chalk"


def config_dir() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file() -> Path:
    return config_dir() / "config.json"


@dataclass
class Settings:
    llm_provider: str = "openrouter"
    llm_model: str = ""
    default_tts_profile: str = "sapi_local"
    default_theme: str = "chalk_board"
    default_output_dir: str = str(Path.home() / "Documents" / "Virtual-Chalk Videos")
    export_h5p_by_default: bool = True

    @classmethod
    def load(cls) -> "Settings":
        path = config_file()
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self) -> None:
        config_file().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def get_api_key(provider: str) -> str | None:
    return keyring.get_password(KEYRING_SERVICE, provider)


def set_api_key(provider: str, api_key: str) -> None:
    keyring.set_password(KEYRING_SERVICE, provider, api_key)
