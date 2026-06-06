"""Resolución de identidades de personas entre fuentes.

El mismo individuo aparece con nombres distintos según la fuente: "Juan" en
WhatsApp, "Juan Pérez" en una nota, un teléfono, etc. :class:`IdentityMap`
mantiene un mapa **alias → canónico** (local, editable por el usuario) para
unificarlos, de modo que "qué hablé con Juan" cruce todas las fuentes.

Persistencia: un JSON en la carpeta de datos (``identities.json``), con forma
``{"canónico": ["alias1", "alias2", ...]}``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


class IdentityMap:
    """Mapa de alias → identidad canónica, persistido en JSON local."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._canon: dict[str, list[str]] = self._load()
        self._reverse = self._build_reverse()

    def _load(self) -> dict[str, list[str]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}

    def _build_reverse(self) -> dict[str, str]:
        rev: dict[str, str] = {}
        for canonical, aliases in self._canon.items():
            rev[canonical.lower()] = canonical
            for a in aliases:
                rev[a.lower()] = canonical
        return rev

    def resolve(self, name: str) -> str:
        """Devuelve la identidad canónica de ``name`` (o el propio nombre)."""
        return self._reverse.get((name or "").lower(), name)

    def add(self, canonical: str, *aliases: str) -> None:
        """Asocia uno o más alias a una identidad canónica y guarda."""
        current = set(self._canon.get(canonical, []))
        current.update(a for a in aliases if a and a != canonical)
        self._canon[canonical] = sorted(current)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._canon, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        self._reverse = self._build_reverse()

    @property
    def resolver(self) -> Callable[[str], str]:
        return self.resolve
