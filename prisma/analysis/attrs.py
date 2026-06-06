"""Analizador de atributos estructurados de fotos.

Combina **detección** (personas/animales, vía :class:`Detector`) y **reconocimiento
facial** (caras conocidas, vía :class:`FaceMatcher`) para rellenar ``derived`` con
``people_count``, ``animals``, ``faces`` y la bandera derivada ``is_only_me``.

Es lo que habilita el caso "búscame fotos donde salga solo yo, sin gatos ni otras
personas". Cada motor degrada por su cuenta si su herramienta no está instalada.
"""

from __future__ import annotations

from typing import Any, Optional

from prisma.analysis.base import Analyzer, register
from prisma.analysis.detect import Detector, YoloDetector, _EXT
from prisma.analysis.faces import FaceMatcher, FaceRecognitionMatcher, FaceStore


@register
class AttributesAnalyzer(Analyzer):
    name = "attrs"

    def __init__(self, detector: Optional[Detector] = None,
                 matcher: Optional[FaceMatcher] = None) -> None:
        self.detector = detector or YoloDetector()
        self.matcher = matcher  # se completa en configure() con la ruta de datos

    def configure(self, cfg: Any) -> None:
        # El reconocedor necesita saber dónde está la cara enrolada.
        if self.matcher is None:
            self.matcher = FaceRecognitionMatcher(FaceStore(cfg.faces_dir))

    def detect(self, *, data: bytes, mime: str, type: str) -> dict[str, Any]:
        if type != "photo":
            return {}
        return self.detector.detect_image(data, _EXT.get(mime, ".jpg")) or {}

    def identify(self, *, data: bytes, mime: str, type: str) -> Optional[list[str]]:
        if type != "photo" or self.matcher is None:
            return None
        return self.matcher.identify(data, _EXT.get(mime, ".jpg"))
