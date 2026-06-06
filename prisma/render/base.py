"""Utilidades comunes de render."""

from __future__ import annotations


class RenderError(RuntimeError):
    """Error de generación de collage/vídeo (dependencia ausente, sin imágenes…)."""
