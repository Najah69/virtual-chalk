from __future__ import annotations

import array
import math
import random
import tempfile
import wave
import zlib
from pathlib import Path

from app.scenes.schema import Scene

# Placeholder synthétisé (bruit filtré + enveloppe) : aucun enregistrement
# réel de craie n'était disponible localement. Remplacer les fichiers de
# resources/chalk_sounds/ par de vrais enregistrements ne demande aucun
# changement de code, ensure_sound_pack() ne (re)génère que ce qui manque.
SOUND_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "chalk_sounds"
SAMPLE_RATE = 22050
TAP_INTERVAL_RANGE = (0.35, 0.65)  # variété du rythme des tapotements
HEADROOM_GAIN = 0.8  # marge anti-saturation quand plusieurs tapotements se chevauchent


def _synthesize_tap(path: Path, seed: int) -> None:
    rng = random.Random(seed)
    duration = rng.uniform(0.06, 0.16)
    decay = duration * 0.28
    alpha = rng.uniform(0.15, 0.4)  # coefficient du filtre passe-bas (bruit "gratté", pas blanc pur)
    n_samples = int(SAMPLE_RATE * duration)

    state = 0.0
    samples = array.array("h")
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        envelope = math.exp(-t / decay)
        noise = rng.uniform(-1.0, 1.0)
        state += alpha * (noise - state)
        value = max(-1.0, min(1.0, state * envelope * 0.5))
        samples.append(int(value * 32767))

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(samples.tobytes())


def ensure_sound_pack(count: int = 6) -> list[Path]:
    SOUND_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(SOUND_DIR.glob("chalk_tap_*.wav"))
    if len(existing) >= count:
        return existing
    for i in range(count):
        path = SOUND_DIR / f"chalk_tap_{i:02d}.wav"
        if not path.exists():
            _synthesize_tap(path, seed=i * 97 + 13)
    return sorted(SOUND_DIR.glob("chalk_tap_*.wav"))


def _read_wav_samples(path: Path) -> array.array:
    with wave.open(str(path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    samples = array.array("h")
    samples.frombytes(raw)
    return samples


def build_chalk_track(scene: Scene) -> Path:
    """Piste audio dédiée aux tapotements de craie, un ou plusieurs par
    tracé (selon sa durée), avec un son choisi aléatoirement à chaque fois
    parmi le pool pour éviter la répétition. Mixée sous la voix off côté
    ffmpeg (volume réduit), le gain ici ne sert qu'à éviter la saturation
    quand deux tapotements se chevauchent."""
    sound_pool = ensure_sound_pack()
    rng = random.Random(zlib.crc32(scene.scene_id.encode("utf-8")))

    total_samples = max(1, int(scene.duration_sec * SAMPLE_RATE))
    buffer = array.array("h")
    buffer.frombytes(bytes(total_samples * 2))

    for stroke in scene.strokes:
        t = stroke.start_sec
        while t < stroke.end_sec:
            tap = _read_wav_samples(rng.choice(sound_pool))
            offset = int(t * SAMPLE_RATE)
            for i, s in enumerate(tap):
                idx = offset + i
                if idx >= total_samples:
                    break
                mixed = buffer[idx] + int(s * HEADROOM_GAIN)
                buffer[idx] = max(-32768, min(32767, mixed))
            t += rng.uniform(*TAP_INTERVAL_RANGE)

    out_path = Path(tempfile.mktemp(suffix="_chalk.wav"))
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(buffer.tobytes())
    return out_path
