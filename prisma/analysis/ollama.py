"""Analizador local con Ollama.

Usa un servidor Ollama corriendo en local (``http://localhost:11434``) para
describir imágenes con un modelo de visión (por defecto ``llava``), 100% gratis y
offline. La transcripción de audio no la cubre Ollama (eso es Whisper); aquí solo
hacemos ``caption``.

Diseño:
- Sin dependencias: habla con Ollama por HTTP con ``urllib`` de la stdlib.
- **Degradación elegante**: si Ollama no está disponible, ``caption`` devuelve
  ``None`` (el evento se ingiere igual, solo sin descripción) y se avisa una vez.
- Modelo y host configurables por entorno: ``PRISMA_OLLAMA_HOST``,
  ``PRISMA_OLLAMA_VISION_MODEL``.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional

from prisma.analysis.base import Analyzer, register

_DEFAULT_HOST = os.environ.get("PRISMA_OLLAMA_HOST", "http://localhost:11434")
_DEFAULT_MODEL = os.environ.get("PRISMA_OLLAMA_VISION_MODEL", "llava")
_PROMPT = "Describe esta imagen en español en una frase concisa, mencionando objetos, personas y lugar si se aprecian."


@register
class OllamaAnalyzer(Analyzer):
    name = "ollama"

    def __init__(self, host: str = _DEFAULT_HOST, model: str = _DEFAULT_MODEL) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self._warned = False

    def caption(self, *, data: bytes, mime: str, type: str) -> Optional[str]:
        if type not in ("photo", "video"):
            return None
        try:
            return self._generate(data)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self._warn_once(exc)
            return None

    def _generate(self, image: bytes) -> Optional[str]:
        payload = json.dumps({
            "model": self.model,
            "prompt": _PROMPT,
            "images": [base64.b64encode(image).decode("ascii")],
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/generate", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = (body.get("response") or "").strip()
        return text or None

    def _warn_once(self, exc: Exception) -> None:
        if not self._warned:
            print(
                f"⚠️  Ollama no disponible ({exc}); ingiero sin descripción de "
                f"imágenes. Instálalo con: brew install ollama && ollama pull {self.model}",
                file=sys.stderr,
            )
            self._warned = True
