"""Importador de notas de texto.

Recorre una carpeta con notas en texto plano o Markdown (``.txt`` / ``.md`` /
``.markdown``) y emite un :class:`Event` por nota. Sirve para notas de Apple
exportadas como texto, o cualquier carpeta de apuntes.

- ``title``: la primera línea no vacía (si parece un título), o el nombre del
  fichero.
- ``timestamp``: la fecha de modificación del fichero (ISO-8601 UTC).
- ``content``: el texto completo de la nota.

Idempotente: el id deriva de la ruta relativa, así que reimportar no duplica.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from prisma.importers.base import Importer
from prisma.schema import Event

_EXTS = {".txt", ".md", ".markdown", ".text"}


class NotesImporter(Importer):
    source = "notes"

    def iter_events(self) -> Iterator[Event]:
        if self.source_path is None:
            raise ValueError("NotesImporter requiere source_path (carpeta o fichero)")
        root = self.source_path
        paths = sorted(root.rglob("*")) if root.is_dir() else [root]
        for path in paths:
            if path.is_file() and path.suffix.lower() in _EXTS:
                yield self._build_event(root, path)

    def _build_event(self, root: Path, path: Path) -> Event:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        title = self._title(text, path)
        rel = path.relative_to(root) if root.is_dir() else path.name
        ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        return Event.create(
            source=self.source,
            source_native_id=str(rel),
            type="note",
            timestamp=ts,
            title=title,
            content=text,
            source_meta={"filename": path.name},
        )

    @staticmethod
    def _title(text: str, path: Path) -> str:
        for line in text.splitlines():
            line = line.lstrip("# ").strip()  # admite encabezados Markdown
            if line:
                return line[:100]
        return path.stem
