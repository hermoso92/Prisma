"""Tests de Whisper (transcripción) y Tesseract (OCR) locales, y del compuesto.

No requieren los binarios reales: se aíslan los puntos de ejecución
(``_transcribe_file`` / ``_ocr_file``) y la detección de disponibilidad.

    python -m unittest discover -s tests
"""

import contextlib
import io
import unittest

from prisma.analysis import (
    OcrAnalyzer, WhisperAnalyzer, LocalAnalyzer, get_analyzer,
)


class TestWhisperAnalyzer(unittest.TestCase):
    def test_only_audio_and_video(self):
        a = WhisperAnalyzer()
        a.available = lambda: True
        a._transcribe_file = lambda media, outdir: "transcrito"
        self.assertEqual(a.transcribe(data=b"x", mime="audio/mp4", type="audio"), "transcrito")
        self.assertEqual(a.transcribe(data=b"x", mime="video/mp4", type="video"), "transcrito")
        self.assertIsNone(a.transcribe(data=b"x", mime="image/jpeg", type="photo"))

    def test_graceful_when_tool_missing(self):
        a = WhisperAnalyzer(cmd="whisper-que-no-existe-xyz")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(a.transcribe(data=b"x", mime="audio/mp4", type="audio"))

    def test_analyze_orchestration_fills_transcript(self):
        a = WhisperAnalyzer()
        a.available = lambda: True
        a._transcribe_file = lambda media, outdir: "hola que tal"
        d = a.analyze(data=b"x", mime="audio/mp4", type="audio")
        self.assertEqual(d["transcript"], "hola que tal")
        self.assertEqual(d["analyzer"], "whisper")

    def test_writes_tempfile_with_right_suffix(self):
        a = WhisperAnalyzer()
        a.available = lambda: True
        seen = {}
        def fake(media, outdir):
            seen["suffix"] = media.suffix
            seen["data"] = media.read_bytes()
            return "ok"
        a._transcribe_file = fake
        a.transcribe(data=b"audio-bytes", mime="audio/ogg", type="audio")
        self.assertEqual(seen["suffix"], ".ogg")
        self.assertEqual(seen["data"], b"audio-bytes")


class TestOcrAnalyzer(unittest.TestCase):
    def test_only_photos(self):
        a = OcrAnalyzer()
        a.available = lambda: True
        a._ocr_file = lambda img: "texto en la imagen"
        self.assertEqual(a.ocr(data=b"x", mime="image/png", type="photo"), "texto en la imagen")
        self.assertIsNone(a.ocr(data=b"x", mime="video/mp4", type="video"))

    def test_graceful_when_tool_missing(self):
        a = OcrAnalyzer(cmd="tesseract-que-no-existe-xyz")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(a.ocr(data=b"x", mime="image/png", type="photo"))

    def test_analyze_fills_ocr(self):
        a = OcrAnalyzer()
        a.available = lambda: True
        a._ocr_file = lambda img: "FACTURA total 42€"
        d = a.analyze(data=b"x", mime="image/png", type="photo")
        self.assertEqual(d["ocr"], "FACTURA total 42€")


class TestLocalComposite(unittest.TestCase):
    def test_combines_vision_ocr_transcribe(self):
        class V:
            def caption(self, **kw): return "una playa"
        class O:
            def ocr(self, **kw): return "cartel: bar"
        class W:
            def transcribe(self, **kw): return "audio del vídeo"
        a = LocalAnalyzer(vision=V(), ocr=O(), transcriber=W())
        # Foto: caption + ocr, sin transcript.
        d = a.analyze(data=b"x", mime="image/jpeg", type="photo")
        self.assertEqual(d["caption"], "una playa")
        self.assertEqual(d["ocr"], "cartel: bar")
        self.assertNotIn("transcript", d)
        # Vídeo: los tres aplican.
        dv = a.analyze(data=b"x", mime="video/mp4", type="video")
        self.assertEqual(dv["transcript"], "audio del vídeo")
        self.assertEqual(dv["analyzer"], "local")

    def test_registered(self):
        for name in ("ocr", "whisper", "local"):
            self.assertIsNotNone(get_analyzer(name))


if __name__ == "__main__":
    unittest.main()
