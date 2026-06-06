"""Analizador local compuesto.

Combina todos los motores locales y gratuitos en un único analizador:

- **visión** → :class:`~prisma.analysis.ollama.OllamaAnalyzer` (describe imágenes),
- **OCR** → :class:`~prisma.analysis.ocr.OcrAnalyzer` (texto en imágenes),
- **transcripción** → :class:`~prisma.analysis.whisper.WhisperAnalyzer` (audio/vídeo),
- **atributos** → :class:`~prisma.analysis.attrs.AttributesAnalyzer`
  (personas/animales con YOLO + caras conocidas → ``is_only_me``).

Cada pieza degrada por su cuenta si su herramienta no está instalada, así que
``--analyzer local`` siempre funciona: rellena lo que puede y omite el resto.
"""

from __future__ import annotations

from typing import Any, Optional

from prisma.analysis.attrs import AttributesAnalyzer
from prisma.analysis.base import Analyzer, register
from prisma.analysis.ocr import OcrAnalyzer
from prisma.analysis.ollama import OllamaAnalyzer
from prisma.analysis.whisper import WhisperAnalyzer


@register
class LocalAnalyzer(Analyzer):
    name = "local"

    def __init__(self, vision: Optional[Analyzer] = None,
                 ocr: Optional[Analyzer] = None,
                 transcriber: Optional[Analyzer] = None,
                 attrs: Optional[Analyzer] = None) -> None:
        self._vision = vision or OllamaAnalyzer()
        self._ocr = ocr or OcrAnalyzer()
        self._transcriber = transcriber or WhisperAnalyzer()
        self._attrs = attrs or AttributesAnalyzer()

    def configure(self, cfg: Any) -> None:
        self._attrs.configure(cfg)

    def caption(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        return self._vision.caption(data=data, mime=mime, type=type)

    def ocr(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        return self._ocr.ocr(data=data, mime=mime, type=type)

    def transcribe(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        return self._transcriber.transcribe(data=data, mime=mime, type=type)

    def detect(self, *, data: bytes, mime: str, type: str) -> dict[str, Any]:
        return self._attrs.detect(data=data, mime=mime, type=type)

    def identify(self, *, data: bytes, mime: str, type: str) -> Optional[list[str]]:
        return self._attrs.identify(data=data, mime=mime, type=type)
