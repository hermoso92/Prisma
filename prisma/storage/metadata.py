"""Almacén de metadatos / línea temporal (SQLite).

Guarda los :class:`~prisma.schema.Event`. El dedupe es por clave primaria
(``id`` determinista): insertar el mismo evento dos veces no duplica. Los campos
compuestos (listas, dicts) se serializan a JSON en columnas dedicadas, y se
mantienen además columnas escalares (``timestamp``, ``source``, ``type``,
``thread_id``) para poder filtrar e indexar de forma eficiente.

Fase 0: SQLite. Sustituible por Postgres al escalar.
"""

from __future__ import annotations

import array
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from prisma.schema import Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    type          TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    title         TEXT,
    content       TEXT NOT NULL DEFAULT '',
    thread_id     TEXT,
    people        TEXT NOT NULL DEFAULT '[]',   -- JSON
    location      TEXT,                          -- JSON
    media         TEXT NOT NULL DEFAULT '[]',   -- JSON
    source_meta   TEXT NOT NULL DEFAULT '{}',   -- JSON
    derived       TEXT NOT NULL DEFAULT '{}',   -- JSON
    ingested_at   TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_source    ON events(source);
CREATE INDEX IF NOT EXISTS idx_events_thread    ON events(thread_id);

-- Estado de cada fuente: cursor incremental, último import, etc.
CREATE TABLE IF NOT EXISTS sources (
    source       TEXT PRIMARY KEY,
    cursor       TEXT,
    last_ingest  TEXT,
    event_count  INTEGER NOT NULL DEFAULT 0
);

