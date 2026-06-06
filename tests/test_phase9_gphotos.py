"""Tests del importador de Google Photos (API viva, lógica mockeada).

No hace red: se inyectan ``_fetch_page`` y ``_download``.

    python -m unittest discover -s tests
"""

import tempfile
import unittest
from pathlib import Path

from prisma.importers.google_photos import GooglePhotosImporter, GooglePhotosError
from prisma.storage import ObjectStore


_PAGE1 = {
    "mediaItems": [
        {"id": "g1", "filename": "playa.jpg", "mimeType": "image/jpeg",
         "baseUrl": "https://base/g1", "description": "atardecer",
         "mediaMetadata": {"creationTime": "2026-02-14T21:02:00Z", "photo": {}}},
        {"id": "g2", "filename": "clip.mp4", "mimeType": "video/mp4",
         "baseUrl": "https://base/g2",
         "mediaMetadata": {"creationTime": "2026-02-15T10:00:00.000Z", "video": {}}},
    ],
    "nextPageToken": "TOK2",
}
_PAGE2 = {
    "mediaItems": [
        {"id": "g3", "filename": "monte.jpg", "mimeType": "image/jpeg",
         "baseUrl": "https://base/g3",
         "mediaMetadata": {"creationTime": "2026-03-01T08:00:00Z", "photo": {}}},
    ],
}


def _importer(tmp, **kw):
    objects = ObjectStore(Path(tmp) / "objects")
    imp = GooglePhotosImporter(objects=objects, access_token="fake-token", **kw)
    pages = {None: _PAGE1, "TOK2": _PAGE2}
    imp._fetch_page = lambda page_token: pages[page_token]
    imp._download = lambda base_url, is_video: f"BYTES:{base_url}".encode()
    return imp, objects


class TestGooglePhotos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_requires_token(self):
        imp = GooglePhotosImporter(access_token=None)
        with self.assertRaises(GooglePhotosError):
            list(imp.iter_events())

    def test_paginates_all_items(self):
        imp, _ = _importer(self.tmp.name)
        events = list(imp.iter_events())
        self.assertEqual([e.source_meta["google_id"] for e in events], ["g1", "g2", "g3"])

    def test_type_and_timestamp_mapping(self):
        imp, _ = _importer(self.tmp.name)
        events = {e.source_meta["google_id"]: e for e in imp.iter_events()}
        self.assertEqual(events["g1"].type, "photo")
        self.assertEqual(events["g2"].type, "video")
        self.assertEqual(events["g1"].timestamp, "2026-02-14T21:02:00Z")
        self.assertEqual(events["g2"].timestamp, "2026-02-15T10:00:00Z")
        self.assertEqual(events["g1"].content, "atardecer")
        self.assertEqual(events["g1"].source, "gphotos")

    def test_downloads_into_object_store(self):
        imp, objects = _importer(self.tmp.name)
        ev = next(iter(imp.iter_events()))
        ref = ev.media[0]["ref"]
        self.assertTrue(objects.exists(ref))
        self.assertEqual(objects.get(ref), b"BYTES:https://base/g1")

    def test_no_download_keeps_base_url(self):
        imp, _ = _importer(self.tmp.name, download=False)
        ev = next(iter(imp.iter_events()))
        self.assertEqual(ev.media, [])
        self.assertEqual(ev.source_meta["base_url"], "https://base/g1")

    def test_max_items(self):
        imp, _ = _importer(self.tmp.name, max_items=1)
        self.assertEqual(len(list(imp.iter_events())), 1)

    def test_deterministic_ids(self):
        a, _ = _importer(self.tmp.name)
        b, _ = _importer(self.tmp.name)
        self.assertEqual([e.id for e in a.iter_events()], [e.id for e in b.iter_events()])


if __name__ == "__main__":
    unittest.main()
