"""Análisis de contenido (multimodal) — capa enchufable.

El análisis pesado (describir una foto, OCR de una captura, transcribir un audio)
se aísla detrás de la interfaz :class:`Analyzer`, de modo que se pueda elegir el
backend sin tocar el pipeline:

- **null** (por defecto: no analiza; útil para ingerir rápido o sin dependencias),
- **ollama** (describe imágenes con un modelo de visión local),
- **ocr** (Tesseract: texto dentro de imágenes),
- **whisper** (transcribe audio/vídeo),
- **detect** (YOLO: cuenta personas y detecta animales),
- **attrs** (detección + reconocimiento facial → ``is_only_me``),
- **local** (compuesto: visión + OCR + transcripción + atributos, todo local).

Decisión de diseño clave (ver ``docs/ARCHITECTURE.md`` §10 y §12): todo el
análisis corre **en local**; nada de tus datos sale del dispositivo.
"""

from prisma.analysis.base import Analyzer, get_analyzer, ANALYZERS, ME_LABEL
from prisma.analysis.null import NullAnalyzer
from prisma.analysis.ollama import OllamaAnalyzer
from prisma.analysis.ocr import OcrAnalyzer
from prisma.analysis.whisper import WhisperAnalyzer
from prisma.analysis.detect import DetectAnalyzer
from prisma.analysis.attrs import AttributesAnalyzer
from prisma.analysis.local import LocalAnalyzer

__all__ = [
    "Analyzer", "NullAnalyzer", "OllamaAnalyzer", "OcrAnalyzer",
    "WhisperAnalyzer", "DetectAnalyzer", "AttributesAnalyzer", "LocalAnalyzer",
    "get_analyzer", "ANALYZERS", "ME_LABEL",
]
