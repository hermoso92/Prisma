"""Tests del caso 'fotos solo yo → collage/vídeo'.

Cubren: regla is_only_me, analizador de atributos con stubs, consulta por
atributos en el store, render con degradación elegante, y las tools MCP.
No requieren YOLO/face_recognition/Pillow/ffmpeg reales.

    python -m unittest discover -s tests
"""

import tempfile
import unittest
from pathlib import Path

from prisma.analysis.attrs import AttributesAnalyzer
from prisma.analysis.base import Analyzer, ME_LABEL
from prisma.analysis.detect import Detector
from prisma.analysis.faces import FaceMatcher
from prisma.ingest import Pipeline
from prisma.importers import PhotosImporter
from prisma.mcp import McpServer
from prisma.render import RenderError, make_collage, make_video
from prisma.schema import Event
from prisma.storage import MetadataStore, ObjectStore


# --- Stubs deterministas ----------------------------------------------------

class StubDetector(Detector):
    def __init__(self, people=1, animals=None):
        self.people, self.animals = people, animals or []
    def detect_image(self, data, suffix):
        return {"people_count": self.people, "animals": list(self.animals), "objects": []}


class StubMatcher(FaceMatcher):
    def __init__(self, names):
        self.names = names
    def enroll(self, name, image_paths):
        return len(image_paths)
    def identify(self, data, suffix):
        return list(self.names)


def _attrs(people=1, animals=None, faces=("me",)):
    a = AttributesAnalyzer(detector=StubDetector(people, animals),
                           matcher=StubMatcher(list(faces)))
    return a


# --- Regla is_only_me -------------------------------------------------------

class TestOnlyMeRule(unittest.TestCase):
    def test_only_me_true(self):
        d = _attrs(people=1, animals=[], faces=["me"]).analyze(
            data=b"x", mime="image/jpeg", type="photo")
        self.assertTrue(d["is_only_me"])
        self.assertEqual(d["people_count"], 1)

    def test_other_person_breaks_only_me(self):
        d = _attrs(people=2, faces=["me"]).analyze(data=b"x", mime="image/jpeg", type="photo")
        self.assertFalse(d["is_only_me"])

    def test_cat_breaks_only_me(self):
        d = _attrs(people=1, animals=["cat"], faces=["me"]).analyze(
            data=b"x", mime="image/jpeg", type="photo")
        self.assertFalse(d["is_only_me"])
        self.assertEqual(d["animals"], ["cat"])

    def test_not_me_breaks_only_me(self):
        d = _attrs(people=1, faces=[]).analyze(data=b"x", mime="image/jpeg", type="photo")
        self.assertFalse(d["is_only_me"])

    def test_no_face_data_means_no_flag(self):
        # Analizador que solo detecta, sin reconocimiento → no afirmamos is_only_me.
        class OnlyDetect(Analyzer):
            name = "od"
            def detect(self, *, data, mime, type):
                return {"people_count": 1, "animals": []}
        d = OnlyDetect().analyze(data=b"x", mime="image/jpeg", type="photo")
        self.assertNotIn("is_only_me", d)


# --- Consulta por atributos en el store -------------------------------------

class TestPhotosWhere(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MetadataStore(Path(self.tmp.name) / "db.sqlite")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _photo(self, nid, derived):
        ev = Event.create(source="photos", source_native_id=nid, type="photo",
                          timestamp="2026-02-01T00:00:00Z", media=[{"ref": f"blob://sha256:{nid}"}])
        ev.derived = derived
        self.store.add_event(ev)
        return ev

    def test_filters(self):
        self._photo("a", {"people_count": 1, "animals": [], "is_only_me": True})
        self._photo("b", {"people_count": 2, "animals": [], "is_only_me": False})
        self._photo("c", {"people_count": 1, "animals": ["cat"], "is_only_me": False})
        only_me = self.store.photos_where(only_me=True)
        self.assertEqual([e.source_meta.get("filename", e.id) for e in only_me], [only_me[0].id])
        self.assertEqual(len(only_me), 1)
        self.assertEqual(len(self.store.photos_where(no_animals=True)), 2)  # a y b
        self.assertEqual(len(self.store.photos_where(max_people=1)), 2)     # a y c


# --- Pipeline e2e con stubs -------------------------------------------------

class TestPipelineAttrs(unittest.TestCase):
    def test_ingest_photo_fills_is_only_me_and_query(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        media = root / "media"; media.mkdir()
        (media / "yo.jpg").write_bytes(b"jpegfake")
        objects = ObjectStore(root / "objects")
        store = MetadataStore(root / "db.sqlite"); self.addCleanup(store.close)
        analyzer = _attrs(people=1, animals=[], faces=["me"])
        res = Pipeline(store, objects, analyzer).ingest(
            PhotosImporter(source_path=media, objects=objects))
        self.assertEqual(res.analyzed, 1)
        self.assertEqual(len(store.photos_where(only_me=True)), 1)


# --- Render: degradación elegante (sin Pillow/ffmpeg en el entorno) ---------

class TestRenderGraceful(unittest.TestCase):
    def test_empty_raises_rendererror(self):
        with self.assertRaises(RenderError):
            make_collage([], "/tmp/x.jpg")
        with self.assertRaises(RenderError):
            make_video([], "/tmp/x.mp4")

    def test_missing_dependency_is_rendererror_not_crash(self):
        # En este entorno no hay Pillow ni ffmpeg → RenderError con mensaje claro.
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        with self.assertRaises(RenderError):
            make_collage([b"fake"], Path(tmp.name) / "c.jpg")
        with self.assertRaises(RenderError):
            make_video([b"fake"], Path(tmp.name) / "v.mp4")


# --- MCP tools de fotos -----------------------------------------------------

class TestMcpPhotoTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = MetadataStore(self.root / "db.sqlite")
        self.objects = ObjectStore(self.root / "objects")
        ref = self.objects.put(b"imagen")
        ev = Event.create(source="photos", source_native_id="a", type="photo",
                          timestamp="2026-02-01T00:00:00Z",
                          media=[{"ref": ref, "mime": "image/jpeg"}])
        ev.derived = {"people_count": 1, "animals": [], "is_only_me": True}
        self.store.add_event(ev)
        self.srv = McpServer(self.store, objects=self.objects, render_dir=self.root / "render")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _call(self, name, **args):
        r = self.srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": name, "arguments": args}})
        return r["result"]

    def test_find_photos_lists_only_me(self):
        out = self._call("find_photos", only_me=True)
        self.assertIn("solo-yo", out["content"][0]["text"])

    def test_make_collage_degrades_gracefully(self):
        # Sin Pillow → isError con mensaje, no excepción.
        res = self._call("make_collage", only_me=True)
        self.assertTrue(res["isError"])
        self.assertIn("Pillow", res["content"][0]["text"])

    def test_tools_listed(self):
        resp = self.srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in resp["result"]["tools"]}
        self.assertIn("find_photos", names)
        self.assertIn("make_collage", names)
        self.assertIn("make_video", names)


if __name__ == "__main__":
    unittest.main()
