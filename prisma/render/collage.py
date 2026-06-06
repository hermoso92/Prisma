"""Collage en cuadrícula a partir de varias imágenes (Pillow)."""

from __future__ import annotations

import io
import math
from pathlib import Path

from prisma.render.base import RenderError


def make_collage(images: list[bytes], out_path: Path | str,
                 cols: int | None = None, cell: int = 320, gap: int = 8) -> Path:
    """Compone las ``images`` en una cuadrícula y la guarda en ``out_path``.

    Requiere Pillow (``pip install pillow``). Lanza :class:`RenderError` si falta
    o si no hay imágenes.
    """
    if not images:
        raise RenderError("No hay imágenes para el collage.")
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RenderError(
            "Pillow no está instalado; no puedo hacer el collage. "
            "Instálalo: pipx inject prisma-context pillow  (o pip install pillow)"
        ) from exc

    n = len(images)
    cols = cols or max(1, round(math.sqrt(n)))
    rows = math.ceil(n / cols)
    width = cols * cell + (cols + 1) * gap
    height = rows * cell + (rows + 1) * gap
    canvas = Image.new("RGB", (width, height), (245, 245, 245))

    for i, raw in enumerate(images):
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            continue  # imagen ilegible: la saltamos
        img.thumbnail((cell, cell))
        r, c = divmod(i, cols)
        x = gap + c * (cell + gap) + (cell - img.width) // 2
        y = gap + r * (cell + gap) + (cell - img.height) // 2
        canvas.paste(img, (x, y))

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out
