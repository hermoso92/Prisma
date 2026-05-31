"""Interfaz común de los importadores.

Un importador es la pieza que sabe leer *una* fuente concreta y traducir sus
datos crudos al esquema común. Mantener una interfaz mínima y uniforme permite
que el orquestador de ingesta trate todas las fuentes igual.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, Optional

from prisma.schema import Event
from prisma.storage import ObjectStore


class Importer(ABC):
    """Clase base de todos los importadores.

    Args:
        source_path: Ruta al export/archivo de la fuente (un ZIP, un ``.txt``,
            una carpeta de fotos...). Algunos importadores futuros (API) podrán
            ignorarla.
        objects: Object store donde depositar binarios y obtener sus referencias.
            Los importadores de texto puro pueden no usarlo.
    """

    #: Nombre de la fuente; se escribe en ``Event.source``. Lo define cada subclase.
    source: str = "unknown"

    def __init__(
        self,
        source_path: Optional[Path | str] = None,
        objects: Optional[ObjectStore] = None,
    ) -> None:
        self.source_path = Path(source_path) if source_path is not None else None
        self.objects = objects

    @abstractmethod
    def iter_events(self) -> Iterator[Event]:
        """Genera los eventos normalizados de la fuente.

        Debe ser perezoso (yield) para soportar exports grandes sin cargarlos
        enteros en memoria, e idempotente: misma entrada → mismos ``Event.id``.
        """
        raise NotImplementedError
