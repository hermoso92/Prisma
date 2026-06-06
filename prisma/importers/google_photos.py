"""Importador de Google Photos (API viva, OAuth).

Cierra la flecha "—API—" del diagrama para fotos. Habla con la **Google Photos
Library API** por HTTP (con ``urllib``, sin dependencias nuevas) usando un token
de acceso OAuth que se obtiene del **gestor de secretos** (nunca se guarda en
disco en claro). Pagina ``mediaItems``, mapea cada uno a un :class:`Event` y, si
hay object store, descarga el binario original y lo deduplica.

Notas honestas:
- El token de acceso caduca (~1h); para histórico grande conviene un refresh
  token. Aquí el token se inyecta (desde secreto o entorno); la obtención OAuth
  completa es opcional y vive fuera (extra ``google``).
- La Library API **no** devuelve GPS (Google lo elimina); la fecha sí
  (``creationTime``). El ``id`` de cada media es estable → ingesta idempotente.

Decoplado y testeable: las llamadas HTTP (``_fetch_page`` / ``_download``) están
aisladas para poder mockearlas.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Iterator, Optional

from prisma.importers.base import Importer
from prisma.importers.util import normalize_iso
from prisma.schema import Event

_API = "https://photoslibrary.googleapis.com/v1/mediaItems"


class GooglePhotosError(RuntimeError):
    """Error de acceso a la API de Google Photos (token ausente/ inválido…)."""


class GooglePhotosImporter(Importer):
    source = "gphotos"

    def __init__(self, *args, access_token: Optional[str] = None,
                 download: bool = True, page_size: int = 100,
                 max_items: Optional[int] = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.access_token = access_token
        self.download = download
        self.page_size = page_size
        self.max_items = max_items

    def iter_events(self) -> Iterator[Event]:
        if not self.access_token:
            raise GooglePhotosError(
                "Falta el token de Google. Consíguelo (scope "
                "photoslibrary.readonly) y guárdalo: `prisma secret set google` "
                "(o variable PRISMA_GOOGLE_TOKEN)."
            )
        seen = 0
        page_token: Optional[str] = None
        while True:
            body = self._fetch_page(page_token)
            for item in body.get("mediaItems", []):
                yield self._to_event(item)
                seen += 1
                if self.max_items and seen >= self.max_items:
                    return
            page_token = body.get("nextPageToken")
            if not page_token:
                return

    # ------------------------------------------------------------ mapeo

    def _to_event(self, item: dict[str, Any]) -> Event:
        meta = item.get("mediaMetadata") or {}
        is_video = "video" in meta or (item.get("mimeType", "").startswith("video"))
        type_ = "video" if is_video else "photo"
        mime = item.get("mimeType", "image/jpeg")

        media: list[dict[str, Any]] = []
        source_meta: dict[str, Any] = {
            "filename": item.get("filename"),
            "google_id": item.get("id"),
        }
        base_url = item.get("baseUrl")
        if self.download and self.objects is not None and base_url:
            try:
                data = self._download(base_url, is_video)
                media = [{"ref": self.objects.put(data), "mime": mime, "role": "primary"}]
            except (urllib.error.URLError, OSError):
                source_meta["base_url"] = base_url  # quedó sin descargar
        elif base_url:
            source_meta["base_url"] = base_url

        return Event.create(
            source=self.source,
            source_native_id=item.get("id", base_url or item.get("filename", "?")),
            type=type_,
            timestamp=normalize_iso(meta.get("creationTime")) or "1970-01-01T00:00:00Z",
            content=item.get("description") or "",
            media=media,
            source_meta=source_meta,
        )

    # ------------------------------------------------------------ HTTP (mockeable)

    def _fetch_page(self, page_token: Optional[str]) -> dict[str, Any]:
        url = f"{_API}?pageSize={self.page_size}"
        if page_token:
            url += f"&pageToken={page_token}"
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self.access_token}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise GooglePhotosError(
                f"La API devolvió {exc.code}. ¿Token válido y con scope "
                f"photoslibrary.readonly?") from exc

    def _download(self, base_url: str, is_video: bool) -> bytes:
        # '=d' descarga el original (foto); '=dv' el vídeo.
        url = base_url + ("=dv" if is_video else "=d")
        with urllib.request.urlopen(url, timeout=120) as resp:
            return resp.read()
