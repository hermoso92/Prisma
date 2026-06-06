"""Tests de los importadores de Notas (texto) y Google Keep (Takeout).

    python -m unittest discover -s tests
"""

import json
import tempfile
import unittest
from pathlib import Path

from prisma.importers import NotesImporter, KeepImporter


class TestNotesImporter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_txt_and_md(self):
        (self.dir / "compra.txt").write_text("Comprar pan\ny leche", encoding="utf-8")
        (self.dir / "ideas.md").write_text("# Idea genial\nmontar una app", encoding="utf-8")
        (self.dir / "foto.jpg").write_bytes(b"no soy nota")
        events = {e.title: e for e in NotesImporter(source_path=self.dir).iter_events()}
        self.assertEqual(set(events), {"Comprar pan", "Idea genial"})
        self.assertEqual(events["Idea genial"].type, "note")
        self.assertIn("montar una app", events["Idea genial"].content)

    def test_title_falls_back_to_filename(self):
        (self.dir / "vacia.txt").write_text("   \n  ", encoding="utf-8")
        ev = next(iter(NotesImporter(source_path=self.dir).iter_events()))
        self.assertEqual(ev.title, "vacia")

    def test_deterministic_ids(self):
        (self.dir / "n.txt").write_text("hola", encoding="utf-8")
        a = list(NotesImporter(source_path=self.dir).iter_events())
        b = list(NotesImporter(source_path=self.dir).iter_events())
        self.assertEqual([e.id for e in a], [e.id for e in b])

    def test_single_file(self):
        p = self.dir / "una.md"
        p.write_text("Título\ncuerpo", encoding="utf-8")
        events = list(NotesImporter(source_path=p).iter_events())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "Título")


class TestKeepImporter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, note):
        (self.dir / name).write_text(json.dumps(note), encoding="utf-8")

    def test_text_note(self):
        self._write("n1.json", {
            "title": "Mudanza",
            "textContent": "pedir cajas",
            "userEditedTimestampUsec": 1740825600000000,  # 2025-03-01T...
            "labels": [{"name": "casa"}],
        })
        ev = next(iter(KeepImporter(source_path=self.dir).iter_events()))
        self.assertEqual(ev.title, "Mudanza")
        self.assertEqual(ev.content, "pedir cajas")
        self.assertEqual(ev.type, "note")
        self.assertEqual(ev.source, "keep")
        self.assertEqual(ev.source_meta["labels"], ["casa"])
        self.assertTrue(ev.timestamp.startswith("2025-03-01"))

    def test_list_note_with_checkboxes(self):
        self._write("n2.json", {
            "title": "Compra",
            "listContent": [
                {"text": "pan", "isChecked": True},
                {"text": "leche", "isChecked": False},
            ],
            "createdTimestampUsec": 1700000000000000,
        })
        ev = next(iter(KeepImporter(source_path=self.dir).iter_events()))
        self.assertIn("[x] pan", ev.content)
        self.assertIn("[ ] leche", ev.content)

    def test_trashed_is_skipped(self):
        self._write("trash.json", {
            "textContent": "borrame", "isTrashed": True,
            "userEditedTimestampUsec": 1700000000000000,
        })
        self.assertEqual(list(KeepImporter(source_path=self.dir).iter_events()), [])

    def test_ignores_non_keep_json(self):
        self._write("otro.json", {"foo": "bar"})
        self.assertEqual(list(KeepImporter(source_path=self.dir).iter_events()), [])


if __name__ == "__main__":
    unittest.main()
