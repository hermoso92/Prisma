"""Analizador nulo (por defecto).

No analiza el contenido: devuelve un resultado vacío. Permite ingerir fotos y
vídeos —con sus metadatos EXIF/sidecar (fecha, GPS) ya extraídos por el
importador— sin requerir modelos ni dependencias, y deja el hueco listo para
enchufar un backend local u online en fases posteriores.
"""

from __future__ import annotations

from prisma.analysis.base import Analyzer, register


@register
class NullAnalyzer(Analyzer):
    name = "null"
