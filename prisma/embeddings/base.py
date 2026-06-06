"""Interfaz común de los generadores de embeddings."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Embedder(ABC):
    """Convierte texto en un vector. Subclasear para local/online."""

    #: Nombre con el que se registra y se selecciona desde la CLI.
    name: str = "base"
    #: Etiqueta del modelo concreto (se guarda junto al vector para no mezclar).
    model: str = "base"

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Devuelve el vector de ``text``."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    @property
    def key(self) -> str:
        """Identificador estable del espacio vectorial: ``name:model``."""
        return f"{self.name}:{self.model}"


EMBEDDERS: dict[str, type[Embedder]] = {}


def register(cls: type[Embedder]) -> type[Embedder]:
    EMBEDDERS[cls.name] = cls
    return cls


def get_embedder(name: str, **kwargs) -> Embedder:
    if name not in EMBEDDERS:
        raise KeyError(
            f"Embedder desconocido: {name!r}. Disponibles: {sorted(EMBEDDERS)}"
        )
    return EMBEDDERS[name](**kwargs)
