"""Transcripción de audio/vídeo con Whisper local.

Convierte audios y vídeos (p. ej. las notas de voz de WhatsApp) en texto
buscable, 100% en local y gratis. Usa el binario ``whisper`` (openai-whisper) si
está instalado; configurable por entorno:

- ``PRISMA_WHISPER_CMD``    — comando (por defecto ``whisper``).
- ``PRISMA_WHISPER_MODEL``  — modelo (por defecto ``base``).
- ``PRISMA_WHISPER_LANG``   — idioma (por defecto ``Spanish``).

Degrada con elegancia: si Whisper no está disponible, ``transcribe`` devuelve
``None`` (el medio se ingiere igual, solo sin transcripción) y avisa una vez.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from prisma.analysis.base import Analyzer, register

_EXT = {
    "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav",
    "audio/ogg": ".ogg", "audio/opus": ".opus",
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/x-m4v": ".m4v",
    "video/x-msvideo": ".avi", "video/x-matroska": ".mkv",
}


@register
class WhisperAnalyzer(Analyzer):
    name = "whisper"

    def __init__(self, cmd: Optional[str] = None, model: Optional[str] = None,
                 lang: Optional[str] = None) -> None:
        self.cmd = cmd or os.environ.get("PRISMA_WHISPER_CMD", "whisper")
        self.model = model or os.environ.get("PRISMA_WHISPER_MODEL", "base")
        self.lang = lang or os.environ.get("PRISMA_WHISPER_LANG", "Spanish")
        self._warned = False

    def available(self) -> bool:
        return shutil.which(self.cmd) is not None

    def transcribe(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        if type not in ("audio", "video"):
            return None
        if not self.available():
            self._warn_once()
            return None
        suffix = _EXT.get(mime, ".bin")
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / f"clip{suffix}"
            media.write_bytes(data)
            return self._transcribe_file(media, Path(tmp))

    def _transcribe_file(self, media: Path, outdir: Path) -> Optional[str]:
        """Ejecuta Whisper y devuelve el texto. Aislado para poder testearlo."""
        try:
            subprocess.run(
                [self.cmd, str(media), "--model", self.model,
                 "--language", self.lang, "--output_format", "txt",
                 "--output_dir", str(outdir), "--fp16", "False"],
                capture_output=True, text=True, check=True,
            )
        except (OSError, subprocess.SubprocessError):
            self._warn_once()
            return None
        txt = media.with_suffix(".txt")
        if not txt.exists():
            return None
        return txt.read_text(encoding="utf-8", errors="replace").strip() or None

    def _warn_once(self) -> None:
        if not self._warned:
            print(
                f"⚠️  Whisper ('{self.cmd}') no disponible; ingiero sin "
                "transcripción. Instálalo: brew install ffmpeg && pipx install openai-whisper",
                file=sys.stderr,
            )
            self._warned = True
