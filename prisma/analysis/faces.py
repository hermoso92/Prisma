"""Reconocimiento facial local: enrolar "yo" e identificar caras conocidas.

Backend real local y gratuito: la librería ``face_recognition`` (dlib). Flujo:

1. **Enrolar**: con 3-5 fotos tuyas de referencia se calculan *embeddings* de tu
   cara y se guardan en ``cfg.faces_dir`` (JSON local, en tu equipo).
2. **Identificar**: por cada foto se detectan caras y se comparan con las
   enroladas; devuelve los nombres reconocidos (p. ej. ``["me"]``).

La regla "solo yo" (en :meth:`Analyzer.analyze`) combina esto con el recuento de
personas de YOLO: 1 persona ∧ es "me" ∧ sin animales.

Degrada con elegancia: si la librería no está o no has enrolado tu cara,
``identify`` devuelve ``None`` (no afirmamos nada). Instalar en Mac:
``brew install cmake && pipx install face_recognition``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

#: Distancia máxima para considerar que dos caras son la misma (dlib ~0.6).
_TOLERANCE = 0.6


class FaceStore:
    """Persistencia local de los embeddings enrolados (``nombre → [vectores]``)."""

    def __init__(self, faces_dir: Path | str) -> None:
        self.dir = Path(faces_dir)

    def _path(self) -> Path:
        return self.dir / "enrolled.json"

    def load(self) -> dict[str, list[list[float]]]:
        p = self._path()
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}

    def add(self, name: str, encodings: list[list[float]]) -> int:
        self.dir.mkdir(parents=True, exist_ok=True)
        data = self.load()
        data.setdefault(name, []).extend(encodings)
        self._path().write_text(json.dumps(data), encoding="utf-8")
        return len(data[name])


class FaceMatcher(ABC):
    """Interfaz de reconocimiento facial."""

    @abstractmethod
    def enroll(self, name: str, image_paths: list[Path]) -> int:
        """Registra la cara de ``name`` desde fotos. Devuelve nº de caras añadidas."""

    @abstractmethod
    def identify(self, data: bytes, suffix: str) -> Optional[list[str]]:
        """Nombres reconocidos en la imagen. ``None`` si no se pudo evaluar."""


class FaceRecognitionMatcher(FaceMatcher):
    """Backend real con la librería ``face_recognition`` (dlib)."""

    def __init__(self, store: FaceStore, tolerance: float = _TOLERANCE) -> None:
        self.store = store
        self.tolerance = tolerance
        self._warned = False

    def _lib(self):
        try:
            import face_recognition  # type: ignore
            return face_recognition
        except Exception:
            self._warn_once()
            return None

    def enroll(self, name: str, image_paths: list[Path]) -> int:
        fr = self._lib()
        if fr is None:
            return 0
        added: list[list[float]] = []
        for path in image_paths:
            image = fr.load_image_file(str(path))
            for enc in fr.face_encodings(image):
                added.append(enc.tolist())
        if added:
            self.store.add(name, added)
        return len(added)

    def identify(self, data: bytes, suffix: str) -> Optional[list[str]]:
        fr = self._lib()
        enrolled = self.store.load()
        if fr is None or not enrolled:
            return None
        import numpy as np  # face_recognition ya arrastra numpy
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / f"img{suffix}"
            img_path.write_bytes(data)
            image = fr.load_image_file(str(img_path))
            encodings = fr.face_encodings(image)
        known_names, known_vecs = [], []
        for nm, vecs in enrolled.items():
            for v in vecs:
                known_names.append(nm)
                known_vecs.append(np.array(v))
        matched: set[str] = set()
        for enc in encodings:
            dists = fr.face_distance(known_vecs, enc)
            if len(dists) and dists.min() <= self.tolerance:
                matched.add(known_names[int(dists.argmin())])
        return sorted(matched)

    def _warn_once(self) -> None:
        if not self._warned:
            print("⚠️  face_recognition no disponible; ingiero sin reconocimiento "
                  "facial. Instálalo: brew install cmake && pipx install face_recognition",
                  file=sys.stderr)
            self._warned = True
