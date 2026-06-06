"""Importador de chats de WhatsApp (export «Exportar chat»).

WhatsApp no tiene API personal: la vía oficial es el export manual, que produce
un ``_chat.txt`` (y, opcionalmente, los ficheros de medios). Este importador
parsea ese .txt de forma robusta, soportando los dos formatos habituales:

- iOS:      ``[14/2/26, 21:05:32] Juan: hola``
- Android:  ``14/2/26, 21:05 - Juan: hola``

Maneja mensajes multilínea (las líneas sin cabecera de fecha pertenecen al
mensaje anterior), mensajes de sistema (sin remitente) y marcadores de medios
(``<adjunto: IMG-0001.jpg>``, ``IMG-0001.jpg (archivo adjunto)``, ``<Media omitted>``).

El nombre del chat (``thread_id``) se toma del argumento ``chat_name`` o del
nombre del fichero. Con ``me`` se indica qué remitente eres tú, para etiquetarte
como «yo» en ``people``.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from prisma.importers.base import Importer
from prisma.schema import Event, make_event_id

# Cabecera de línea: captura fecha, hora y "resto" (remitente: texto | sistema).
# Acepta corchetes (iOS) o "fecha, hora - " (Android), con separadores / . - .
_LINE_RE = re.compile(
    r"^\[?\s*"
    r"(?P<date>\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4})"          # 14/2/26 o 2026-02-14
    r"[,\s]+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?\s?m\.?)?)"  # 21:05[:32] [a.m.]
    r"\s*\]?\s*[-–]?\s*"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)

_MEDIA_MARKERS = (
    "<adjunto:", "(archivo adjunto)", "<attached:", "(file attached)",
    "<media omitted>", "<multimedia omitido>", "imagen omitida", "audio omitido",
)


class WhatsAppImporter(Importer):
    source = "whatsapp"

    def __init__(self, *args, chat_name: Optional[str] = None,
                 me: Optional[str] = None, dayfirst: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.chat_name = chat_name
        self.me = me
        self.dayfirst = dayfirst

    def iter_events(self) -> Iterator[Event]:
        if self.source_path is None:
            raise ValueError("WhatsAppImporter requiere source_path (el _chat.txt)")
        path = Path(self.source_path)
        chat = self.chat_name or path.stem.replace("_chat", "").strip() or "whatsapp"

        records = self._parse_lines(path)
        for idx, (timestamp, sender, text) in enumerate(records):
            yield self._build_event(chat, idx, timestamp, sender, text)

    def _parse_lines(self, path: Path) -> list[tuple[str, Optional[str], str]]:
        """Agrupa líneas en (timestamp_iso, remitente|None, texto)."""
        records: list[tuple[str, Optional[str], str]] = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.replace("‎", "").rstrip("\n")  # quita marca LTR de iOS
            m = _LINE_RE.match(line)
            if not m:
                # Continuación del mensaje anterior (multilínea).
                if records:
                    ts, sender, text = records[-1]
                    records[-1] = (ts, sender, f"{text}\n{line}".strip())
                continue
            ts = self._to_iso(m.group("date"), m.group("time"))
            if ts is None:
                continue
            rest = m.group("rest")
            sender, text = self._split_sender(rest)
            records.append((ts, sender, text))
        return records

    @staticmethod
    def _split_sender(rest: str) -> tuple[Optional[str], str]:
        # "Remitente: mensaje" → (remitente, mensaje). Sin ':' → mensaje de sistema.
        if ": " in rest:
            sender, text = rest.split(": ", 1)
            # Evita partir frases de sistema con ':' largo (heurística simple).
            if len(sender) <= 60 and "\n" not in sender:
                return sender.strip(), text.strip()
        return None, rest.strip()

    def _build_event(self, chat: str, idx: int, timestamp: str,
                     sender: Optional[str], text: str) -> Event:
        is_system = sender is None
        people: list[str] = []
        if sender:
            people.append("yo" if self.me and sender == self.me else sender)

        source_meta = {"chat": chat}
        if sender:
            source_meta["sender"] = sender
        if any(mk in text.lower() for mk in _MEDIA_MARKERS):
            source_meta["has_media_marker"] = True

        return Event(
            id=make_event_id(self.source, f"{chat}:{idx}"),
            source=self.source,
            type="note" if is_system else "message",
            timestamp=timestamp,
            content=text,
            people=people,
            thread_id=chat,
            source_meta=source_meta,
        )

    def _to_iso(self, date: str, time: str) -> Optional[str]:
        parts = re.split(r"[/.\-]", date)
        try:
            a, b, c = (int(p) for p in parts)
        except (ValueError, TypeError):
            return None
        # Año de 4 cifras al principio → ISO (YYYY-MM-DD); si no, day/month-first.
        if len(parts[0]) == 4:
            year, month, day = a, b, c
        else:
            day, month = (a, b) if self.dayfirst else (b, a)
            year = c + 2000 if c < 100 else c

        t = time.strip().lower().replace(".", "").replace(" ", "")
        ampm = ""
        if t.endswith("am") or t.endswith("pm"):
            ampm, t = t[-2:], t[:-2]
        hms = [int(x) for x in t.split(":")]
        hour, minute = hms[0], hms[1]
        second = hms[2] if len(hms) > 2 else 0
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        try:
            dt = datetime(year, month, day, hour, minute, second)
        except ValueError:
            return None
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
