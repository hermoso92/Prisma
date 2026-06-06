"""Onboarding guiado: comprobación de entorno y guías por fuente.

El objetivo es que Prisma "te lleve de la mano": comprobar qué hace falta y, en
tono ameno, explicarte cómo exportar tus datos de cada app. Todo pensado para
macOS primero (las pistas de instalación usan Homebrew), pero el código es
multiplataforma.

- :func:`check_environment` — diagnóstico de herramientas (``prisma doctor``).
- :data:`CONNECT_GUIDES` — guías paso a paso por fuente (``prisma connect X``).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional

_run = subprocess.run


@dataclass
class ToolStatus:
    name: str
    ok: bool
    required: bool
    detail: str
    install_hint: str
    why: str

    @property
    def mark(self) -> str:
        if self.ok:
            return "✅"
        return "❌" if self.required else "⚪️"


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _ollama_running() -> bool:
    """¿Está Ollama instalado y respondiendo en local?"""
    if not _has("ollama"):
        return False
    try:
        proc = _run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def check_environment(checks: Optional[dict[str, Callable[[], bool]]] = None) -> list[ToolStatus]:
    """Diagnóstico del entorno. ``checks`` permite inyectar detección en tests."""
    c = checks or {}
    py_ok = sys.version_info >= (3, 10)

    def has(cmd: str) -> bool:
        return c[cmd]() if cmd in c else _has(cmd)

    ollama_ok = c["ollama"]() if "ollama" in c else _ollama_running()

    return [
        ToolStatus(
            "Python ≥ 3.10", py_ok, True,
            detail=sys.version.split()[0],
            install_hint="brew install python",
            why="Motor de Prisma.",
        ),
        ToolStatus(
            "pipx", has("pipx"), False,
            detail="instalado" if has("pipx") else "no encontrado",
            install_hint="brew install pipx && pipx ensurepath",
            why="Instala Prisma de forma aislada y limpia.",
        ),
        ToolStatus(
            "Ollama (IA local)", ollama_ok, False,
            detail="en marcha" if ollama_ok else "no disponible",
            install_hint="brew install ollama && ollama pull llava && ollama pull nomic-embed-text",
            why="Describe tus fotos y genera embeddings, 100% local y gratis.",
        ),
        ToolStatus(
            "Whisper / ffmpeg", has("whisper") or has("ffmpeg"), False,
            detail="disponible" if (has("whisper") or has("ffmpeg")) else "no encontrado",
            install_hint="brew install ffmpeg && pipx install openai-whisper",
            why="Transcribe audios y vídeos a texto, en local.",
        ),
        ToolStatus(
            "Tesseract (OCR)", has("tesseract"), False,
            detail="instalado" if has("tesseract") else "no encontrado",
            install_hint="brew install tesseract tesseract-lang",
            why="Lee el texto dentro de capturas de pantalla.",
        ),
    ]


# --- Guías por fuente (tono ameno, paso a paso) -----------------------------

_SECURITY_NOTE = (
    "🔐 Si una fuente te pide un token o código: apúntalo en tu libreta y NO lo "
    "compartas con nadie. Prisma no lo guarda en disco; con --keychain lo deja "
    "cifrado en tu Llavero de macOS y lo usa solo en el momento de la petición."
)

CONNECT_GUIDES: dict[str, str] = {
    "chatgpt": """📦 Exportar tu ChatGPT

1. Abre ChatGPT (web o app) con tu cuenta.
2. Ajustes → Controles de datos → «Exportar datos» → Confirmar.
3. Recibirás un email con un enlace; descarga el .zip (caduca pronto).
4. Déjalo en tu carpeta buzón y luego:
     prisma ingest --importer chatgpt RUTA/al/chatgpt-export.zip

ℹ️  El .zip trae conversations.json con todo tu historial y fechas. No necesita
   ningún token: es un export oficial, todo se procesa en tu Mac.""",

    "claude": """📦 Exportar tu Claude

1. Abre Claude con tu cuenta.
2. Ajustes (Settings) → Privacy → «Export data».
3. Llega por email; descarga el .zip.
4. Ingiérelo:
     prisma ingest --importer claude RUTA/al/claude-export.zip

ℹ️  Incluye conversaciones y proyectos. Export oficial, sin tokens, todo local.""",

    "whatsapp": """📦 Exportar un chat de WhatsApp (a lápiz, te guío)

En el móvil:
1. Abre el chat (o grupo) que quieras guardar.
2. Toca el nombre del chat arriba → baja hasta «Exportar chat».
3. Elige «Incluir archivos» si quieres también fotos/audios (pesa más) o
   «Sin archivos» para solo el texto.
4. Envíatelo a ti mismo (email, Notas, AirDrop al Mac…).
5. En el Mac, descomprime y deja el .txt (y la carpeta de medios) en el buzón:
     prisma ingest --importer whatsapp RUTA/al/_chat.txt --me "Tu Nombre"

ℹ️  --me indica cuál de los nombres eres tú (para marcarte como «yo»).
   WhatsApp no tiene API personal: este export manual es la vía oficial.""",

    "fotos": """📦 Tus fotos y vídeos

Opción A — carpeta local (lo más simple):
   prisma ingest --importer photos ~/Pictures --analyzer ollama

Opción B — Google Fotos vía Takeout (https://takeout.google.com):
1. Selecciona solo «Google Photos» → crea la exportación.
2. Descarga y descomprime el .zip.
3. Ingiere la carpeta (Prisma lee la fecha y el GPS de los sidecars .json):
     prisma ingest --importer photos RUTA/Takeout/Google\\ Photos --analyzer ollama

Opción C — Google Photos API (en vivo, sin descargar export):
1. Consigue un token OAuth con scope photoslibrary.readonly (p. ej. en
   OAuth Playground) y guárdalo seguro:  prisma secret set google
2. Ingiere directamente desde la API:
     prisma ingest --importer gphotos --analyzer ollama

ℹ️  Con --analyzer ollama, tu Mac describe cada foto en local (necesita Ollama).
   Sin él, se guardan igual con su fecha. (La API de Google no expone el GPS.)""",

    "notas": """📦 Notas

- Apple Notes: selecciona notas → Archivo → «Exportar como PDF», o cópialas a una
  carpeta de texto (.txt/.md). Luego:
     prisma ingest --importer notes RUTA/a/tus-notas
- Google Keep: usa Takeout (https://takeout.google.com) → solo «Keep». Descomprime
  y apunta a la carpeta Keep/ (Prisma lee los .json):
     prisma ingest --importer keep RUTA/Takeout/Keep

ℹ️  El importador de notas lee carpetas de .txt/.md; el de Keep lee el Takeout.""",
}


def connect_guide(source: str) -> Optional[str]:
    guide = CONNECT_GUIDES.get(source)
    if guide is None:
        return None
    return f"{guide}\n\n{_SECURITY_NOTE}"
