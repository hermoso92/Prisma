"""Tests de la Fase 4: embeddings y búsqueda semántica.

    python -m unittest discover -s tests
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import prisma.cli as cli
from prisma.embeddings import HashingEmbedder, OllamaEmbedder, get_embedder
from prisma.schema import Event
from prisma.storage import MetadataStore


def _ev(native, ts, content, title=None, source="chatgpt"):
    return Event.create(source=source, source_native_id=native, type="message",
                        timestamp=ts, content=content, title=title)


class TestHashingEmbedder(unittest.TestCase):
    def test_deterministic_and_normalized(self):
        e = HashingEmbedder(dim=64)
        v1 = e.embed("hola mundo")
        v2 = e.embed("hola mundo")
        self.assertEqual(v1, v2)
        self.assertEqual(len(v1), 64)
        norm = sum(x * x for x in v1) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_empty_text(self):
        self.assertEqual(HashingEmbedder(dim=8).embed(""), [0.0] * 8)

    def test_key_includes_model(self):
        self.assertEqual(HashingEmbedder(dim=32).key, "hashing:hashing-32")


class TestOllamaEmbedderMock(unittest.TestCase):
    def test_embed_uses_http(self):
        e = OllamaEmbedder()
        e._embed = lambda text: [0.1, 0.2, 0.3]
        self.assertEqual(e.embed("x"), [0.1, 0.2, 0.3])

    def test_registry(self):
        self.assertIsInstance(get_embedder("ollama"), OllamaEmbedder)
        self.assertIsInstance(get_embedder("hashing"), HashingEmbedder)
        with self.assertRaises(KeyError):
            get_embedder("no-existe")


class TestVectorStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MetadataStore(Path(self.tmp.name) / "db.sqlite")
        self.emb = HashingEmbedder(dim=128)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _index_all(self):
        for ev in self.store.iter_unembedded(self.emb.key):
            self.store.add_embedding(ev.id, self.emb.key, self.emb.embed(ev.content))

    def test_iter_unembedded_skips_empty_and_already_indexed(self):
        a = _ev("a", "2026-01-01T00:00:00Z", "contrato de alquiler firmado")
        b = _ev("b", "2026-01-02T00:00:00Z", "")  # sin texto → se ignora
        self.store.add_event(a)
        self.store.add_event(b)
        pending = list(self.store.iter_unembedded(self.emb.key))
        self.assertEqual([e.id for e in pending], [a.id])
        self._index_all()
        self.assertEqual(list(self.store.iter_unembedded(self.emb.key)), [])
        self.assertEqual(self.store.count_embeddings(self.emb.key), 1)

    def test_vector_search_ranks_by_similarity(self):
        self.store.add_event(_ev("a", "2026-01-01T00:00:00Z",
                                 "firmamos el contrato de alquiler del piso"))
        self.store.add_event(_ev("b", "2026-01-02T00:00:00Z",
                                 "receta de tortilla de patatas con cebolla"))
        self.store.add_event(_ev("c", "2026-01-03T00:00:00Z",
                                 "el contrato laboral incluye cláusulas"))
        self._index_all()
        results = self.store.vector_search(self.emb.embed("contrato"), self.emb.key, limit=3)
        self.assertEqual(len(results), 3)
        # Los dos de "contrato" deben puntuar por encima de la receta.
        top_two = {ev.content for ev, _ in results[:2]}
        self.assertTrue(any("contrato" in c for c in top_two))
        self.assertGreaterEqual(results[0][1], results[-1][1])  # orden desc
        self.assertIn("tortilla", results[-1][0].content)  # la receta, la última

    def test_separate_spaces_do_not_mix(self):
        self.store.add_event(_ev("a", "2026-01-01T00:00:00Z", "hola"))
        self._index_all()  # espacio hashing-128
        # Otro espacio (otra dim) está vacío.
        other = HashingEmbedder(dim=64)
        self.assertEqual(self.store.count_embeddings(other.key), 0)
        self.assertEqual(
            self.store.vector_search(other.embed("hola"), other.key, limit=5), []
        )


class TestOverview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MetadataStore(Path(self.tmp.name) / "db.sqlite")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_overview_aggregates(self):
        self.store.add_event(_ev("a", "2026-01-01T00:00:00Z", "hola", source="chatgpt"))
        p = Event.create(source="photos", source_native_id="p", type="photo",
                         timestamp="2026-03-01T00:00:00Z", content="una playa")
        p.derived = {"caption": "una playa", "is_only_me": True}
        self.store.add_event(p)
        self.store.add_embedding("a:nope", "sp", [0.1])  # no cuenta como evento real distinto
        ov = self.store.overview()
        self.assertEqual(ov["total"], 2)
        self.assertEqual(ov["photos"], 1)
        self.assertEqual(ov["captions"], 1)
        self.assertEqual(ov["only_me"], 1)
        self.assertEqual(ov["span"], ("2026-01-01T00:00:00Z", "2026-03-01T00:00:00Z"))
        self.assertEqual(ov["by_source"]["chatgpt"], 1)


class TestSearchSemanticErrorHandling(unittest.TestCase):
    """Si el embedder falla (p. ej. Ollama caído), mensaje claro, no traceback."""

    def test_friendly_error_when_embed_fails(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class Boom:
            key = "x:y"
            def embed(self, q):
                raise OSError("connection refused")

        orig = cli.get_embedder
        cli.get_embedder = lambda name: Boom()
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = cli.main(["--home", tmp.name, "search", "hola", "--semantic"])
        finally:
            cli.get_embedder = orig
        self.assertEqual(rc, 1)
        self.assertIn("Ollama", err.getvalue())


if __name__ == "__main__":
    unittest.main()
