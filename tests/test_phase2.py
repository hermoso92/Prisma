"""Tests de la Fase 2: análisis enchufable, EXIF, importador de fotos y pipeline.

    python -m unittest discover -s tests
"""

import json
import struct
import tempfile
import unittest
from pathlib import Path

from prisma.analysis import NullAnalyzer, get_analyzer
from prisma.analysis.base import Analyzer
from prisma.analysis.exif import parse_exif
from prisma.importers import PhotosImporter
from prisma.ingest import Pipeline
from prisma.storage import MetadataStore, ObjectStore


class TestAnalyzerRegistry(unittest.TestCase):
    def test_null_is_registered_and_default_like(self):
        a = get_analyzer("null")
        self.assertIsInstance(a, NullAnalyzer)
        self.assertEqual(a.analyze(data=b"x", mime="image/jpeg", type="photo"), {})

    def test_unknown_analyzer_raises(self):
        with self.assertRaises(KeyError):
            get_analyzer("no-existe")

    def test_custom_analyzer_orchestration(self):
        class FakeVision(Analyzer):
            name = "fake"
            def caption(self, *, data, mime, type):
                return "una playa al atardecer"
            def transcribe(self, *, data, mime, type):
                return "hola que tal"
        d = FakeVision().analyze(data=b"x", mime="image/jpeg", type="photo")
        self.assertEqual(d["caption"], "una playa al atardecer")
        self.assertNotIn("transcript", d)  # foto no transcribe
        self.assertEqual(d["analyzer"], "fake")
        dv = FakeVision().analyze(data=b"x", mime="video/mp4", type="video")
        self.assertEqual(dv["transcript"], "hola que tal")


class TestExifParser(unittest.TestCase):
    def test_no_exif_returns_empty(self):
        self.assertEqual(parse_exif(b"not a jpeg"), {"datetime": None, "gps": None})

    def test_parses_datetime_and_gps(self):
        blob = build_exif_blob()
        res = parse_exif(blob)
        self.assertEqual(res["datetime"], "2026:02:14 21:02:00")
        self.assertEqual(res["gps"], (40.416667, -3.7))  # 40°25', -3°42' (W)


class TestPhotosImporter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.media = self.dir / "media"
        self.media.mkdir()
        self.objects = ObjectStore(self.dir / "objects")

    def tearDown(self):
        self.tmp.cleanup()

    def _importer(self):
        return PhotosImporter(source_path=self.media, objects=self.objects)

    def test_skips_non_media(self):
        (self.media / "foto.jpg").write_bytes(b"\xff\xd8\xff\xe0jpegdata")
        (self.media / "notas.txt").write_text("hola")
        events = list(self._importer().iter_events())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "photo")

    def test_stores_binary_and_sets_media_ref(self):
        (self.media / "foto.jpg").write_bytes(b"binario-de-imagen")
        ev = next(iter(self._importer().iter_events()))
        ref = ev.media[0]["ref"]
        self.assertTrue(self.objects.exists(ref))
        self.assertEqual(self.objects.get(ref), b"binario-de-imagen")

    def test_takeout_sidecar_timestamp_and_gps(self):
        (self.media / "foto.jpg").write_bytes(b"img")
        (self.media / "foto.jpg.json").write_text(json.dumps({
            "photoTakenTime": {"timestamp": "1739566920"},  # 2025-02-14T21:02:00Z
            "geoData": {"latitude": 40.4168, "longitude": -3.7038},
        }))
        ev = next(iter(self._importer().iter_events()))
        self.assertEqual(ev.timestamp, "2025-02-14T21:02:00Z")
        self.assertEqual(ev.location, {"lat": 40.4168, "lon": -3.7038})
        self.assertTrue(ev.source_meta["sidecar"])

    def test_video_and_audio_types(self):
        (self.media / "v.mp4").write_bytes(b"v")
        (self.media / "a.m4a").write_bytes(b"a")
        types = sorted(e.type for e in self._importer().iter_events())
        self.assertEqual(types, ["audio", "video"])

    def test_dedup_same_binary(self):
        (self.media / "a.jpg").write_bytes(b"same")
        (self.media / "b.jpg").write_bytes(b"same")
        ids = [e.id for e in self._importer().iter_events()]
        self.assertEqual(ids[0], ids[1])  # mismo binario → mismo id


