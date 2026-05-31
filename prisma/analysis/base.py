"""Interfaz común de los analizadores de contenido.

Un :class:`Analyzer` recibe el binario de un medio (foto, vídeo, audio) y
devuelve campos *derivados* que se vuelven texto buscable: ``caption`` (qué se ve
en la imagen), ``ocr`` (texto dentro de la imagen) y ``transcript`` (audio→texto).

El pipeline mezcla ese resultado en :attr:`Event.derived` y, si el evento no
tenía texto, usa el ``caption`` como :attr:`Event.content` para que la búsqueda
lo encuentre.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class Analyzer(ABC):
    """Backend de análisis de medios. Subclasear para local/online."""

    #: Nombre con el que se registra y se selecciona desde la CLI.
    name: str = "base"

    def analyze(self, *, data: bytes, mime: str, type: str) -> dict[str, Any]:
        """Analiza un medio y devuelve campos derivados (sin claves vacías).

        Implementación por defecto: orquesta ``caption``/``ocr``/``transcribe``
        según el tipo. Las subclases normalmente solo sobreescriben esos tres.
        """
        derived: dict[str, Any] = {}
        if type in ("photo", "video"):
            cap = self.caption(data=data, mime=mime, type=type)
            if cap:
                derived["caption"] = cap
            ocr = self.ocr(data=data, mime=mime, type=type)
            if ocr:
                derived["ocr"] = ocr
        if type in ("audio", "video"):
            tr = self.transcribe(data=data, mime=mime, type=type)
            if tr:
                derived["transcript"] = tr
        if derived:
            derived["analyzer"] = self.name
        return derived

    def caption(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        """Descripción textual de una imagen/fotograma. ``None`` si no aplica."""
        return None

    def ocr(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        """Texto reconocido dentro de la imagen. ``None`` si no aplica."""
        return None

    def transcribe(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        """Transcripción de audio/vídeo. ``None`` si no aplica."""
        return None


#: Registro de analizadores por nombre. Backends locales/online se añaden aquí
#: en fases posteriores sin tocar el pipeline ni la CLI.
ANALYZERS: dict[str, type[Analyzer]] = {}


def register(cls: type[Analyzer]) -> type[Analyzer]:
    ANALYZERS[cls.name] = cls
    return cls


def get_analyzer(name: str) -> Analyzer:
    if name not in ANALYZERS:
        raise KeyError(
            f"Analizador desconocido: {name!r}. Disponibles: {sorted(ANALYZERS)}"
        )
    return ANALYZERS[name]()
