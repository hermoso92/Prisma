"""Importador de ChatGPT.

Procesa el export oficial de ChatGPT (Ajustes → Controles de datos → Exportar).
El ZIP contiene ``conversations.json``: una lista de conversaciones, cada una con
un ``mapping`` (árbol de nodos) donde cada nodo puede llevar un ``message``.

Estrategia: recorrer el ``mapping`` de cada conversación, quedarnos con los
mensajes de ``user`` y ``assistant`` con texto, y emitir un :class:`Event` por
mensaje. ``thread_id`` = id de la conversación; ``people`` = ``["yo"]`` /
``["ChatGPT"]`` según el rol. Idempotente: el id del evento deriva del id del
mensaje, así que reimportar no duplica.

Formatos no-texto (imágenes, etc.) se anotan en ``source_meta`` para que las
fases multimodales posteriores los recojan; en Fase 1 solo extraemos texto.
"""

from __future__ import annotations

from typing import Any, Iterator

from prisma.importers.base import Importer
from prisma.importers.util import load_json_member, unix_to_iso
from prisma.schema import Event

_ROLE_PEOPLE = {"user": "yo", "assistant": "ChatGPT"}


class ChatGptImporter(Importer):
    source = "chatgpt"

    def iter_events(self) -> Iterator[Event]:
        if self.source_path is None:
            raise ValueError("ChatGptImporter requiere source_path")
        conversations = load_json_member(self.source_path, "conversations.json")
        for conv in conversations:
            yield from self._iter_conversation(conv)

    def _iter_conversation(self, conv: dict[str, Any]) -> Iterator[Event]:
        conv_id = conv.get("conversation_id") or conv.get("id") or "?"
        title = conv.get("title")
        conv_created = conv.get("create_time")
        mapping = conv.get("mapping") or {}

        # Recogemos mensajes válidos y los ordenamos cronológicamente: el árbol
        # del mapping no garantiza orden temporal de iteración.
        nodes = []
        for node in mapping.values():
            msg = node.get("message") if isinstance(node, dict) else None
            if not msg:
                continue
            parsed = self._parse_message(msg, conv_id, title, conv_created)
            if parsed is not None:
                nodes.append(parsed)
        nodes.sort(key=lambda ev: ev.timestamp)
        yield from nodes

    def _parse_message(
        self, msg: dict[str, Any], conv_id: str, title, conv_created
    ) -> Event | None:
        role = (msg.get("author") or {}).get("role")
        if role not in _ROLE_PEOPLE:
            return None  # saltamos system / tool en Fase 1

        text, nontext = self._extract_content(msg.get("content") or {})
        if not text and not nontext:
            return None

        timestamp = unix_to_iso(msg.get("create_time")) or unix_to_iso(conv_created)
        if timestamp is None:
            return None

        source_meta = {"role": role, "conversation_id": conv_id}
        if nontext:
            source_meta["nontext_parts"] = nontext

        return Event.create(
            source=self.source,
            source_native_id=msg.get("id", f"{conv_id}:{timestamp}"),
            type="message",
            timestamp=timestamp,
            title=title,
            content=text,
            people=[_ROLE_PEOPLE[role]],
            thread_id=conv_id,
            source_meta=source_meta,
        )

    @staticmethod
    def _extract_content(content: dict[str, Any]) -> tuple[str, list[Any]]:
        """Devuelve ``(texto, partes_no_texto)`` de un bloque de contenido."""
        parts = content.get("parts")
        if parts is None:
            # Algunos tipos usan 'text' directamente.
            return (content.get("text") or "").strip(), []
        texts, nontext = [], []
        for part in parts:
            if isinstance(part, str):
                if part.strip():
                    texts.append(part)
            else:
                nontext.append(part)  # dict: imagen, audio, etc.
        return "\n".join(texts).strip(), nontext
