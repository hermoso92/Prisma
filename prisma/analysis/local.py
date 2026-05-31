"""Analizador local compuesto.

Combina los tres motores locales y gratuitos en un único analizador:

- **visión** → :class:`~prisma.analysis.ollama.OllamaAnalyzer` (describe imágenes),
- **OCR** → :class:`~prisma.analysis.ocr.OcrAnalyzer` (texto en imágenes),
- **transcripción** → :class:`~prisma.analysis.whisper.WhisperAnalyzer` (audio/vídeo).

Cada pieza degrada por su cuenta si su herramienta no está instalada, así que
``--analyzer local`` siempre funciona: rellena lo que puede y omite el resto.
"""

from __future__ import annotations

from typing import Optional

from prisma.analysis.base import Analyzer, register
from prisma.analysis.ocr import OcrAnalyzer
from prisma.analysis.ollama import OllamaAnalyzer
from prisma.analysis.whisper import WhisperAnalyzer


@register
class LocalAnalyzer(Analyzer):
    name = "local"

    def __init__(self, vision: Optional[Analyzer] = None,
                 ocr: Optional[Analyzer] = None,
                 transcriber: Optional[Analyzer] = None) -> None:
        self._vision = vision or OllamaAnalyzer()
        self._ocr = ocr or OcrAnalyzer()
        self._transcriber = transcriber or WhisperAnalyzer()

    def caption(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        return self._vision.caption(data=data, mime=mime, type=type)

    def ocr(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        return self._ocr.ocr(data=data, mime=mime, type=type)

    def transcribe(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        return self._transcriber.transcribe(data=data, mime=mime, type=type)
