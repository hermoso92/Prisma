"""Embedder de respaldo por *hashing* (determinista, sin dependencias).

Proyecta el texto en un vector de dimensión fija usando el *hashing trick* sobre
palabras y bigramas, con peso tf sublineal y normalización L2. **No es semántico**
(no entiende sinónimos): mide solapamiento léxico. Sirve como respaldo offline y
para probar la maquinaria de búsqueda vectorial sin necesidad de Ollama.
"""

from __future__ import annotations

import hashlib
import math
import re

from prisma.embeddings.base import Embedder, register

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@register
class HashingEmbedder(Embedder):
    name = "hashing"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self.model = f"hashing-{dim}"

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = _TOKEN_RE.findall((text or "").lower())
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        counts: dict[int, int] = {}
        for feat in features:
            h = int.from_bytes(hashlib.md5(feat.encode("utf-8")).digest()[:4], "big")
            counts[h % self.dim] = counts.get(h % self.dim, 0) + 1
        for idx, c in counts.items():
            vec[idx] = 1.0 + math.log(c)  # tf sublineal
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec
