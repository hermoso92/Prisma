"""Análisis de contenido (multimodal) — capa enchufable.

El análisis pesado (describir una foto, OCR de una captura, transcribir un audio)
se aísla detrás de la interfaz :class:`Analyzer`, de modo que se pueda elegir el
backend sin tocar el pipeline:

- **local** (privado, sin que los datos salgan del dispositivo),
- **online** (un modelo en la nube, más potente),
- **null** (por defecto: no analiza; útil para ingerir rápido o sin dependencias).

Decisión de diseño clave (ver ``docs/ARCHITECTURE.md`` §10 y §12): por defecto
**no** se envía nada fuera. Activar un backend online es una decisión explícita.
"""

from prisma.analysis.base import Analyzer, get_analyzer, ANALYZERS
from prisma.analysis.null import NullAnalyzer

__all__ = ["Analyzer", "NullAnalyzer", "get_analyzer", "ANALYZERS"]
