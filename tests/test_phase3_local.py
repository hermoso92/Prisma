"""Tests del enfoque local/guiado: secretos, onboarding, WhatsApp y Ollama.

    python -m unittest discover -s tests
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import prisma.secrets as secrets_mod
from prisma.secrets import (
    MemorySecretStore, KeychainSecretStore, get_secret_store,
)
from prisma.onboarding import check_environment, connect_guide, CONNECT_GUIDES
from prisma.importers import WhatsAppImporter
from prisma.analysis.ollama import OllamaAnalyzer


# --- Secretos ---------------------------------------------------------------

class TestMemorySecretStore(unittest.TestCase):
    def test_set_get_delete(self):
        s = MemorySecretStore()
        self.assertIsNone(s.get("tok"))
        s.set("tok", "abc123")
        self.assertEqual(s.get("tok"), "abc123")
        self.assertFalse(s.persistent)
        self.assertTrue(s.delete("tok"))
        self.assertIsNone(s.get("tok"))
        self.assertFalse(s.delete("tok"))


class TestKeychainSecretStore(unittest.TestCase):
    """Mockeamos el binario `security` para no tocar el Llavero real."""

    def setUp(self):
        self._orig = secrets_mod._run
        self.store: dict = {}

        def fake_run(cmd, **kw):
            action = cmd[1]
            svc = cmd[cmd.index("-s") + 1]
            if action == "add-generic-password":
                self.store[svc] = cmd[cmd.index("-w") + 1]
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if action == "find-generic-password":
                if svc in self.store:
                    return SimpleNamespace(returncode=0, stdout=self.store[svc] + "\n", stderr="")
                return SimpleNamespace(returncode=44, stdout="", stderr="not found")
            if action == "delete-generic-password":
                existed = self.store.pop(svc, None) is not None
                return SimpleNamespace(returncode=0 if existed else 44, stdout="", stderr="")
            raise AssertionError(action)

        secrets_mod._run = fake_run

    def tearDown(self):
        secrets_mod._run = self._orig

    def test_roundtrip_via_security_cli(self):
        kc = KeychainSecretStore()
        self.assertTrue(kc.persistent)
        self.assertIsNone(kc.get("openai"))
        kc.set("openai", "sk-secret")
        self.assertEqual(kc.get("openai"), "sk-secret")
        # El servicio se prefija con "prisma:"
        self.assertIn("prisma:openai", self.store)
        self.assertTrue(kc.delete("openai"))
        self.assertIsNone(kc.get("openai"))

    def test_get_returns_none_on_missing(self):
        self.assertIsNone(KeychainSecretStore().get("no-existe"))


class TestGetSecretStore(unittest.TestCase):
    def test_falls_back_to_memory_when_no_keychain(self):
        self.assertIsInstance(get_secret_store(use_keychain=False), MemorySecretStore)


# --- Onboarding -------------------------------------------------------------

class TestOnboarding(unittest.TestCase):
    def test_check_environment_with_injected_checks(self):
        statuses = check_environment(checks={
            "pipx": lambda: True,
            "ollama": lambda: False,
            "whisper": lambda: False,
            "ffmpeg": lambda: False,
            "tesseract": lambda: True,
        })
        by_name = {s.name: s for s in statuses}
        self.assertTrue(by_name["Python ≥ 3.10"].ok)       # corremos en ≥3.10
        self.assertTrue(by_name["pipx"].ok)
        self.assertFalse(by_name["Ollama (IA local)"].ok)
        self.assertTrue(by_name["Tesseract (OCR)"].ok)
        # Python es lo único required
        self.assertEqual([s.name for s in statuses if s.required], ["Python ≥ 3.10"])

    def test_connect_guides_exist_and_include_security_note(self):
        for src in ("chatgpt", "claude", "whatsapp", "fotos"):
            guide = connect_guide(src)
            self.assertIsNotNone(guide)
            self.assertIn("🔐", guide)  # nota de seguridad presente
        self.assertIsNone(connect_guide("inexistente"))

    def test_whatsapp_guide_mentions_export(self):
        self.assertIn("Exportar chat", CONNECT_GUIDES["whatsapp"])


# --- WhatsApp ---------------------------------------------------------------

class TestWhatsAppImporter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, text, name="_chat.txt"):
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_ios_format(self):
        p = self._write(
            "[14/2/26, 21:05:32] Juan: ¿confirmamos el lunes?\n"
            "[14/2/26, 21:06:01] Yo Mismo: sí, perfecto\n"
        )
        events = list(WhatsAppImporter(source_path=p, me="Yo Mismo").iter_events())
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].timestamp, "2026-02-14T21:05:32Z")
        self.assertEqual(events[0].people, ["Juan"])
        self.assertEqual(events[1].people, ["yo"])  # mapeado por --me
        self.assertEqual(events[0].source_meta["sender"], "Juan")

    def test_android_format_and_multiline(self):
        p = self._write(
            "14/2/26, 21:05 - Juan: primera línea\n"
            "y esta es continuación\n"
            "14/2/26, 21:07 - Ana: vale\n"
        )
        events = list(WhatsAppImporter(source_path=p).iter_events())
        self.assertEqual(len(events), 2)
        self.assertIn("continuación", events[0].content)
        self.assertEqual(events[0].timestamp, "2026-02-14T21:05:00Z")

    def test_system_message_has_no_sender(self):
        p = self._write(
            "[14/2/26, 21:00:00] Los mensajes están cifrados de extremo a extremo\n"
            "[14/2/26, 21:05:00] Juan: hola\n"
        )
        events = list(WhatsAppImporter(source_path=p).iter_events())
        self.assertEqual(events[0].type, "note")     # sistema
        self.assertEqual(events[0].people, [])
        self.assertEqual(events[1].type, "message")

    def test_media_marker_flagged(self):
        p = self._write("[14/2/26, 21:05:00] Juan: IMG-0001.jpg (archivo adjunto)\n")
        ev = next(iter(WhatsAppImporter(source_path=p).iter_events()))
        self.assertTrue(ev.source_meta.get("has_media_marker"))

    def test_deterministic_ids(self):
        p = self._write("[1/1/26, 10:00:00] A: hola\n")
        a = list(WhatsAppImporter(source_path=p).iter_events())
        b = list(WhatsAppImporter(source_path=p).iter_events())
        self.assertEqual([e.id for e in a], [e.id for e in b])

    def test_12h_ampm(self):
        p = self._write("[2/14/26, 9:05:00 PM] Juan: tarde\n")
        # formato US: forzamos month-first
        ev = next(iter(WhatsAppImporter(source_path=p, dayfirst=False).iter_events()))
        self.assertEqual(ev.timestamp, "2026-02-14T21:05:00Z")


# --- Ollama (mock HTTP) -----------------------------------------------------

class TestOllamaAnalyzer(unittest.TestCase):
    def test_caption_success(self):
        a = OllamaAnalyzer()
        a._generate = lambda image: "una playa al atardecer"
        d = a.analyze(data=b"img", mime="image/jpeg", type="photo")
        self.assertEqual(d["caption"], "una playa al atardecer")
        self.assertEqual(d["analyzer"], "ollama")

    def test_graceful_degradation_when_offline(self):
        a = OllamaAnalyzer()
        def boom(image):
            raise OSError("connection refused")
        a._generate = boom
        with contextlib.redirect_stderr(io.StringIO()):  # silencia el aviso
            d = a.analyze(data=b"img", mime="image/jpeg", type="photo")
        self.assertEqual(d, {})  # sin caption, no rompe

    def test_does_not_caption_audio(self):
        a = OllamaAnalyzer()
        a._generate = lambda image: "no debería llamarse"
        self.assertIsNone(a.caption(data=b"x", mime="audio/mp4", type="audio"))


if __name__ == "__main__":
    unittest.main()