class TestPipelineWithAnalyzer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.media = self.dir / "media"; self.media.mkdir()
        self.objects = ObjectStore(self.dir / "objects")
        self.store = MetadataStore(self.dir / "db.sqlite")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_caption_becomes_searchable_content(self):
        class FakeVision(Analyzer):
            name = "fake"
            def caption(self, *, data, mime, type):
                return "playa al atardecer con dos personas"
        (self.media / "foto.jpg").write_bytes(b"img")
        importer = PhotosImporter(source_path=self.media, objects=self.objects)
        result = Pipeline(self.store, self.objects, FakeVision()).ingest(importer)
        self.assertEqual(result.new, 1)
        self.assertEqual(result.analyzed, 1)
        hits = self.store.search("atardecer")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].derived["caption"], "playa al atardecer con dos personas")

    def test_null_analyzer_leaves_content_empty(self):
        (self.media / "foto.jpg").write_bytes(b"img")
        importer = PhotosImporter(source_path=self.media, objects=self.objects)
        result = Pipeline(self.store, self.objects, NullAnalyzer()).ingest(importer)
        self.assertEqual(result.analyzed, 0)
        self.assertEqual(self.store.search("atardecer"), [])


# --- Builder real del EXIF (definido tras las clases para legibilidad) --------

def build_exif_blob() -> bytes:
    """EXIF little-endian con DateTimeOriginal (SubIFD) y GPS (lat 40°25', lon 3°42'W)."""
    bo = "<"
    dt = b"2026:02:14 21:02:00\x00"  # 20 bytes

    def entry(tag, typ, count, value):
        return struct.pack(bo + "HHII", tag, typ, count, value)

    # Offsets (relativos al inicio del TIFF):
    #   8   IFD0
    #   38  SubIFD
    #   56  GPS IFD
    #   110 pool: datetime (20) -> 110; lat (24) -> 130; lon (24) -> 154
    ifd0 = struct.pack(bo + "H", 2) + entry(0x8769, 4, 1, 38) + entry(0x8825, 4, 1, 56) + struct.pack(bo + "I", 0)
    subifd = struct.pack(bo + "H", 1) + entry(0x9003, 2, 20, 110) + struct.pack(bo + "I", 0)
    gps = (
        struct.pack(bo + "H", 4)
        + entry(0x0001, 2, 2, struct.unpack(bo + "I", b"N\x00\x00\x00")[0])  # LatRef 'N'
        + entry(0x0002, 5, 3, 130)                                          # Latitude
        + entry(0x0003, 2, 2, struct.unpack(bo + "I", b"W\x00\x00\x00")[0])  # LonRef 'W'
        + entry(0x0004, 5, 3, 154)                                          # Longitude
        + struct.pack(bo + "I", 0)
    )
    header = b"II" + struct.pack(bo + "HI", 42, 8)
    pool_dt = dt
    lat = struct.pack(bo + "II II II", 40, 1, 25, 1, 0, 1)   # 40°25'0"
    lon = struct.pack(bo + "II II II", 3, 1, 42, 1, 0, 1)    # 3°42'0"

    tiff = header + ifd0 + subifd + gps + pool_dt + lat + lon
    # Comprobamos que los offsets cuadran con el layout anunciado.
    assert len(header) == 8 and len(header + ifd0) == 38
    assert len(header + ifd0 + subifd) == 56
    assert len(header + ifd0 + subifd + gps) == 110
    assert len(header + ifd0 + subifd + gps + pool_dt) == 130
    return b"\xff\xd8" + b"Exif\x00\x00" + tiff


if __name__ == "__main__":
    unittest.main()
