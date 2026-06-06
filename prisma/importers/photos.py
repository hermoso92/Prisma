"""Importador de fotos y vídeos desde una carpeta.

Recorre un directorio (recursivamente), guarda cada medio en el object store
(content-addressed: deduplica binarios idénticos) y emite un :class:`Event` con:

- ``timestamp``: resuelto por orden de fiabilidad → sidecar de Google Takeout →
  EXIF (``DateTimeOriginal``) → fecha de modificación del fichero.
- ``location``: ``{lat, lon}`` desde el sidecar o el EXIF, si hay.
- ``media``: referencia al binario en el object store.

El *contenido buscable* (caption, OCR, transcripción) lo añade el pipeline a
través del :class:`~prisma.analysis.base.Analyzer` configurado; aquí solo se
extraen metadatos. Soporta los sidecars JSON de Google Takeout
(``foto.jpg.json``, ``foto.jpg.supplemental-metadata.json``, ``foto.json``).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from prisma.analysis.exif import parse_exif
from prisma.importers.base import Importer
from prisma.importers.util import normalize_iso, unix_to_iso
from prisma.schema import Event

# Extensión → (tipo de evento, mime).
_KINDS: dict[str, tuple[str, str]] = {
    ".jpg": ("photo", "image/jpeg"), ".jpeg": ("photo", "image/jpeg"),
    ".png": ("photo", "image/png"), ".gif": ("photo", "image/gif"),
    ".webp": ("photo", "image/webp"), ".heic": ("photo", "image/heic"),
    ".tif": ("photo", "image/tiff"), ".tiff": ("photo", "image/tiff"),
    ".mp4": ("video", "video/mp4"), ".mov": ("video", "video/quicktime"),
    ".m4v": ("video", "video/x-m4v"), ".avi": ("video", "video/x-msvideo"),
    ".mkv": ("video", "video/x-matroska"),
    ".m4a": ("audio", "audio/mp4"), ".mp3": ("audio", "audio/mpeg"),
    ".wav": ("audio", "audio/wav"), ".ogg": ("audio", "audio/ogg"),
    ".opus": ("audio", "audio/opus"),
}


class PhotosImporter(Importer):
    source = "photos"

    def iter_events(self) -> Iterator[Event]:
        if self.source_path is None:
            raise ValueError("PhotosImporter requiere source_path (una carpeta)")
        if self.objects is None:
            raise ValueError("PhotosImporter requiere un object store")
        root = self.source_path
        paths = sorted(root.rglob("*")) if root.is_dir() else [root]
        for path in paths:
            if not path.is_file():
                continue
            kind = _KINDS.get(path.suffix.lower())
            if kind is None:
                continue  # no es medio (p. ej. el propio .json sidecar)
            yield self._build_event(path, *kind)

    def _build_event(self, path: Path, type: str, mime: str) -> Event:
        data = path.read_bytes()
        ref = self.objects.put(data)  # type: ignore[union-attr]
        digest = ref.rsplit(":", 1)[-1]

        sidecar = self._load_sidecar(path)
        timestamp = self._resolve_timestamp(path, data, sidecar)
        location = self._resolve_location(data, sidecar)

        source_meta: dict[str, Any] = {"filename": path.name}
        if sidecar:
            source_meta["sidecar"] = True

        return Event.create(
            source=self.source,
            source_native_id=digest,  # estable y dedup: mismo binario → mismo id
            type=type,
            timestamp=timestamp,
            content="",  # lo rellena el analizador (caption/transcripción)
            location=location,
            media=[{"ref": ref, "mime": mime, "role": "primary"}],
            source_meta=source_meta,
        )

    # ---------------------------------------------------------------- sidecar

    @staticmethod
    def _load_sidecar(path: Path) -> Optional[dict]:
        for cand in (
            path.with_name(path.name + ".json"),
            path.with_name(path.name + ".supplemental-metadata.json"),
            path.with_suffix(".json"),
        ):
            if cand.is_file():
                try:
                    return json.loads(cand.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    return None
        return None

    # --------------------------------------------------------------- resolución

    def _resolve_timestamp(self, path: Path, data: bytes, sidecar: Optional[dict]) -> str:
        # 1) Sidecar de Google Takeout.
        if sidecar:
            taken = (sidecar.get("photoTakenTime") or {}).get("timestamp")
            iso = unix_to_iso(taken) if taken else None
            if iso:
                return iso
        # 2) EXIF.
        dt = parse_exif(data).get("datetime")
        if dt:
            iso = self._exif_dt_to_iso(dt)
            if iso:
                return iso
        # 3) Fecha de modificación del fichero.
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    @staticmethod
    def _resolve_location(data: bytes, sidecar: Optional[dict]) -> Optional[dict]:
        if sidecar:
            geo = sidecar.get("geoData") or sidecar.get("geoDataExif") or {}
            lat, lon = geo.get("latitude"), geo.get("longitude")
            if lat or lon:  # Takeout usa 0.0 cuando no hay dato
                return {"lat": lat, "lon": lon}
        gps = parse_exif(data).get("gps")
        if gps:
            return {"lat": gps[0], "lon": gps[1]}
        return None

    @staticmethod
    def _exif_dt_to_iso(dt: str) -> Optional[str]:
        # EXIF: "YYYY:MM:DD HH:MM:SS" (hora local, sin zona → se asume UTC).
        try:
            d, t = dt.split(" ", 1)
            return normalize_iso(f"{d.replace(':', '-')}T{t}Z")
        except (ValueError, IndexError):
            return None
