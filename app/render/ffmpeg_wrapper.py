from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

FFMPEG_BIN = Path(__file__).resolve().parent.parent.parent / "resources" / "ffmpeg" / "ffmpeg.exe"

# Nombre de dernières lignes de stderr conservées dans le message d'erreur —
# la sortie ffmpeg est très verbeuse (une ligne de progression par frame)
# mais l'erreur réelle (filtre, codec, mémoire...) est quasi toujours dans
# les toutes dernières lignes.
_STDERR_TAIL_LINES = 15


class FFmpegError(RuntimeError):
    """Echec ffmpeg rapportant le VRAI message d'erreur (stderr), pas
    seulement le code de sortie brut d'un CalledProcessError — rencontré en
    pratique : un encodage a échoué avec le code 3752568763 (0xDFABA7BB,
    valeur système sans rapport avec ffmpeg lui-même), et sans stderr
    capturé l'UI n'affichait que ce nombre opaque, impossible à
    diagnostiquer sans relancer la commande à la main pour découvrir la
    cause réelle (ici : "Cannot allocate memory" dans le filtre `scale`,
    mémoire système épuisée en cours d'encodage)."""


def _ffmpeg() -> str:
    return str(FFMPEG_BIN) if FFMPEG_BIN.exists() else "ffmpeg"


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-_STDERR_TAIL_LINES:])
        raise FFmpegError(f"ffmpeg a échoué (code {result.returncode}) :\n{tail}")


def encode_scene(frames_dir: Path, audio_path: Path, fps: int, out_path: Path,
                  chalk_audio_path: Path | None = None) -> Path:
    cmd = [
        _ffmpeg(), "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%05d.jpg"),
        "-i", str(audio_path),
    ]

    if chalk_audio_path is not None:
        # Piste craie mixée sous la voix off (volume réduit) ; aresample
        # explicite car les deux pistes n'ont pas forcément le même taux
        # d'échantillonnage (voix TTS vs piste craie synthétisée à 22050 Hz).
        cmd += ["-i", str(chalk_audio_path)]
        filter_complex = (
            "[1:a]aresample=44100[voice];"
            "[2:a]volume=0.3,aresample=44100[chalk];"
            "[voice][chalk]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
        cmd += ["-filter_complex", filter_complex, "-map", "0:v", "-map", "[aout]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]

    # Les frames JPEG sont en plage complète (0-255, "pc"/"full") — sans
    # conversion explicite, le fichier de sortie reste tagué full-range
    # (yuvj420p) alors que la quasi-totalité des lecteurs vidéo attendent
    # la plage limitée standard (16-235, "tv") pour du H.264 : le résultat
    # apparaît délavé/plat dans un lecteur normal, même si une extraction
    # de frame via ffmpeg (qui respecte le tag) semble correcte. `scale`
    # remappe réellement les valeurs de pixels, pas juste l'étiquette.
    cmd += ["-vf", "scale=in_range=full:out_range=tv"]

    # crf 18 plutôt que le défaut (23) : le texte à la craie est un détail
    # fin et peu contrasté, une compression plus agressive le rend illisible.
    cmd += [
        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-color_range", "tv",
        "-c:a", "aac", "-shortest", str(out_path),
    ]
    _run(cmd)
    return out_path


def concat_scenes(scene_paths: list[Path], out_path: Path) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as list_file:
        for p in scene_paths:
            list_file.write(f"file '{p.as_posix()}'\n")
        concat_list = list_file.name

    _run([_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", str(out_path)])
    return out_path
