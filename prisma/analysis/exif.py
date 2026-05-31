"""Parser EXIF mínimo, sin dependencias.

Extrae de un JPEG las dos cosas que de verdad importan para la línea temporal:
la **fecha de captura** (``DateTimeOriginal``) y las **coordenadas GPS**. Es
*best-effort*: ante cualquier formato inesperado devuelve lo que haya podido leer
sin lanzar excepción. Para fuentes con sidecar (Google Takeout) el importador
prefiere el sidecar, así que esto cubre el caso de fotos "sueltas".

No pretende ser un parser EXIF completo; solo recorre el árbol TIFF/IFD lo justo
para esos dos datos.
"""

from __future__ import annotations

import struct
from typing import Any, Optional

# Tamaño en bytes de cada tipo TIFF.
_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}

_TAG_EXIF_IFD = 0x8769
_TAG_GPS_IFD = 0x8825
_TAG_DATETIME = 0x0132          # en IFD0 (fallback)
_TAG_DATETIME_ORIGINAL = 0x9003  # en Exif SubIFD (preferido)


def parse_exif(data: bytes) -> dict[str, Any]:
    """Devuelve ``{"datetime": "YYYY:MM:DD HH:MM:SS"|None, "gps": (lat, lon)|None}``."""
    result: dict[str, Any] = {"datetime": None, "gps": None}
    try:
        tiff = data.find(b"Exif\x00\x00")
        if tiff == -1:
            return result
        tiff += 6  # los offsets EXIF son relativos al inicio del bloque TIFF

        bo = {b"II": "<", b"MM": ">"}.get(data[tiff:tiff + 2])
        if bo is None:
            return result
        ifd0_off = struct.unpack(bo + "I", data[tiff + 4:tiff + 8])[0]
        ifd0 = _read_ifd(data, tiff, ifd0_off, bo)

        # Fecha: DateTimeOriginal (SubIFD) y, si no, DateTime (IFD0).
        if _TAG_EXIF_IFD in ifd0:
            sub_off = _scalar(data, tiff, bo, *ifd0[_TAG_EXIF_IFD])
            sub = _read_ifd(data, tiff, sub_off, bo)
            if _TAG_DATETIME_ORIGINAL in sub:
                result["datetime"] = _ascii(data, tiff, bo, *sub[_TAG_DATETIME_ORIGINAL])
        if result["datetime"] is None and _TAG_DATETIME in ifd0:
            result["datetime"] = _ascii(data, tiff, bo, *ifd0[_TAG_DATETIME])

        # GPS.
        if _TAG_GPS_IFD in ifd0:
            gps_off = _scalar(data, tiff, bo, *ifd0[_TAG_GPS_IFD])
            result["gps"] = _read_gps(data, tiff, gps_off, bo)
    except Exception:
        return result
    return result


def _read_ifd(data, tiff, rel_off, bo) -> dict[int, tuple]:
    base = tiff + rel_off
    n = struct.unpack(bo + "H", data[base:base + 2])[0]
    entries: dict[int, tuple] = {}
    for i in range(n):
        e = base + 2 + i * 12
        tag, typ, count = struct.unpack(bo + "HHI", data[e:e + 8])
        entries[tag] = (typ, count, data[e + 8:e + 12])
    return entries


def _value_bytes(data, tiff, bo, typ, count, raw) -> bytes:
    size = _TYPE_SIZE.get(typ, 1) * count
    if size <= 4:
        return raw[:size]
    off = struct.unpack(bo + "I", raw)[0]
    return data[tiff + off:tiff + off + size]


def _scalar(data, tiff, bo, typ, count, raw) -> int:
    return struct.unpack(bo + "I", _value_bytes(data, tiff, bo, typ, count, raw)[:4])[0]


def _ascii(data, tiff, bo, typ, count, raw) -> Optional[str]:
    b = _value_bytes(data, tiff, bo, typ, count, raw)
    s = b.split(b"\x00", 1)[0].decode("ascii", "ignore").strip()
    return s or None


def _rationals(data, tiff, bo, typ, count, raw) -> list[float]:
    b = _value_bytes(data, tiff, bo, typ, count, raw)
    out = []
    for i in range(count):
        num, den = struct.unpack(bo + "II", b[i * 8:i * 8 + 8])
        out.append(num / den if den else 0.0)
    return out


def _read_gps(data, tiff, rel_off, bo) -> Optional[tuple[float, float]]:
    gps = _read_ifd(data, tiff, rel_off, bo)
    if 2 not in gps or 4 not in gps:
        return None
    lat = _dms_to_deg(_rationals(data, tiff, bo, *gps[2]))
    lon = _dms_to_deg(_rationals(data, tiff, bo, *gps[4]))
    if 1 in gps and (_ascii(data, tiff, bo, *gps[1]) or "N").upper().startswith("S"):
        lat = -lat
    if 3 in gps and (_ascii(data, tiff, bo, *gps[3]) or "E").upper().startswith("W"):
        lon = -lon
    return (round(lat, 6), round(lon, 6))


def _dms_to_deg(dms: list[float]) -> float:
    d = dms + [0, 0, 0]
    return d[0] + d[1] / 60 + d[2] / 3600
