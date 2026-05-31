"""Importadores de Prisma: uno por fuente.

Cada importador lee un export/API y emite :class:`~prisma.schema.Event` ya
normalizados. La interfaz común vive en :mod:`prisma.importers.base`.

Fase 0 incluye :class:`~prisma.importers.jsonl.JsonlImporter`, un importador
genérico para validar el pipeline. Los importadores reales (ChatGPT, Claude,
WhatsApp, fotos...) llegan en las fases siguientes del roadmap.
"""

from prisma.importers.base import Importer
from prisma.importers.jsonl import JsonlImporter

#: Registro de importadores disponibles por nombre (usado por la CLI).
REGISTRY: dict[str, type[Importer]] = {
    "jsonl": JsonlImporter,
}

__all__ = ["Importer", "JsonlImporter", "REGISTRY"]
