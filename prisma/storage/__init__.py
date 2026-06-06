"""Capa de almacenamiento de Prisma.

Tres almacenes, simples al principio y sustituibles después:

- :class:`~prisma.storage.metadata.MetadataStore` — eventos / línea temporal (SQLite).
- :class:`~prisma.storage.objects.ObjectStore` — binarios *content-addressed*.
- (Fase 4) vector store para embeddings.
"""

from prisma.storage.metadata import MetadataStore
from prisma.storage.objects import ObjectStore

__all__ = ["MetadataStore", "ObjectStore"]
