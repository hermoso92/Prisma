"""Tests del autodiagnóstico `prisma verify`.

    python -m unittest discover -s tests
"""

import unittest

from prisma.verify import run_verify, _core_checks, _capabilities


class TestVerify(unittest.TestCase):
    def test_core_all_pass(self):
        core = _core_checks()
        failed = [c.name for c in core if not c.ok]
        self.assertEqual(failed, [], f"fallos en el núcleo: {failed}")
        # Debe cubrir todas las etapas clave del pipeline.
        names = " ".join(c.name for c in core)
        for stage in ("Almacenamiento", "Ingesta", "semántica", "identidades", "MCP"):
            self.assertIn(stage, names)

    def test_run_verify_returns_true_and_writes(self):
        lines = []
        ok = run_verify(write=lines.append)
        self.assertTrue(ok)
        out = "\n".join(lines)
        self.assertIn("Núcleo", out)
        self.assertIn("Capacidades opcionales", out)

    def test_capabilities_listed(self):
        caps = {c.name for c in _capabilities()}
        self.assertIn("Pillow (collage)", caps)
        self.assertIn("YOLO (personas/animales)", caps)


if __name__ == "__main__":
    unittest.main()
