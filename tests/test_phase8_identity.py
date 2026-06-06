"""Tests de la resolución de identidades entre fuentes (pasada 2: CEREBRO).

    python -m unittest discover -s tests
"""

import tempfile
import unittest
from pathlib import Path

from prisma.identity import IdentityMap
from prisma.schema import Event
from prisma.storage import MetadataStore


def _ev(nid, ts, people, source="whatsapp"):
    return Event.create(source=source, source_native_id=nid, type="message",
                        timestamp=ts, content="hola", people=people)


class TestIdentityMap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "identities.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolve_default_is_identity(self):
        idmap = IdentityMap(self.path)
        self.assertEqual(idmap.resolve("Juan"), "Juan")

    def test_add_and_resolve_aliases(self):
        idmap = IdentityMap(self.path)
        idmap.add("Juan Pérez", "Juan", "+34600111222")
        self.assertEqual(idmap.resolve("Juan"), "Juan Pérez")
        self.assertEqual(idmap.resolve("+34600111222"), "Juan Pérez")
        self.assertEqual(idmap.resolve("juan"), "Juan Pérez")  # case-insensitive
        self.assertEqual(idmap.resolve("Otro"), "Otro")

    def test_persists_across_instances(self):
        IdentityMap(self.path).add("Ana", "Anita")
        self.assertEqual(IdentityMap(self.path).resolve("Anita"), "Ana")


class TestPeopleAggregation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MetadataStore(Path(self.tmp.name) / "db.sqlite")
        self.idmap = IdentityMap(Path(self.tmp.name) / "id.json")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _seed(self):
        self.store.add_event(_ev("a", "2026-01-01T00:00:00Z", ["Juan"], source="whatsapp"))
        self.store.add_event(_ev("b", "2026-01-02T00:00:00Z", ["Juan Pérez"], source="notes"))
        self.store.add_event(_ev("c", "2026-01-03T00:00:00Z", ["Ana", "yo"], source="chatgpt"))

    def test_counts_without_map(self):
        self._seed()
        counts = self.store.people_counts()
        self.assertEqual(counts["Juan"], 1)
        self.assertEqual(counts["Juan Pérez"], 1)  # sin unificar, separados

    def test_counts_with_identity_map(self):
        self._seed()
        self.idmap.add("Juan Pérez", "Juan")
        counts = self.store.people_counts(resolve=self.idmap.resolve)
        self.assertEqual(counts["Juan Pérez"], 2)  # unificados
        self.assertNotIn("Juan", counts)

    def test_events_by_person_crosses_sources(self):
        self._seed()
        self.idmap.add("Juan Pérez", "Juan")
        evs = self.store.events_by_person("Juan", resolve=self.idmap.resolve)
        # Encuentra ambos (whatsapp + notes) aunque preguntemos por el alias.
        self.assertEqual({e.source for e in evs}, {"whatsapp", "notes"})
        self.assertEqual(len(evs), 2)


if __name__ == "__main__":
    unittest.main()
