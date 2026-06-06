"""OCR de imágenes con Tesseract local.

Extrae el texto que aparece dentro de una imagen (capturas de pantalla, fotos de
documentos…), 100% en local y gratis, usando el binario ``tesseract``.
Configurable por entorno:

- ``PRISMA_TESSERACT_CMD``   — comando (por defecto ``tesseract``).
- ``PRISMA_TESSERACT_LANG``  — idiomas (por defecto ``spa+eng``).

Degrada con elegancia: si Tesseract no está, ``ocr`` devuelve ``None`` y avisa
una vez. Solo se aplica a fotos (no a vídeos).
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
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/tiff": ".tif", "image/heic": ".heic",
}
# Por debajo de este nº de caracteres consideramos que no hay texto útil.
_MIN_CHARS = 3


@register
class OcrAnalyzer(Analyzer):
    name = "ocr"

    def __init__(self, cmd: Optional[str] = None, lang: Optional[str] = None) -> None:
        self.cmd = cmd or os.environ.get("PRISMA_TESSERACT_CMD", "tesseract")
        self.lang = lang or os.environ.get("PRISMA_TESSERACT_LANG", "spa+eng")
        self._warned = False

    def available(self) -> bool:
        return shutil.which(self.cmd) is not None

    def ocr(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        if type != "photo":
            return None
        if not self.available():
            self._warn_once()
            return None
        suffix = _EXT.get(mime, ".png")
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / f"img{suffix}"
            img.write_bytes(data)
            return self._ocr_file(img)

    def _ocr_file(self, img: Path) -> Optional[str]:
        """Ejecuta Tesseract y devuelve el texto. Aislado para poder testearlo."""
        try:
            proc = subprocess.run(
                [self.cmd, str(img), "stdout", "-l", self.lang],
                capture_output=True, text=True, check=True,
            )
        except (OSError, subprocess.SubprocessError):
            self._warn_once()
            return None
        text = proc.stdout.strip()
        return text if len(text) >= _MIN_CHARS else None

    def _warn_once(self) -> None:
        if not self._warned:
            print(
                f"⚠️  Tesseract ('{self.cmd}') no disponible; ingiero sin OCR. "
                "Instálalo: brew install tesseract tesseract-lang",
                file=sys.stderr,
            )
            self._warned = True
