"""Tests de la Fase 5: servidor MCP (protocolo + herramientas).

    python -m unittest discover -s tests
"""

import io
import json
import tempfile
import unittest
from pathlib import Path

from prisma.mcp import McpServer, PROTOCOL_VERSION
from prisma.embeddings import HashingEmbedder
from prisma.schema import Event
from prisma.storage import MetadataStore


def _ev(native, ts, content, title=None, source="chatgpt", thread=None, people=None):
    return Event.create(source=source, source_native_id=native, type="message",
                        timestamp=ts, content=content, title=title,
                        thread_id=thread, people=people or [])


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MetadataStore(Path(self.tmp.name) / "db.sqlite")
        # Servidor con embedder offline (hashing) para testear semántica sin Ollama.
        # Usamos el HashingEmbedder por defecto: misma "key" que get_embedder("hashing")
        # dentro del servidor, para que el espacio vectorial coincida.
        self.emb = HashingEmbedder()
        self.srv = McpServer(self.store, embedder_name="hashing")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def call(self, name, **arguments):
        resp = self.srv.handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        return resp["result"]

    def text(self, result):
        return result["content"][0]["text"]


class TestProtocol(_Base):
    def test_initialize(self):
        resp = self.srv.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize"})
        self.assertEqual(resp["result"]["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(resp["result"]["serverInfo"]["name"], "prisma")
        self.assertIn("tools", resp["result"]["capabilities"])

    def test_initialized_notification_has_no_response(self):
        self.assertIsNone(self.srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_tools_list(self):
        resp = self.srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in resp["result"]["tools"]}
        self.assertEqual(names, {"search_context", "get_timeline", "get_thread",
                                 "summarize_period", "stats"})
        for t in resp["result"]["tools"]:
            self.assertIn("inputSchema", t)  # cada tool declara su esquema

    def test_unknown_method_errors(self):
        resp = self.srv.handle({"jsonrpc": "2.0", "id": 3, "method": "no_existe"})
        self.assertEqual(resp["error"]["code"], -32601)

    def test_unknown_tool_errors(self):
        resp = self.srv.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                "params": {"name": "fantasma", "arguments": {}}})
        self.assertEqual(resp["error"]["code"], -32602)


class TestTools(_Base):
    def _seed(self):
        self.store.add_event(_ev("a", "2026-02-03T10:15:00Z",
                                 "organizar un viaje a Madrid", thread="t1",
                                 title="Viaje", people=["yo"]))
        self.store.add_event(_ev("b", "2026-02-14T21:05:00Z",
                                 "confirmamos el contrato el lunes", source="whatsapp",
                                 thread="t2", people=["Juan"]))
        self.store.add_event(_ev("c", "2026-03-01T09:00:00Z",
                                 "pedir cajas para la mudanza", source="notes", thread="t1"))
        for ev in self.store.iter_unembedded(self.emb.key):
            self.store.add_embedding(ev.id, self.emb.key, self.emb.embed(ev.content))

    def test_stats(self):
        self._seed()
        out = self.text(self.call("stats"))
        self.assertIn("whatsapp: 1", out)
        self.assertIn("TOTAL: 3", out)

    def test_timeline_filter(self):
        self._seed()
        out = self.text(self.call("get_timeline", since="2026-02-01T00:00:00Z",
                                  until="2026-02-28T23:59:59Z"))
        self.assertIn("Madrid", out)
        self.assertIn("contrato", out)
        self.assertNotIn("mudanza", out)  # marzo queda fuera

    def test_get_thread(self):
        self._seed()
        out = self.text(self.call("get_thread", thread_id="t1"))
        self.assertIn("Viaje", out)       # título
        self.assertIn("Madrid", out)
        self.assertIn("mudanza", out)     # ambos eventos del hilo t1
        self.assertIn("yo:", out)

    def test_get_thread_missing(self):
        out = self.text(self.call("get_thread", thread_id="no-existe"))
        self.assertIn("No hay conversación", out)

    def test_search_semantic(self):
        self._seed()
        out = self.text(self.call("search_context", query="contrato", limit=3))
        self.assertIn("contrato", out)

    def test_search_literal(self):
        self._seed()
        out = self.text(self.call("search_context", query="Madrid", semantic=False))
        self.assertIn("Madrid", out)

    def test_summarize_period(self):
        self._seed()
        out = self.text(self.call("summarize_period", since="2026-01-01T00:00:00Z",
                                  until="2026-12-31T00:00:00Z"))
        self.assertIn("Resume lo importante", out)
        self.assertIn("3 eventos", out)

    def test_tool_error_is_captured_not_raised(self):
        # get_thread sin argumento requerido -> KeyError capturado como isError.
        result = self.call("get_thread")
        self.assertTrue(result["isError"])
        self.assertIn("Error:", self.text(result))


class TestStdioLoop(_Base):
    def test_end_to_end_stdio(self):
        self.store.add_event(_ev("a", "2026-02-03T10:15:00Z", "hola mundo"))
        requests = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "stats", "arguments": {}}}),
        ]) + "\n"
        out = io.StringIO()
        self.srv.serve_stdio(stdin=io.StringIO(requests), stdout=out)
        lines = [json.loads(l) for l in out.getvalue().splitlines()]
        # 2 respuestas (initialize y tools/call); la notificación no responde.
        self.assertEqual([m["id"] for m in lines], [1, 2])
        self.assertIn("TOTAL: 1", lines[1]["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
