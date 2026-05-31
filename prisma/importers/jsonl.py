"""Importador genérico JSONL.

Lee un archivo ``.jsonl`` (un objeto JSON por línea) donde cada línea describe un
evento ya en (o casi en) el esquema común. Sirve para dos cosas:

1. Validar el pipeline de ingesta de punta a punta sin depender de exports reales.
2. Reingerir datos previamente normalizados por Prisma (export → reimport).

Cada línea debe incluir al menos ``type`` y ``timestamp``. Si no trae ``id``, se
genera de forma determinista a partir de ``source`` + ``source_native_id`` (o, en
su defecto, del número de línea), de modo que reimportar el mismo archivo no
duplica.
"""

from __future__ import annotations

import json
from typing import Iterator

from prisma.importers.base import Importer
from prisma.schema import Event, make_event_id


class JsonlImporter(Importer):
    source = "jsonl"

    def iter_events(self) -> Iterator[Event]:
        if self.source_path is None:
            raise ValueError("JsonlImporter requiere source_path")
        with open(self.source_path, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                data = json.loads(line)
                yield self._to_event(data, lineno)

    def _to_event(self, data: dict, lineno: int) -> Event:
        source = data.get("source", self.source)
        if "id" in data:
            event_id = data["id"]
        else:
            native = data.get("source_native_id", f"line:{lineno}")
            event_id = make_event_id(source, native)
        payload = {k: v for k, v in data.items() if k != "source_native_id"}
        payload["id"] = event_id
        payload["source"] = source
        return Event.from_dict(payload)
