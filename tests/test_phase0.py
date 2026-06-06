"""Tests de la Fase 0: esquema, almacenamiento, importador y pipeline.

Escritos con ``unittest`` para poder ejecutarse sin instalar nada:

    python -m unittest discover -s tests
"""

import tempfile
import unittest
from pathlib import Path

from prisma.schema import Event, make_event_id
from prisma.storage import MetadataStore, ObjectStore
from prisma.storage.objects import REF_PREFIX
from prisma.importers import JsonlImporter
from prisma.ingest import Pipeline


class TestEventId(unittest.TestCase):
    def test_id_is_deterministic(self):
        a = make_event_id("chatgpt", "msg-1")
        b = make_event_id("chatgpt", "msg-1")
        self.assertEqual(a, b)

    def test_id_depends_on_source_and_native_id(self):
        self.assertNotEqual(
            make_event_id("chatgpt", "msg-1"), make_event_id("claude", "msg-1")
        )
        self.assertNotEqual(
            make_event_id("chatgpt", "msg-1"), make_event_id("chatgpt", "msg-2")
        )

    def test_create_sets_deterministic_id(self):
        ev = Event.create(
            source="claude", source_native_id="x", type="message",
            timestamp="2026-01-01T00:00:00Z", content="hola",
        )
        self.assertEqual(ev.id, make_event_id("claude", "x"))

    def test_roundtrip_dict(self):
        ev = Event.create(
            source="photos", source_native_id="img.jpg", type="photo",
            timestamp="2026-02-14T21:02:00Z", content="cena",
            people=["Juan"], location={"place": "Madrid"},
        )
        self.assertEqual(Event.from_dict(ev.to_dict()), ev)

    def test_from_dict_ignores_extra_keys(self):
        ev = Event.from_dict(
            {"id": "z", "source": "s", "type": "note",
             "timestamp": "2026-01-01T00:00:00Z", "extra_unknown": 123}
        )
        self.assertEqual(ev.id, "z")


class TestObjectStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ObjectStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_put_get_roundtrip(self):
        ref = self.store.put(b"hola mundo")
        self.assertTrue(ref.startswith(REF_PREFIX))
        self.assertEqual(self.store.get(ref), b"hola mundo")
        self.assertTrue(self.store.exists(ref))

    def test_dedup_same_content_same_ref(self):
        self.assertEqual(self.store.put(b"abc"), self.store.put(b"abc"))

    def test_missing_object_raises(self):
        with self.assertRaises(KeyError):
            self.store.get(f"{REF_PREFIX}{'0' * 64}")


class TestMetadataStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MetadataStore(Path(self.tmp.name) / "db.sqlite")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _ev(self, native, ts, source="chatgpt", **kw):
        return Event.create(
            source=source, source_native_id=native, type="message",
            timestamp=ts, **kw,
        )

    def test_add_and_get(self):
        ev = self._ev("m1", "2026-01-01T00:00:00Z", content="hola")
        self.assertTrue(self.store.add_event(ev))
        got = self.store.get_event(ev.id)
        self.assertEqual(got, ev)

    def test_dedupe_on_reinsert(self):
        ev = self._ev("m1", "2026-01-01T00:00:00Z")
        self.assertTrue(self.store.add_event(ev))
        self.assertFalse(self.store.add_event(ev))  # ya existe
        self.assertEqual(self.store.count(), 1)

    def test_counts_by_source(self):
        self.store.add_event(self._ev("a", "2026-01-01T00:00:00Z", source="chatgpt"))
        self.store.add_event(self._ev("b", "2026-01-02T00:00:00Z", source="claude"))
        self.store.add_event(self._ev("c", "2026-01-03T00:00:00Z", source="claude"))
        self.assertEqual(self.store.counts_by_source(), {"claude": 2, "chatgpt": 1})

    def test_timeline_filters_and_order(self):
        self.store.add_event(self._ev("a", "2026-03-01T00:00:00Z"))
        self.store.add_event(self._ev("b", "2026-01-01T00:00:00Z"))
        self.store.add_event(self._ev("c", "2026-02-01T00:00:00Z"))
        ts = [e.timestamp for e in self.store.timeline()]
        self.assertEqual(ts, sorted(ts))  # orden ascendente
        feb_on = list(self.store.timeline(since="2026-02-01T00:00:00Z"))
        self.assertEqual(len(feb_on), 2)

    def test_search(self):
        self.store.add_event(self._ev("a", "2026-01-01T00:00:00Z", content="contrato firmado"))
        self.store.add_event(self._ev("b", "2026-01-02T00:00:00Z", content="comprar pan"))
        res = self.store.search("contrato")
        self.assertEqual(len(res), 1)
        self.assertIn("contrato", res[0].content)

    def test_json_fields_roundtrip(self):
        ev = self._ev(
            "a", "2026-01-01T00:00:00Z",
            people=["Juan", "yo"], location={"place": "Madrid"},
            media=[{"ref": "blob://sha256:x", "mime": "image/jpeg"}],
        )
        self.store.add_event(ev)
        got = self.store.get_event(ev.id)
        self.assertEqual(got.people, ["Juan", "yo"])
        self.assertEqual(got.location, {"place": "Madrid"})
        self.assertEqual(got.media[0]["mime"], "image/jpeg")


class TestPipelineIngest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = MetadataStore(self.root / "db.sqlite")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _write_jsonl(self, lines):
        p = self.root / "data.jsonl"
        p.write_text("\n".join(lines), encoding="utf-8")
        return p

    def test_ingest_jsonl_end_to_end(self):
        path = self._write_jsonl([
            '{"source": "chatgpt", "source_native_id": "m1", "type": "message", "timestamp": "2026-02-03T10:15:00Z", "content": "viaje"}',
            '{"source": "whatsapp", "source_native_id": "w1", "type": "message", "timestamp": "2026-02-14T21:05:00Z", "content": "contrato", "people": ["Juan"]}',
        ])
        result = Pipeline(self.store).ingest(JsonlImporter(source_path=path))
        self.assertEqual(result.new, 2)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(self.store.count(), 2)

    def test_ingest_is_idempotent(self):
        path = self._write_jsonl([
            '{"source": "chatgpt", "source_native_id": "m1", "type": "message", "timestamp": "2026-02-03T10:15:00Z", "content": "hola"}',
        ])
        Pipeline(self.store).ingest(JsonlImporter(source_path=path))
        second = Pipeline(self.store).ingest(JsonlImporter(source_path=path))
        self.assertEqual(second.new, 0)
        self.assertEqual(second.skipped, 1)
        self.assertEqual(self.store.count(), 1)

    def test_ingest_skips_comments_and_blank_lines(self):
        path = self._write_jsonl([
            "# comentario",
            "",
            '{"source": "notes", "source_native_id": "n1", "type": "note", "timestamp": "2026-03-01T09:00:00Z", "content": "x"}',
        ])
        result = Pipeline(self.store).ingest(JsonlImporter(source_path=path))
        self.assertEqual(result.new, 1)


if __name__ == "__main__":
    unittest.main()
