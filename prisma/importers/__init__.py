"""Importadores de Prisma: uno por fuente.

Cada importador lee un export/API y emite :class:`~prisma.schema.Event` ya
normalizados. La interfaz común vive en :mod:`prisma.importers.base`.

Fase 0 incluye :class:`~prisma.importers.jsonl.JsonlImporter`, un importador
genérico para validar el pipeline. Los importadores reales (ChatGPT, Claude,
WhatsApp, fotos...) llegan en las fases siguientes del roadmap.
"""

from prisma.importers.base import Importer
from prisma.importers.jsonl import JsonlImporter
from prisma.importers.chatgpt import ChatGptImporter
from prisma.importers.claude import ClaudeImporter
from prisma.importers.photos import PhotosImporter
from prisma.importers.whatsapp import WhatsAppImporter
from prisma.importers.notes import NotesImporter
from prisma.importers.keep import KeepImporter
from prisma.importers.google_photos import GooglePhotosImporter

#: Registro de importadores disponibles por nombre (usado por la CLI).
REGISTRY: dict[str, type[Importer]] = {
    "jsonl": JsonlImporter,
    "chatgpt": ChatGptImporter,
    "claude": ClaudeImporter,
    "photos": PhotosImporter,
    "whatsapp": WhatsAppImporter,
    "notes": NotesImporter,
    "keep": KeepImporter,
    "gphotos": GooglePhotosImporter,
}

__all__ = [
    "Importer", "JsonlImporter", "ChatGptImporter", "ClaudeImporter",
    "PhotosImporter", "WhatsAppImporter", "NotesImporter", "KeepImporter",
    "GooglePhotosImporter", "REGISTRY",
]
