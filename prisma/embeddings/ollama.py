"""Embedder local con Ollama (recomendado).

Genera embeddings con un modelo de Ollama corriendo en local (por defecto
``nomic-embed-text``), gratis y offline. Habla con Ollama por HTTP con la
biblioteca estándar (sin dependencias). Si Ollama no está disponible, lanza una
excepción clara para que la CLI lo explique (a diferencia del análisis de
imágenes, aquí no degradamos en silencio: sin embeddings no hay búsqueda).

Configurable por entorno: ``PRISMA_OLLAMA_HOST``, ``PRISMA_OLLAMA_EMBED_MODEL``.
"""

from __future__ import annotations

import json
import os
import urllib.request

from prisma.embeddings.base import Embedder, register

_DEFAULT_HOST = os.environ.get("PRISMA_OLLAMA_HOST", "http://localhost:11434")
_DEFAULT_MODEL = os.environ.get("PRISMA_OLLAMA_EMBED_MODEL", "nomic-embed-text")


@register
class OllamaEmbedder(Embedder):
    name = "ollama"

    def __init__(self, host: str = _DEFAULT_HOST, model: str = _DEFAULT_MODEL) -> None:
        self.host = host.rstrip("/")
        self.model = model

    def embed(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        payload = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/embeddings", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        vec = body.get("embedding")
        if not vec:
            raise ValueError(f"Ollama no devolvió embedding (modelo {self.model}).")
        return vec
