"""Object store *content-addressed*.

Guarda binarios (fotos, vídeos, audios, adjuntos) bajo su hash SHA-256. Que el
nombre sea el contenido implica **deduplicación automática**: la misma foto
enviada por WhatsApp y guardada en Photos se almacena una sola vez.

Fase 0: una carpeta local. Sustituible por S3/MinIO sin cambiar la interfaz.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Prefijo de las referencias que se guardan en ``Event.media[*].ref``.
REF_PREFIX = "blob://sha256:"


class ObjectStore:
    """Almacén de binarios direccionado por contenido."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, digest: str) -> Path:
        # Reparte en subcarpetas por los 2 primeros chars para no saturar un dir.
        return self.root / digest[:2] / digest

    @staticmethod
    def ref_for(digest: str) -> str:
        return f"{REF_PREFIX}{digest}"

    @staticmethod
    def digest_of(ref: str) -> str:
        """Extrae el SHA-256 de una referencia ``blob://sha256:...``."""
        if not ref.startswith(REF_PREFIX):
            raise ValueError(f"referencia no es de object store: {ref!r}")
        return ref[len(REF_PREFIX):]

    def put(self, data: bytes) -> str:
        """Guarda ``data`` y devuelve su referencia. Idempotente."""
        digest = hashlib.sha256(data).hexdigest()
        path = self._path_for(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Escritura atómica: tmp + rename.
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.rename(path)
        return self.ref_for(digest)

    def put_file(self, src: Path | str) -> str:
        """Guarda el contenido de un archivo del disco y devuelve su referencia."""
        return self.put(Path(src).read_bytes())

    def get(self, ref: str) -> bytes:
        path = self._path_for(self.digest_of(ref))
        if not path.exists():
            raise KeyError(f"objeto no encontrado: {ref}")
        return path.read_bytes()

    def exists(self, ref: str) -> bool:
        return self._path_for(self.digest_of(ref)).exists()

    def path_of(self, ref: str) -> Path:
        """Ruta en disco de un objeto (para servirlo sin cargarlo en memoria)."""
        return self._path_for(self.digest_of(ref))
