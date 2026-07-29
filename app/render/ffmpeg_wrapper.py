from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

FFMPEG_BIN = Path(__file__).resolve().parent.parent.parent / "resources" / "ffmpeg" / "ffmpeg.exe"


def _ffmpeg() -> str:
    return str(FFMPEG_BIN) if FFMPEG_BIN.exists() else "ffmpeg"


def encode_scene(frames_dir: Path, audio_path: Path, fps: int, out_path: Path) -> Path:
    subprocess.run(
        [
            _ffmpeg(), "-y",
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%05d.png"),
            "-i", str(audio_path),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(out_path),
        ],
        check=True,
    )
    return out_path


def concat_scenes(scene_paths: list[Path], out_path: Path) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as list_file:
        for p in scene_paths:
            list_file.write(f"file '{p.as_posix()}'\n")
        concat_list = list_file.name

    subprocess.run(
        [_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", str(out_path)],
        check=True,
    )
    return out_path
