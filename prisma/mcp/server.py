"""Servidor MCP de Prisma (JSON-RPC 2.0 sobre stdio, sin dependencias).

Herramientas expuestas:

- ``search_context``  — busca en tu contexto (semántica o literal).
- ``get_timeline``    — eventos de un rango de fechas (cruzando fuentes).
- ``get_thread``      — reconstruye una conversación completa.
- ``summarize_period``— devuelve el material de un periodo para que el LLM resuma.
- ``stats``           — qué hay en tu base (conteo por fuente).

El servidor no llama a ningún LLM ni manda nada fuera: solo lee tu base local y
devuelve texto. La inteligencia la pone el cliente (Claude) al otro lado de MCP.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Optional

from prisma import __version__
from prisma.embeddings import get_embedder
from prisma.schema import Event
from prisma.storage import MetadataStore

PROTOCOL_VERSION = "2024-11-05"

# Definición de herramientas (name, description, JSON Schema de entrada).
TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_context",
        "description": (
            "Busca en el contexto personal del usuario (chats, WhatsApp, notas, "
            "fotos...). Por defecto búsqueda por significado (semántica)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Qué buscar."},
                "semantic": {"type": "boolean", "default": True,
                             "description": "True = por significado; False = literal."},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_timeline",
        "description": "Eventos del usuario en un rango de fechas (ISO-8601), cruzando fuentes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "Fecha desde (ISO-8601)."},
                "until": {"type": "string", "description": "Fecha hasta (ISO-8601)."},
                "source": {"type": "string", "description": "Filtra por fuente."},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "get_thread",
        "description": "Reconstruye una conversación completa por su thread_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"thread_id": {"type": "string"}},
            "required": ["thread_id"],
        },
    },
    {
        "name": "summarize_period",
        "description": (
            "Devuelve los eventos de un periodo para que tú (el modelo) los resumas. "
            "No resume por su cuenta: te da el material."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {"type": "string"},
                "until": {"type": "string"},
                "limit": {"type": "integer", "default": 200},
            },
            "required": ["since", "until"],
        },
    },
    {
        "name": "stats",
        "description": "Resumen de qué hay en la base: conteo de eventos por fuente.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class McpServer:
    """Maneja mensajes MCP contra un :class:`MetadataStore`."""

    def __init__(self, store: MetadataStore, embedder_name: str = "ollama") -> None:
        self.store = store
        self.embedder_name = embedder_name
        self._handlers: dict[str, Callable[[dict], dict]] = {
            "search_context": self._t_search,
            "get_timeline": self._t_timeline,
            "get_thread": self._t_thread,
            "summarize_period": self._t_summarize,
            "stats": self._t_stats,
        }

    # ----------------------------------------------------------- JSON-RPC core

    def handle(self, msg: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Procesa un mensaje JSON-RPC. Devuelve la respuesta o ``None`` (notif.)."""
        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            return self._ok(msg_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "prisma", "version": __version__},
            })
        if method == "notifications/initialized":
            return None  # notificación: sin respuesta
        if method == "ping":
            return self._ok(msg_id, {})
        if method == "tools/list":
            return self._ok(msg_id, {"tools": TOOLS})
        if method == "tools/call":
            return self._call_tool(msg_id, msg.get("params") or {})
        if msg_id is not None:
            return self._err(msg_id, -32601, f"Método no soportado: {method}")
        return None

    def _call_tool(self, msg_id: Any, params: dict) -> dict:
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = self._handlers.get(name)
        if handler is None:
            return self._err(msg_id, -32602, f"Herramienta desconocida: {name}")
        try:
            return self._ok(msg_id, handler(args))
        except Exception as exc:  # nunca tumbamos el servidor por un error de tool
            return self._ok(msg_id, self._text(f"Error: {exc}", is_error=True))

    @staticmethod
    def _ok(msg_id: Any, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _err(msg_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}

    @staticmethod
    def _text(text: str, is_error: bool = False) -> dict:
        return {"content": [{"type": "text", "text": text}], "isError": is_error}

    # --------------------------------------------------------------- las tools

    def _t_search(self, args: dict) -> dict:
        query = args["query"]
        limit = int(args.get("limit", 10))
        semantic = args.get("semantic", True)
        if semantic:
            embedder = get_embedder(self.embedder_name)
            scored = self.store.vector_search(embedder.embed(query), embedder.key, limit)
            if not scored:
                return self._text(
                    "Sin resultados semánticos. ¿Se ha ejecutado `prisma index`? "
                    "Puedo probar búsqueda literal si lo pides (semantic=false)."
                )
            lines = [f"[{s:.2f}] {self._fmt(ev)}" for ev, s in scored]
        else:
            events = self.store.search(query, limit=limit)
            lines = [self._fmt(ev) for ev in events] or ["Sin resultados."]
        return self._text("\n".join(lines))

    def _t_timeline(self, args: dict) -> dict:
        events = list(self.store.timeline(
            since=args.get("since"), until=args.get("until"),
            source=args.get("source"), limit=int(args.get("limit", 50)),
        ))
        if not events:
            return self._text("Sin eventos en ese rango.")
        return self._text("\n".join(self._fmt(ev) for ev in events))

    def _t_thread(self, args: dict) -> dict:
        events = self.store.thread(args["thread_id"])
        if not events:
            return self._text(f"No hay conversación con thread_id={args['thread_id']!r}.")
        title = events[0].title or args["thread_id"]
        body = "\n".join(f"{ev.timestamp} — {self._who(ev)}: {ev.content}" for ev in events)
        return self._text(f"# {title}\n{body}")

    def _t_summarize(self, args: dict) -> dict:
        events = list(self.store.timeline(
            since=args["since"], until=args["until"], limit=int(args.get("limit", 200)),
        ))
        if not events:
            return self._text("No hay material en ese periodo para resumir.")
        header = (f"Material de {args['since']} a {args['until']} "
                  f"({len(events)} eventos). Resume lo importante:\n")
        return self._text(header + "\n".join(self._fmt(ev) for ev in events))

    def _t_stats(self, args: dict) -> dict:
        counts = self.store.counts_by_source()
        if not counts:
            return self._text("La base está vacía todavía.")
        lines = [f"{src}: {n}" for src, n in counts.items()]
        lines.append(f"TOTAL: {self.store.count()}")
        return self._text("\n".join(lines))

    # ------------------------------------------------------------------ format

    @staticmethod
    def _who(ev: Event) -> str:
        return ev.people[0] if ev.people else ev.source

    def _fmt(self, ev: Event) -> str:
        snippet = (ev.content or ev.title or "").replace("\n", " ")
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        return f"{ev.timestamp} [{ev.source}/{ev.type}] {snippet}"

    # --------------------------------------------------------------- I/O stdio

    def serve_stdio(self, stdin=None, stdout=None) -> None:
        """Bucle de servicio: lee mensajes JSON por línea de stdin y responde."""
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = self.handle(msg)
            if response is not None:
                stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                stdout.flush()
