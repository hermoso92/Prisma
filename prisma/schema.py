"""Esquema común de Prisma.

El corazón del sistema: todo dato del mundo —un WhatsApp, una foto, un chat de
Claude, una nota— se normaliza al mismo tipo de :class:`Event`. Esa uniformidad
es lo que permite cruzar fuentes en una única línea temporal.

Ver ``docs/ARCHITECTURE.md`` (sección 5) para el diseño y las decisiones.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

#: Versión del esquema. Permite migraciones sin reimportar todo.
SCHEMA_VERSION = 1


def make_event_id(source: str, source_native_id: str) -> str:
    """Genera un id estable y determinista para un evento.

    Es ``sha256(source + "\\x00" + source_native_id)``. Al ser determinista,
    reimportar el mismo export **no duplica** eventos (idempotencia / dedupe):
    el mismo dato de origen siempre produce el mismo id.

    Args:
        source: Identificador de la fuente (``"chatgpt"``, ``"whatsapp"``...).
        source_native_id: Identificador del dato en su fuente original
            (id de mensaje, ruta de archivo, hash...). Debe ser estable.
    """
    h = hashlib.sha256()
    h.update(source.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(source_native_id).encode("utf-8"))
    return h.hexdigest()


def utcnow_iso() -> str:
    """Timestamp actual en ISO-8601 UTC (con sufijo ``Z``)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Event:
    """Unidad atómica de la línea temporal de Prisma.

    Todos los campos textuales relevantes acaban en :attr:`content` para que una
    sola búsqueda los cubra (el ``content`` de una foto es su *caption*; el de un
    audio, su transcripción). Los binarios no van aquí: :attr:`media` guarda
    referencias al object store.
    """

    # --- Identidad y clasificación ---
    id: str
    source: str
    type: str  # message | photo | video | audio | note | event | file
    timestamp: str  # ISO-8601 UTC del momento al que pertenece el dato

    # --- Contenido ---
    content: str = ""
    title: Optional[str] = None
    people: list[str] = field(default_factory=list)
    location: Optional[dict[str, Any]] = None  # {lat, lon, place}
    media: list[dict[str, Any]] = field(default_factory=list)  # [{ref, mime, role}]
    thread_id: Optional[str] = None

    # --- Metadatos crudos y derivados ---
    source_meta: dict[str, Any] = field(default_factory=dict)
    derived: dict[str, Any] = field(default_factory=dict)

    # --- Trazabilidad ---
    ingested_at: str = field(default_factory=utcnow_iso)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        source: str,
        source_native_id: str,
        type: str,
        timestamp: str,
        **kwargs: Any,
    ) -> "Event":
        """Construye un evento calculando su ``id`` determinista.

        Es la forma recomendada de crear eventos desde un importador: garantiza
        el dedupe sin que cada importador tenga que recordar hashear.
        """
        return cls(
            id=make_event_id(source, source_native_id),
            source=source,
            type=type,
            timestamp=timestamp,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializa a ``dict`` (JSON-friendly)."""
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Reconstruye un evento desde un ``dict``, ignorando claves extra."""
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})
