"""Importador de Google Keep (Google Takeout).

Takeout exporta cada nota de Keep como un ``.json`` dentro de la carpeta ``Keep/``.
Este importador recorre esa carpeta y emite un :class:`Event` por nota (saltando
las de la papelera).

Campos del JSON de Keep que usamos:

- ``title``, ``textContent`` — título y cuerpo.
- ``listContent`` — listas con casillas (``[x]`` / ``[ ]``).
- ``userEditedTimestampUsec`` / ``createdTimestampUsec`` — fecha (microsegundos).
- ``labels`` — etiquetas (a ``source_meta``).
- ``isTrashed`` / ``isArchived`` / ``isPinned`` — estado.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Optional

from prisma.importers.base import Importer
from prisma.importers.util import unix_to_iso
from prisma.schema import Event


class KeepImporter(Importer):
    source = "keep"

    def iter_events(self) -> Iterator[Event]:
        if self.source_path is None:
            raise ValueError("KeepImporter requiere source_path (carpeta de Takeout)")
        root = self.source_path
        paths = sorted(root.rglob("*.json")) if root.is_dir() else [root]
        for path in paths:
            try:
                note = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if not isinstance(note, dict) or "textContent" not in note and "listContent" not in note:
                continue  # no parece una nota de Keep
            ev = self._build_event(path, note)
            if ev is not None:
                yield ev

    def _build_event(self, path: Path, note: dict[str, Any]) -> Optional[Event]:
        if note.get("isTrashed"):
            return None
        content = self._content(note)
        title = note.get("title") or None
        if not content and not title:
            return None

        usec = note.get("userEditedTimestampUsec") or note.get("createdTimestampUsec")
        timestamp = unix_to_iso(usec / 1_000_000) if usec else None
        if timestamp is None:
            return None

        source_meta: dict[str, Any] = {"filename": path.name}
        labels = [lbl.get("name") for lbl in note.get("labels", []) if lbl.get("name")]
        if labels:
            source_meta["labels"] = labels
        for flag in ("isArchived", "isPinned"):
            if note.get(flag):
                source_meta[flag] = True

        return Event.create(
            source=self.source,
            source_native_id=path.name,
            type="note",
            timestamp=timestamp,
            title=title,
            content=content,
            source_meta=source_meta,
        )

    @staticmethod
    def _content(note: dict[str, Any]) -> str:
        text = (note.get("textContent") or "").strip()
        items = note.get("listContent") or []
        if items:
            lines = [
                f"[{'x' if it.get('isChecked') else ' '}] {it.get('text', '')}".rstrip()
                for it in items
            ]
            text = (text + "\n" + "\n".join(lines)).strip() if text else "\n".join(lines)
        return text
