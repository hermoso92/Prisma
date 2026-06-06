"""Vídeo/slideshow a partir de varias imágenes (ffmpeg)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from prisma.render.base import RenderError

_run = subprocess.run


def make_video(images: list[bytes], out_path: Path | str,
               seconds_per_image: float = 2.0, size: str = "1280x720") -> Path:
    """Crea un slideshow MP4 con las ``images`` (cada una ``seconds_per_image``).

    Requiere el binario ``ffmpeg``. Lanza :class:`RenderError` si falta o no hay
    imágenes. Las imágenes se escalan/encuadran a ``size`` para que el códec las
    acepte aunque tengan tamaños distintos.
    """
    if not images:
        raise RenderError("No hay imágenes para el vídeo.")
    if shutil.which("ffmpeg") is None:
        raise RenderError(
            "ffmpeg no está instalado; no puedo hacer el vídeo. "
            "Instálalo: brew install ffmpeg"
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = size.split("x")
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for i, raw in enumerate(images):
            (tmpdir / f"frame_{i:04d}.jpg").write_bytes(raw)
        cmd = [
            "ffmpeg", "-y", "-framerate", f"{1 / seconds_per_image:.6f}",
            "-i", str(tmpdir / "frame_%04d.jpg"),
            "-vf", vf, "-c:v", "libx264", "-r", "30", str(out),
        ]
        proc = _run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RenderError(f"ffmpeg falló: {proc.stderr.strip()[-300:]}")
    return out
