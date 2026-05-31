"""Tests de los importadores de ChatGPT y Claude (Fase 1).

Usan datos sintéticos que imitan la estructura de cada export oficial, y cubren
la lectura desde JSON directo y desde ZIP (que es como llegan en realidad).

    python -m unittest discover -s tests
"""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from prisma.importers import ChatGptImporter, ClaudeImporter
from prisma.importers.util import normalize_iso, unix_to_iso


# --- Datos sintéticos -------------------------------------------------------

CHATGPT_EXPORT = [
    {
        "id": "conv-1",
        "title": "Planificar viaje",
        "create_time": 1738577700.0,  # 2025-02-03T10:15:00Z
        "mapping": {
            "root": {"id": "root", "message": None, "parent": None, "children": ["n1"]},
            "n1": {
                "id": "n1",
                "message": {
                    "id": "msg-user-1",
                    "author": {"role": "user"},
                    "create_time": 1738577700.0,
                    "content": {"content_type": "text", "parts": ["Quiero ir a Madrid"]},
                },
                "parent": "root",
                "children": ["n2"],
            },
            "n2": {
                "id": "n2",
                "message": {
                    "id": "msg-asst-1",
                    "author": {"role": "assistant"},
                    "create_time": 1738577760.0,  # un minuto después
                    "content": {"content_type": "text", "parts": ["Buena idea, en febrero."]},
                },
                "parent": "n1",
                "children": [],
            },
            # nodo de sistema (debe ignorarse)
            "n0": {
                "id": "n0",
                "message": {
                    "id": "msg-sys",
                    "author": {"role": "system"},
                    "create_time": 1738577600.0,
                    "content": {"content_type": "text", "parts": [""]},
                },
                "parent": "root",
                "children": [],
            },
        },
    }
]

CLAUDE_EXPORT = [
    {
        "uuid": "conv-claude-1",
        "name": "Proyecto contrato",
        "created_at": "2026-02-10T18:40:00.000000Z",
        "project_uuid": "proj-7",
        "chat_messages": [
            {
                "uuid": "cm-1",
                "sender": "human",
                "created_at": "2026-02-10T18:40:00Z",
                "text": "Revisa el contrato",
                "content": [{"type": "text", "text": "Revisa el contrato"}],
                "attachments": [],
                "files": [],
            },
            {
                "uuid": "cm-2",
                "sender": "assistant",
                "created_at": "2026-02-10T18:41:30Z",
                "text": "",
                "content": [{"type": "text", "text": "Cláusulas revisadas."}],
            },
        ],
    }
]


def _write_json(dirpath: Path, payload) -> Path:
    p = dirpath / "conversations.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _write_zip(dirpath: Path, payload, inner="export/conversations.json") -> Path:
    p = dirpath / "export.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(inner, json.dumps(payload))
    return p


# --- Tests ------------------------------------------------------------------

class TestTimestampUtils(unittest.TestCase):
    def test_unix_to_iso(self):
        self.assertEqual(unix_to_iso(1738577700.0), "2025-02-03T10:15:00Z")
        self.assertIsNone(unix_to_iso(None))

    def test_normalize_iso_variants(self):
        self.assertEqual(normalize_iso("2026-02-10T18:40:00Z"), "2026-02-10T18:40:00Z")
        self.assertEqual(normalize_iso("2026-02-10T18:40:00.000000Z"), "2026-02-10T18:40:00Z")
        self.assertEqual(normalize_iso("2026-02-10T20:40:00+02:00"), "2026-02-10T18:40:00Z")
        self.assertIsNone(normalize_iso(""))


class TestChatGptImporter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_extracts_user_and_assistant_only(self):
        events = list(ChatGptImporter(_write_json(self.dir, CHATGPT_EXPORT)).iter_events())
        self.assertEqual(len(events), 2)  # system ignorado
        self.assertEqual([e.people[0] for e in events], ["yo", "ChatGPT"])

    def test_chronological_order(self):
        events = list(ChatGptImporter(_write_json(self.dir, CHATGPT_EXPORT)).iter_events())
        self.assertEqual([e.timestamp for e in events],
                         ["2025-02-03T10:15:00Z", "2025-02-03T10:16:00Z"])

    def test_thread_and_content(self):
        events = list(ChatGptImporter(_write_json(self.dir, CHATGPT_EXPORT)).iter_events())
        self.assertTrue(all(e.thread_id == "conv-1" for e in events))
        self.assertEqual(events[0].content, "Quiero ir a Madrid")
        self.assertEqual(events[0].title, "Planificar viaje")

    def test_reads_from_zip(self):
        events = list(ChatGptImporter(_write_zip(self.dir, CHATGPT_EXPORT)).iter_events())
        self.assertEqual(len(events), 2)

    def test_deterministic_ids(self):
        a = list(ChatGptImporter(_write_json(self.dir, CHATGPT_EXPORT)).iter_events())
        b = list(ChatGptImporter(_write_json(self.dir, CHATGPT_EXPORT)).iter_events())
        self.assertEqual([e.id for e in a], [e.id for e in b])


class TestClaudeImporter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_extracts_messages(self):
        events = list(ClaudeImporter(_write_json(self.dir, CLAUDE_EXPORT)).iter_events())
        self.assertEqual(len(events), 2)
        self.assertEqual([e.people[0] for e in events], ["yo", "Claude"])

    def test_content_fallback_to_blocks(self):
        events = list(ClaudeImporter(_write_json(self.dir, CLAUDE_EXPORT)).iter_events())
        # El segundo mensaje tiene text="" y cae a los bloques content.
        self.assertEqual(events[1].content, "Cláusulas revisadas.")

    def test_project_in_source_meta(self):
        events = list(ClaudeImporter(_write_json(self.dir, CLAUDE_EXPORT)).iter_events())
        self.assertEqual(events[0].source_meta["project_uuid"], "proj-7")
        self.assertEqual(events[0].thread_id, "conv-claude-1")

    def test_timestamps_normalized(self):
        events = list(ClaudeImporter(_write_json(self.dir, CLAUDE_EXPORT)).iter_events())
        self.assertEqual(events[0].timestamp, "2026-02-10T18:40:00Z")

    def test_reads_from_zip(self):
        events = list(ClaudeImporter(_write_zip(self.dir, CLAUDE_EXPORT)).iter_events())
        self.assertEqual(len(events), 2)


if __name__ == "__main__":
    unittest.main()
