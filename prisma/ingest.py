"""Orquestador de ingesta.

Conecta un importador con el almacenamiento. Es el punto donde, en fases
posteriores, se enganchará el análisis multimodal (visión, OCR, transcripción) y
el cálculo de embeddings, entre la normalización y la persistencia.

De momento (Fase 0): importador → dedupe → persistencia, de forma idempotente.
"""

from __future__ import annotations

from dataclasses import dataclass

from prisma.importers.base import Importer
from prisma.storage import MetadataStore


@dataclass
class IngestResult:
    source: str
    new: int
    skipped: int

    @property
    def total(self) -> int:
        return self.new + self.skipped

    def __str__(self) -> str:
        return (
            f"[{self.source}] {self.new} nuevos, {self.skipped} ya existentes "
            f"({self.total} procesados)"
        )


class Pipeline:
    """Ejecuta importadores contra el almacén de metadatos."""

    def __init__(self, store: MetadataStore) -> None:
        self.store = store

    def ingest(self, importer: Importer) -> IngestResult:
        """Ingiere todos los eventos de un importador.

        El dedupe lo hace el almacén por ``Event.id``, así que volver a ejecutar
        sobre el mismo export es seguro y barato (todo saldrá como "ya existente").
        """
        # Punto de extensión futuro: enriquecer cada evento con análisis
        # multimodal y embeddings antes de persistirlo.
        new, skipped = self.store.add_events(importer.iter_events())
        self.store.set_cursor(importer.source, cursor=None)
        return IngestResult(source=importer.source, new=new, skipped=skipped)
