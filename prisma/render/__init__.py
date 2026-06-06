"""Generación de salidas a partir de un conjunto de fotos: collage y vídeo.

Toma los binarios de imágenes (del object store) y produce un collage (Pillow) o
un vídeo/slideshow (ffmpeg), 100% en local. Ambos lanzan :class:`RenderError` con
un mensaje claro si falta la dependencia, en vez de un traceback.
"""

from prisma.render.collage import make_collage
from prisma.render.video import make_video
from prisma.render.base import RenderError

__all__ = ["make_collage", "make_video", "RenderError"]
