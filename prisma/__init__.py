"""Prisma — tu cerebro de contexto personal.

Paquete raíz. Expone las piezas principales de la Fase 0 (cimientos):
el esquema común (`Event`), el almacenamiento y el orquestador de ingesta.
"""

from prisma.schema import Event, make_event_id, SCHEMA_VERSION

__all__ = ["Event", "make_event_id", "SCHEMA_VERSION"]
__version__ = "0.0.1"
