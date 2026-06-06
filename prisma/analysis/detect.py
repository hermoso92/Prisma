"""Detección de objetos en imágenes: cuántas personas hay y qué animales.

Backend real local y gratuito: **YOLO** (ultralytics), que corre offline en tu
Mac. De cada imagen extrae:

- ``people_count`` — nº de personas detectadas.
- ``animals`` — lista de animales (gato, perro…), clave para el caso "sin gatos".
- ``objects`` — etiquetas más frecuentes (contexto).

Degrada con elegancia: si ultralytics no está instalado, ``detect`` devuelve
``{}`` (la foto se ingiere igual, solo sin estos atributos) y avisa una vez.
Instalar en Mac:  ``pipx install ultralytics``  (o ``pip install ultralytics``).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from prisma.analysis.base import Analyzer, register

# Clases COCO consideradas "animal".
_ANIMALS = {"bird", "cat", "dog", "horse", "sheep", "cow",
            "elephant", "bear", "zebra", "giraffe"}
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
        "image/gif": ".gif", "image/tiff": ".tif", "image/heic": ".heic"}


class Detector:
    """Interfaz de detección. ``detect_image`` recibe los bytes de una imagen."""

    def detect_image(self, data: bytes, suffix: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError


class YoloDetector(Detector):
    """Detector basado en YOLO (ultralytics). Carga el modelo de forma perezosa."""

    def __init__(self, model: Optional[str] = None, conf: float = 0.35) -> None:
        self.model_name = model or os.environ.get("PRISMA_YOLO_MODEL", "yolov8n.pt")
        self.conf = conf
        self._model = None
        self._unavailable = False
        self._warned = False

    def _load(self):
        if self._model is None and not self._unavailable:
            try:
                from ultralytics import YOLO  # type: ignore
                self._model = YOLO(self.model_name)
            except Exception:
                self._unavailable = True
        return self._model

    def detect_image(self, data: bytes, suffix: str) -> Optional[dict[str, Any]]:
        model = self._load()
        if model is None:
            self._warn_once()
            return None
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / f"img{suffix}"
            img.write_bytes(data)
            try:
                results = model(str(img), conf=self.conf, verbose=False)
            except Exception:
                self._warn_once()
                return None
        return self._summarize(model, results)

    @staticmethod
    def _summarize(model, results) -> dict[str, Any]:
        people = 0
        animals: list[str] = []
        objects: list[str] = []
        names = getattr(model, "names", {})
        for res in results:
            for box in getattr(res, "boxes", []):
                label = names.get(int(box.cls[0]), "")
                objects.append(label)
                if label == "person":
                    people += 1
                elif label in _ANIMALS:
                    animals.append(label)
        return {
            "people_count": people,
            "animals": sorted(set(animals)),
            "objects": sorted(set(objects)),
        }

    def _warn_once(self) -> None:
        if not self._warned:
            print("⚠️  YOLO (ultralytics) no disponible; ingiero sin detección de "
                  "personas/animales. Instálalo: pipx install ultralytics",
                  file=sys.stderr)
            self._warned = True


@register
class DetectAnalyzer(Analyzer):
    """Analizador que solo hace detección de objetos (personas/animales)."""

    name = "detect"

    def __init__(self, detector: Optional[Detector] = None) -> None:
        self.detector = detector or YoloDetector()

    def detect(self, *, data: bytes, mime: str, type: str) -> dict[str, Any]:
        if type != "photo":
            return {}
        result = self.detector.detect_image(data, _EXT.get(mime, ".jpg"))
        return result or {}
