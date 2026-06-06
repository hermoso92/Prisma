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

#: Etiqueta de identidad del usuario en el reconocimiento facial.
ME_LABEL = "me"


class Analyzer(ABC):
    """Backend de análisis de medios. Subclasear para local/online."""

    #: Nombre con el que se registra y se selecciona desde la CLI.
    name: str = "base"

    def configure(self, cfg: Any) -> None:
        """Gancho opcional: recibe la Config (rutas) tras crearse el analizador.

        Lo usan los analizadores que necesitan saber dónde viven los datos (p. ej.
        el reconocimiento facial, que lee la cara enrolada de ``cfg.faces_dir``).
        Por defecto no hace nada.
        """

    def analyze(self, *, data: bytes, mime: str, type: str) -> dict[str, Any]:
        """Analiza un medio y devuelve campos derivados (sin claves vacías).

        Orquesta, según el tipo: ``caption``/``ocr`` y los atributos estructurados
        (``detect`` → personas/animales, ``identify`` → caras conocidas) para
        imágenes/vídeo, y ``transcribe`` para audio/vídeo. Además deriva la bandera
        ``is_only_me`` cuando hay datos suficientes.
        """
        derived: dict[str, Any] = {}
        if type in ("photo", "video"):
            cap = self.caption(data=data, mime=mime, type=type)
            if cap:
                derived["caption"] = cap
            ocr = self.ocr(data=data, mime=mime, type=type)
            if ocr:
                derived["ocr"] = ocr
            attrs = self.detect(data=data, mime=mime, type=type)
            if attrs:
                derived.update(attrs)
            faces = self.identify(data=data, mime=mime, type=type)
            if faces is not None:
                derived["faces"] = faces
            self._derive_only_me(derived)
        if type in ("audio", "video"):
            tr = self.transcribe(data=data, mime=mime, type=type)
            if tr:
                derived["transcript"] = tr
        if derived:
            derived["analyzer"] = self.name
        return derived

    @staticmethod
    def _derive_only_me(derived: dict[str, Any]) -> None:
        """`is_only_me` = exactamente 1 persona, que soy yo, y ningún animal.

        Solo se calcula si hay recuento de personas Y reconocimiento de caras
        (si no, no podemos afirmarlo, así que somos conservadores y no la ponemos).
        """
        if "people_count" in derived and "faces" in derived:
            derived["is_only_me"] = bool(
                derived["people_count"] == 1
                and derived["faces"] == [ME_LABEL]
                and not derived.get("animals")
            )

    def caption(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        """Descripción textual de una imagen/fotograma. ``None`` si no aplica."""
        return None

    def ocr(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        """Texto reconocido dentro de la imagen. ``None`` si no aplica."""
        return None

    def transcribe(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        """Transcripción de audio/vídeo. ``None`` si no aplica."""
        return None

    def detect(self, *, data: bytes, mime: str, type: str) -> dict[str, Any]:
        """Atributos estructurados: ``{people_count, animals, objects}``. ``{}`` si no aplica."""
        return {}

    def identify(self, *, data: bytes, mime: str, type: str) -> Optional[list[str]]:
        """Caras conocidas reconocidas (p. ej. ``["me"]``). ``None`` si no se hizo."""
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
