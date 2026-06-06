"""Orquestador de ingesta.

Conecta un importador con el almacenamiento y, entre medias, el **análisis
multimodal**: para cada evento con medios (foto/vídeo/audio) ejecuta el
:class:`~prisma.analysis.base.Analyzer` configurado y mezcla el resultado
(caption, OCR, transcripción) en ``Event.derived``; si el evento no tenía texto,
usa el caption como ``Event.content`` para que la búsqueda lo encuentre.

Flujo: importador → (análisis) → dedupe → persistencia, de forma idempotente.
El cálculo de embeddings se engancha aquí en la Fase 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from prisma.analysis.base import Analyzer
from prisma.importers.base import Importer
from prisma.schema import Event
from prisma.storage import MetadataStore, ObjectStore


@dataclass
class IngestResult:
    source: str
    new: int
    skipped: int
    analyzed: int = 0

    @property
    def total(self) -> int:
        return self.new + self.skipped

    def __str__(self) -> str:
        extra = f", {self.analyzed} analizados" if self.analyzed else ""
        return (
            f"[{self.source}] {self.new} nuevos, {self.skipped} ya existentes"
            f"{extra} ({self.total} procesados)"
        )


class Pipeline:
    """Ejecuta importadores contra el almacén, con análisis opcional de medios."""

    def __init__(
        self,
        store: MetadataStore,
        objects: Optional[ObjectStore] = None,
        analyzer: Optional[Analyzer] = None,
    ) -> None:
        self.store = store
        self.objects = objects
        self.analyzer = analyzer

    def ingest(self, importer: Importer) -> IngestResult:
        """Ingiere todos los eventos de un importador.

        El dedupe lo hace el almacén por ``Event.id``, así que volver a ejecutar
        sobre el mismo export es seguro y barato (todo saldrá como "ya existente").
        """
        new = skipped = analyzed = 0
        for event in importer.iter_events():
            if self._enrich(event):
                analyzed += 1
            if self.store.add_event(event):
                new += 1
            else:
                skipped += 1
        self.store.set_cursor(importer.source, cursor=None)
        return IngestResult(
            source=importer.source, new=new, skipped=skipped, analyzed=analyzed
        )

    def _enrich(self, event: Event) -> bool:
        """Analiza los medios del evento. Devuelve ``True`` si produjo algo."""
        if self.analyzer is None or self.objects is None or not event.media:
            return False
        primary = event.media[0]
        try:
            data = self.objects.get(primary["ref"])
        except (KeyError, OSError):
            return False
        derived = self.analyzer.analyze(
            data=data, mime=primary.get("mime", ""), type=event.type
        )
        if not derived:
            return False
        event.derived.update(derived)
        # Hacer buscable: si no había texto, el caption (o el OCR) pasa a content.
        if not event.content:
            event.content = derived.get("caption") or derived.get("ocr") or ""
        return True
