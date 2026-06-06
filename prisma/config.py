"""Configuración y rutas de Prisma.

Define dónde vive todo: la carpeta buzón (``inbox``) donde el usuario suelta los
exports, y el directorio de datos (``data``) con la base de metadatos y el object
store. La raíz se puede fijar con la variable de entorno ``PRISMA_HOME``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOME = Path(os.environ.get("PRISMA_HOME", "./prisma_data")).resolve()


@dataclass(frozen=True)
class Config:
    """Rutas derivadas de una raíz."""

    home: Path = DEFAULT_HOME

    @property
    def inbox(self) -> Path:
        """Carpeta buzón: el usuario deja aquí los exports a ingerir."""
        return self.home / "inbox"

    @property
    def data(self) -> Path:
        return self.home / "data"

    @property
    def db_path(self) -> Path:
        return self.data / "prisma.db"

    @property
    def objects_dir(self) -> Path:
        return self.data / "objects"

    @property
    def faces_dir(self) -> Path:
        """Donde se guarda la cara enrolada para el reconocimiento facial."""
        return self.data / "faces"

    @property
    def render_dir(self) -> Path:
        """Salida de collages y vídeos generados."""
        return self.home / "render"

    def ensure_dirs(self) -> None:
        for d in (self.home, self.inbox, self.data, self.objects_dir):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, home: str | os.PathLike | None = None) -> "Config":
        return cls(home=Path(home).resolve() if home else DEFAULT_HOME)
