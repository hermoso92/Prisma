"""Análisis de contenido (multimodal) — capa enchufable.

El análisis pesado (describir una foto, OCR de una captura, transcribir un audio)
se aísla detrás de la interfaz :class:`Analyzer`, de modo que se pueda elegir el
backend sin tocar el pipeline:

- **null** (por defecto: no analiza; útil para ingerir rápido o sin dependencias),
- **ollama** (IA local y gratuita: describe imágenes con un modelo de visión).

Decisión de diseño clave (ver ``docs/ARCHITECTURE.md`` §10 y §12): todo el
análisis corre **en local**; nada de tus datos sale del dispositivo.
"""

from prisma.analysis.base import Analyzer, get_analyzer, ANALYZERS
from prisma.analysis.null import NullAnalyzer
from prisma.analysis.ollama import OllamaAnalyzer

__all__ = ["Analyzer", "NullAnalyzer", "OllamaAnalyzer", "get_analyzer", "ANALYZERS"]
