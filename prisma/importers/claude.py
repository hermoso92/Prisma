"""Importador de Claude (Anthropic).

Procesa el export oficial de Claude (Ajustes → Privacidad → Exportar datos). El
ZIP contiene ``conversations.json``: una lista de conversaciones, cada una con
``chat_messages``. Cada mensaje tiene ``sender`` (``human``/``assistant``),
``text`` y/o una lista ``content`` de bloques, más ``created_at`` (ISO).

Emitimos un :class:`Event` por mensaje. ``thread_id`` = uuid de la conversación;
``people`` = ``["yo"]`` / ``["Claude"]``. Si el export trae proyectos, el id del
proyecto se anota en ``source_meta``. Idempotente vía el uuid del mensaje.
"""

from __future__ import annotations

from typing import Any, Iterator

from prisma.importers.base import Importer
from prisma.importers.util import load_json_member, normalize_iso
from prisma.schema import Event

_SENDER_PEOPLE = {"human": "yo", "assistant": "Claude"}


class ClaudeImporter(Importer):
    source = "claude"

    def iter_events(self) -> Iterator[Event]:
        if self.source_path is None:
            raise ValueError("ClaudeImporter requiere source_path")
        conversations = load_json_member(self.source_path, "conversations.json")
        for conv in conversations:
            yield from self._iter_conversation(conv)

    def _iter_conversation(self, conv: dict[str, Any]) -> Iterator[Event]:
        conv_id = conv.get("uuid") or conv.get("id") or "?"
        title = conv.get("name") or conv.get("title")
        project = conv.get("project_uuid") or (conv.get("project") or {}).get("uuid")
        conv_created = conv.get("created_at")

        for msg in conv.get("chat_messages") or conv.get("messages") or []:
            ev = self._parse_message(msg, conv_id, title, project, conv_created)
            if ev is not None:
                yield ev

    def _parse_message(
        self, msg: dict[str, Any], conv_id: str, title, project, conv_created
    ) -> Event | None:
        sender = msg.get("sender") or msg.get("role")
        if sender not in _SENDER_PEOPLE:
            return None

        text = self._extract_text(msg)
        attachments = msg.get("attachments") or []
        files = msg.get("files") or []
        if not text and not attachments and not files:
            return None

        timestamp = normalize_iso(msg.get("created_at")) or normalize_iso(conv_created)
        if timestamp is None:
            return None

        source_meta: dict[str, Any] = {"sender": sender, "conversation_id": conv_id}
        if project:
            source_meta["project_uuid"] = project
        if attachments:
            source_meta["attachments"] = attachments
        if files:
            source_meta["files"] = files

        return Event.create(
            source=self.source,
            source_native_id=msg.get("uuid") or msg.get("id") or f"{conv_id}:{timestamp}",
            type="message",
            timestamp=timestamp,
            title=title,
            content=text,
            people=[_SENDER_PEOPLE[sender]],
            thread_id=conv_id,
            source_meta=source_meta,
        )

    @staticmethod
    def _extract_text(msg: dict[str, Any]) -> str:
        """Texto del mensaje: campo ``text`` o concatenación de bloques ``content``."""
        direct = (msg.get("text") or "").strip()
        if direct:
            return direct
        parts = []
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                t = (block.get("text") or "").strip()
                if t:
                    parts.append(t)
            elif isinstance(block, str) and block.strip():
                parts.append(block)
        return "\n".join(parts).strip()