-- Embeddings para búsqueda semántica. La clave incluye el "espacio" (modelo)
-- para no mezclar vectores de embedders distintos. vec = float32 empaquetado.
CREATE TABLE IF NOT EXISTS embeddings (
    event_id   TEXT NOT NULL,
    space      TEXT NOT NULL,
    vec        BLOB NOT NULL,
    PRIMARY KEY (event_id, space),
    FOREIGN KEY (event_id) REFERENCES events(id)
);
"""

_JSON_FIELDS = ("people", "location", "media", "source_meta", "derived")


class MetadataStore:
    """Persistencia de eventos en SQLite."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "MetadataStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ write

    def add_event(self, event: Event) -> bool:
        """Inserta un evento. Devuelve ``True`` si era nuevo, ``False`` si ya existía.

        El dedupe es por ``id``: un evento ya presente se ignora (no se machaca),
        lo que hace la ingesta idempotente y barata de reejecutar.
        """
        row = self._event_to_row(event)
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        cur = self._conn.execute(
            f"INSERT OR IGNORE INTO events ({cols}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def add_events(self, events: Iterable[Event]) -> tuple[int, int]:
        """Inserta varios eventos. Devuelve ``(nuevos, omitidos)``."""
        new = skipped = 0
        for ev in events:
            if self.add_event(ev):
                new += 1
            else:
                skipped += 1
        return new, skipped

    # ------------------------------------------------------------------- read

    def get_event(self, event_id: str) -> Optional[Event]:
        row = self._conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        return self._row_to_event(row) if row else None

    def count(self, source: Optional[str] = None) -> int:
        if source:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE source = ?", (source,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
        return int(row["n"])

    def counts_by_source(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT source, COUNT(*) AS n FROM events GROUP BY source ORDER BY n DESC"
        ).fetchall()
        return {r["source"]: int(r["n"]) for r in rows}

    def timeline(
        self,
        *,
        since: Optional[str] = None,
        until: Optional[str] = None,
        source: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Iterator[Event]:
        """Recorre eventos por orden cronológico, con filtros opcionales."""
        clauses, params = [], []
        if since:
            clauses.append("timestamp >= ?"); params.append(since)
        if until:
            clauses.append("timestamp <= ?"); params.append(until)
        if source:
            clauses.append("source = ?"); params.append(source)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM events {where} ORDER BY timestamp ASC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        for row in self._conn.execute(sql, params):
            yield self._row_to_event(row)

    def thread(self, thread_id: str) -> list[Event]:
        """Reconstruye una conversación: sus eventos por orden cronológico."""
        rows = self._conn.execute(
            "SELECT * FROM events WHERE thread_id = ? ORDER BY timestamp ASC",
            (thread_id,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def photos_where(
        self,
        *,
        only_me: Optional[bool] = None,
        max_people: Optional[int] = None,
        no_animals: bool = False,
        limit: Optional[int] = None,
    ) -> list[Event]:
        """Filtra fotos por atributos estructurados de ``derived`` (vía json_extract).

        - ``only_me``: exige ``derived.is_only_me``.
        - ``max_people``: nº de personas ≤ este valor.
        - ``no_animals``: sin animales detectados (lista ``animals`` vacía).
        """
        clauses = ["type = 'photo'"]
        params: list[Any] = []
        if only_me is not None:
            clauses.append("json_extract(derived, '$.is_only_me') = ?")
            params.append(1 if only_me else 0)
        if max_people is not None:
            clauses.append("json_extract(derived, '$.people_count') <= ?")
            params.append(max_people)
        if no_animals:
            # animals ausente o lista vacía cuenta como "sin animales".
            clauses.append(
                "(json_extract(derived, '$.animals') IS NULL "
                "OR json_array_length(json_extract(derived, '$.animals')) = 0)"
            )
        sql = f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY timestamp ASC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [self._row_to_event(r) for r in self._conn.execute(sql, params)]

    def search(self, text: str, limit: int = 50) -> list[Event]:
        """Búsqueda ingenua por subcadena en ``content``/``title``.

        Provisional de la Fase 0; la búsqueda semántica llega en la Fase 4.
        """
        like = f"%{text}%"
        rows = self._conn.execute(
            "SELECT * FROM events WHERE content LIKE ? OR title LIKE ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    # ---------------------------------------------------------------- sources

    def get_cursor(self, source: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT cursor FROM sources WHERE source = ?", (source,)
        ).fetchone()
        return row["cursor"] if row else None

    def set_cursor(self, source: str, cursor: Optional[str]) -> None:
        from prisma.schema import utcnow_iso
        self._conn.execute(
            "INSERT INTO sources (source, cursor, last_ingest, event_count) "
            "VALUES (?, ?, ?, (SELECT COUNT(*) FROM events WHERE source = ?)) "
            "ON CONFLICT(source) DO UPDATE SET cursor = excluded.cursor, "
            "last_ingest = excluded.last_ingest, event_count = excluded.event_count",
            (source, cursor, utcnow_iso(), source),
        )
        self._conn.commit()

    # ------------------------------------------------------------- embeddings

    def add_embedding(self, event_id: str, space: str, vector: list[float]) -> None:
        """Guarda (o reemplaza) el embedding de un evento en un espacio dado."""
        blob = array.array("f", vector).tobytes()
        self._conn.execute(
            "INSERT OR REPLACE INTO embeddings (event_id, space, vec) VALUES (?, ?, ?)",
            (event_id, space, blob),
        )
        self._conn.commit()

    def count_embeddings(self, space: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM embeddings WHERE space = ?", (space,)
        ).fetchone()
        return int(row["n"])

    def iter_unembedded(self, space: str) -> Iterator[Event]:
        """Eventos con texto que aún no tienen embedding en ``space``."""
        rows = self._conn.execute(
            "SELECT e.* FROM events e "
            "LEFT JOIN embeddings em ON em.event_id = e.id AND em.space = ? "
            "WHERE em.event_id IS NULL AND e.content <> '' "
            "ORDER BY e.timestamp ASC",
            (space,),
        ).fetchall()
        for row in rows:
            yield self._row_to_event(row)

    def vector_search(
        self, query: list[float], space: str, limit: int = 20
    ) -> list[tuple[Event, float]]:
        """Búsqueda por similitud coseno. Devuelve ``[(evento, score), ...]``.

        Fuerza bruta en Python puro: suficiente para una base personal. Para
        escalar, se sustituiría por un índice vectorial (FAISS/Qdrant/pgvector).
        """
        qnorm = math.sqrt(sum(c * c for c in query)) or 1.0
        rows = self._conn.execute(
            "SELECT e.*, em.vec AS _vec FROM embeddings em "
            "JOIN events e ON e.id = em.event_id WHERE em.space = ?",
            (space,),
        ).fetchall()
        scored: list[tuple[Event, float]] = []
        for row in rows:
            vec = array.array("f")
            vec.frombytes(row["_vec"])
            dot = sum(q * v for q, v in zip(query, vec))
            vnorm = math.sqrt(sum(v * v for v in vec)) or 1.0
            d = {k: row[k] for k in row.keys() if k != "_vec"}
            scored.append((self._row_to_event(d), dot / (qnorm * vnorm)))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:limit]

    # ------------------------------------------------------------ (de)serialize

    @staticmethod
    def _event_to_row(event: Event) -> dict[str, Any]:
        d = event.to_dict()
        for f in _JSON_FIELDS:
            d[f] = json.dumps(d[f], ensure_ascii=False) if d[f] is not None else None
        return d

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        d = dict(row)
        for f in _JSON_FIELDS:
            d[f] = json.loads(d[f]) if d[f] is not None else None
        return Event.from_dict(d)
