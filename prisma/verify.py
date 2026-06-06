"""Autodiagnóstico de Prisma: comprueba que el bosque entero funciona.

``prisma verify`` ejecuta una prueba de integración **no destructiva** (en un
directorio temporal) que recorre todo el pipeline con datos sintéticos:
almacenamiento → ingesta → búsqueda léxica → embeddings/semántica → identidades →
fotos por atributos → servidor MCP. Luego informa de qué **capacidades opcionales**
(Ollama, Whisper, Tesseract, YOLO, reconocimiento facial, Pillow, ffmpeg) están
disponibles en este equipo.

Sirve para que el usuario confirme, en su Mac y de un vistazo, que todo está en
orden antes de validar con sus datos reales.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def _core_checks() -> list[Check]:
    """Prueba el pipeline de punta a punta con datos sintéticos (en sandbox)."""
    from prisma.config import Config
    from prisma.embeddings import HashingEmbedder
    from prisma.identity import IdentityMap
    from prisma.importers import JsonlImporter
    from prisma.ingest import Pipeline
    from prisma.mcp import McpServer
    from prisma.schema import Event
    from prisma.storage import MetadataStore, ObjectStore

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = Config(home=root)
        cfg.ensure_dirs()

        # 1) Almacenamiento + object store
        try:
            store = MetadataStore(cfg.db_path)
            objects = ObjectStore(cfg.objects_dir)
            ref = objects.put(b"hola")
            ok = objects.get(ref) == b"hola"
            checks.append(Check("Almacenamiento (SQLite + object store)", ok))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("Almacenamiento (SQLite + object store)", False, str(exc)))
            return checks  # sin store no seguimos

        # 2) Ingesta (esquema común) idempotente
        try:
            jsonl = root / "s.jsonl"
            jsonl.write_text(
                '{"source":"chatgpt","source_native_id":"m1","type":"message",'
                '"timestamp":"2026-02-03T10:15:00Z","content":"viaje a Roma con Juan",'
                '"people":["Juan"]}\n'
                '{"source":"whatsapp","source_native_id":"w1","type":"message",'
                '"timestamp":"2026-02-14T21:05:00Z","content":"contrato de alquiler",'
                '"people":["Juan Pérez"]}\n', encoding="utf-8")
            res = Pipeline(store, objects).ingest(JsonlImporter(source_path=jsonl))
            again = Pipeline(store, objects).ingest(JsonlImporter(source_path=jsonl))
            ok = res.new == 2 and again.new == 0  # idempotente
            checks.append(Check("Ingesta + normalización (idempotente)", ok,
                                f"{res.new} nuevos, reimport {again.new}"))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("Ingesta + normalización", False, str(exc)))

        # 3) Búsqueda léxica
        try:
            hits = store.search("contrato")
            checks.append(Check("Búsqueda literal", len(hits) == 1))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("Búsqueda literal", False, str(exc)))

        # 4) Embeddings + búsqueda semántica (offline, hashing)
        try:
            emb = HashingEmbedder()
            for ev in store.iter_unembedded(emb.key):
                store.add_embedding(ev.id, emb.key, emb.embed(ev.content))
            scored = store.vector_search(emb.embed("alquiler"), emb.key, limit=2)
            checks.append(Check("Embeddings + búsqueda semántica", bool(scored)))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("Embeddings + búsqueda semántica", False, str(exc)))

        # 5) Resolución de identidades entre fuentes
        try:
            idmap = IdentityMap(root / "id.json")
            idmap.add("Juan Pérez", "Juan")
            evs = store.events_by_person("Juan", resolve=idmap.resolve)
            ok = {e.source for e in evs} == {"chatgpt", "whatsapp"}
            checks.append(Check("Resolución de identidades (cruza fuentes)", ok))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("Resolución de identidades", False, str(exc)))

        # 6) Fotos por atributos (consulta is_only_me)
        try:
            p = Event.create(source="photos", source_native_id="p1", type="photo",
                             timestamp="2026-03-01T00:00:00Z", content="")
            p.derived = {"people_count": 1, "animals": [], "faces": ["me"], "is_only_me": True}
            store.add_event(p)
            ok = len(store.photos_where(only_me=True)) == 1
            checks.append(Check("Fotos por atributos (solo-yo)", ok))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("Fotos por atributos", False, str(exc)))

        # 7) Servidor MCP (handshake + tool)
        try:
            srv = McpServer(store, embedder_name="hashing")
            init = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            tool = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                               "params": {"name": "stats", "arguments": {}}})
            ok = (init["result"]["serverInfo"]["name"] == "prisma"
                  and "TOTAL" in tool["result"]["content"][0]["text"])
            checks.append(Check("Servidor MCP (handshake + tool)", ok))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("Servidor MCP", False, str(exc)))

        store.close()
    return checks


def _importable(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:  # noqa: BLE001
        return False


def _capabilities() -> list[Check]:
    """Capacidades opcionales (mejoran la 'magia'); su ausencia no rompe nada."""
    return [
        Check("Ollama (describir fotos)", shutil.which("ollama") is not None,
              "brew install ollama && ollama pull llava nomic-embed-text"),
        Check("Whisper / ffmpeg (transcribir)",
              shutil.which("whisper") is not None or shutil.which("ffmpeg") is not None,
              "brew install ffmpeg && pipx install openai-whisper"),
        Check("Tesseract (OCR)", shutil.which("tesseract") is not None,
              "brew install tesseract tesseract-lang"),
        Check("YOLO (personas/animales)", _importable("ultralytics"),
              "pipx install ultralytics"),
        Check("Reconocimiento facial ('solo yo')", _importable("face_recognition"),
              "brew install cmake && pipx install face_recognition"),
        Check("Pillow (collage)", _importable("PIL"), "pip install pillow"),
        Check("ffmpeg (vídeo)", shutil.which("ffmpeg") is not None, "brew install ffmpeg"),
    ]


def run_verify(write: Callable[[str], None] = print) -> bool:
    """Ejecuta el autodiagnóstico. Devuelve ``True`` si el núcleo está sano."""
    write("🔬 Verificación de Prisma (prueba no destructiva del pipeline)\n")
    core = _core_checks()
    write("  Núcleo (debe estar todo ✅):")
    for c in core:
        line = f"    {'✅' if c.ok else '❌'}  {c.name}"
        if c.detail and not c.ok:
            line += f"  — {c.detail}"
        write(line)

    write("\n  Capacidades opcionales (mejoran la 'magia', no imprescindibles):")
    for c in _capabilities():
        mark = "✅" if c.ok else "⚪️"
        write(f"    {mark}  {c.name}")
        if not c.ok:
            write(f"          instalar: {c.detail}")

    core_ok = all(c.ok for c in core)
    write("")
    if core_ok:
        write("✅ El núcleo funciona de punta a punta. Lo opcional, instálalo según quieras.")
    else:
        write("❌ Hay fallos en el núcleo; revisa lo marcado arriba.")
    return core_ok
