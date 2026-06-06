"""Utilidades compartidas por los importadores.

- Apertura flexible de exports: acepta un ``.zip``, una carpeta descomprimida o
  un ``.json`` directo, y localiza el fichero buscado (p. ej.
  ``conversations.json``) esté donde esté dentro del archivo.
- Normalización de timestamps a ISO-8601 UTC (con sufijo ``Z``), tanto desde
  epoch Unix (ChatGPT) como desde cadenas ISO (Claude).
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def unix_to_iso(ts: Any) -> Optional[str]:
    """Convierte un epoch Unix (segundos, int/float) a ISO-8601 UTC."""
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def normalize_iso(value: Any) -> Optional[str]:
    """Normaliza una cadena ISO-8601 (con o sin ``Z``/offset/fracciones) a UTC ``Z``."""
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json_member(path: Path | str, *candidates: str) -> Any:
    """Carga un JSON desde un export, sea ``.zip``, carpeta o fichero directo.

    ``candidates`` son nombres de fichero a buscar (por *basename*), en orden de
    preferencia. Ej.: ``load_json_member(p, "conversations.json")``.
    """
    path = Path(path)
    cand = candidates or ()

    # 1) ZIP: buscar el miembro por basename en cualquier subcarpeta.
    if path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            member = _match_member(z.namelist(), cand)
            with z.open(member) as fh:
                return json.load(fh)

    # 2) Carpeta: buscar el fichero (en raíz y recursivamente).
    if path.is_dir():
        for name in cand:
            for found in (path / name, *path.rglob(name)):
                if found.is_file():
                    return json.loads(found.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"No encontré {cand} dentro de {path}")

    # 3) Fichero JSON directo.
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))

    raise FileNotFoundError(f"Ruta no válida: {path}")


def _match_member(names: list[str], candidates: tuple[str, ...]) -> str:
    if not candidates:
        raise ValueError("se requieren nombres candidatos para buscar en el ZIP")
    for cand in candidates:
        for name in names:
            if name == cand or name.rsplit("/", 1)[-1] == cand:
                return name
    raise FileNotFoundError(
        f"No encontré {candidates} en el ZIP (miembros: {names[:10]}...)"
    )
