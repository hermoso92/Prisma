# Prisma

[![CI](https://github.com/hermoso92/Prisma/actions/workflows/ci.yml/badge.svg)](https://github.com/hermoso92/Prisma/actions/workflows/ci.yml)

> Tu **cerebro de contexto personal**: un asistente que conoce todo tu mundo digital
> —chats de ChatGPT y Claude, WhatsApp, notas, fotos y vídeos— lo entiende, lo
> indexa y te deja preguntarle cualquier cosa sobre tu propia vida.

Es **100% local, gratuito y privado**: corre en tu Mac, sin servicios de pago y
sin que tus datos salgan del equipo. Se instala con un comando (**pipx**) y un
CLI **te lleva de la mano** para conectar cada app.

Prisma ingiere, normaliza y analiza los datos de tus aplicaciones para construir
una **base de conocimiento personal** unificada, y expone esa memoria a un LLM
(Claude) a través de un servidor **MCP**. El resultado es un asistente que
responde con *tu* contexto real:

- *"¿Qué hablé con Juan en marzo sobre el contrato?"*
- *"Enséñame fotos del viaje de febrero y qué hacíamos cada día."*
- *"Resúmeme el proyecto X que tenía en Claude."*
- *"¿Qué decidí sobre la mudanza entre WhatsApp y mis notas?"*

---

## La idea en una frase

No es "una app que escanea el móvil" (ningún sistema operativo lo permite: iOS y
Android están aislados por *sandbox*). Es un **pipeline de ingesta** que combina
**exports oficiales + APIs + export manual guiado**, normaliza todo a una línea
temporal común, lo analiza (texto, imagen, audio) y lo hace consultable.

```
  FUENTES                    INGESTA              CEREBRO                  ASISTENTE
┌──────────┐          ┌──────────────────┐   ┌──────────────┐        ┌──────────────┐
│ ChatGPT  │─export──▶│  Importadores    │   │ Metadatos DB │        │              │
│ Claude   │─export──▶│  (1 por fuente)  │──▶│ + Vector DB  │◀──RAG──│  Claude vía  │
│ WhatsApp │─manual──▶│        ↓         │   │ + Object     │        │  servidor    │
│ Fotos    │─API─────▶│  NORMALIZADOR    │   │   store      │        │  MCP propio  │
│ Notas    │─Takeout─▶│ (esquema común)  │   │ + Timeline   │        │              │
└──────────┘          └──────────────────┘   └──────────────┘        └──────────────┘
                              │
                      Análisis multimodal:
                      • Visión (describe fotos)
                      • OCR (capturas de pantalla)
                      • Whisper (audios / vídeos)
```

---

## Qué se puede conectar y cómo

No existe un único "lee todo mi móvil". Cada fuente entra por una de tres vías:

| Vía | Descripción | Fuentes |
|-----|-------------|---------|
| **API / MCP oficial** | Datos vivos, automatizable | Google Photos, Gmail, Calendar, Drive |
| **Export oficial de datos** | Histórico completo en ZIP/JSON | ChatGPT, Claude, Google Takeout |
| **Export manual guiado ("a lápiz")** | Lo que no tiene API; Prisma guía al usuario | WhatsApp, Notas de Apple |

> ⚠️ **Importante:** el historial de ChatGPT/Claude **no** sale por su API
> (la API solo *genera* texto nuevo). Sale por el **export oficial** de cada app,
> que además es estructurado y fácil de procesar.

Ver el detalle fuente por fuente en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Principios

1. **Local, gratis y offline.** Todo corre en tu Mac con software libre. La IA
   (describir fotos, transcribir audios) usa modelos locales gratuitos (Ollama,
   Whisper); nada de tus datos sale del equipo ni hay APIs de pago.
2. **Te lleva de la mano.** Un CLI guiado (`setup`, `doctor`, `connect`) explica
   en lenguaje claro cómo exportar de cada app, paso a paso.
3. **Secretos seguros.** Tokens y datos sensibles nunca se escriben en texto plano:
   se guardan en el **Llavero de macOS** (opt-in) o solo en memoria. Tú los apuntas.
4. **Esquema común antes que features.** El 80 % del valor está en normalizar
   todo a una misma línea temporal para poder *cruzar* fuentes.
5. **Solo vías oficiales.** Nada de scraping ni de saltarse términos de servicio.
   Cumplimiento GDPR (datos de terceros en WhatsApp).

---

## Estado actual

🎉 **Fases 0–5 completadas (roadmap base entero).** Esqueleto funcional (esquema
común `Event`, almacenamiento SQLite + object store *content-addressed*, ingesta
idempotente), **importadores de ChatGPT, Claude, WhatsApp y fotos/vídeos**, **IA
local con Ollama** (describe fotos, gratis y offline), **búsqueda semántica**
(embeddings locales + coseno), **servidor MCP** para conectar tu contexto a
Claude, **onboarding guiado** (`setup` / `doctor` / `connect`) y **gestión segura
de secretos** (Llavero de macOS). Ver el
[roadmap](docs/ARCHITECTURE.md#9-plan-por-fases-roadmap).

## Instalación (Mac)

```bash
brew install pipx && pipx ensurepath     # si no tienes pipx
pipx install prisma-context              # instala el CLI `prisma`
prisma setup                             # asistente: te deja todo a punto
```

`prisma doctor` te dice qué tienes y qué falta (todo opcional menos Python).
Para la "magia" de describir fotos en local: `brew install ollama && ollama pull llava`.

## Uso guiado

```bash
prisma connect whatsapp     # te explica cómo exportar (paso a paso, ameno)
prisma connect chatgpt      # idem para cada fuente
prisma ingest --importer whatsapp ~/_chat.txt --me "Tu Nombre"
prisma ingest --importer photos ~/Pictures --analyzer local   # visión + OCR + audio
prisma index                          # genera embeddings locales (Ollama)
prisma search "lo del viaje" --semantic   # busca por significado, no por palabra
prisma search "contrato"              # búsqueda literal (rápida, sin index)
prisma secret set openai              # guarda un token en el Llavero (nunca en disco)
```

> Sin Ollama puedes probar la búsqueda semántica offline con el embedder léxico
> de respaldo: `prisma index --embedder hashing` y
> `prisma search "..." --semantic --embedder hashing`.

## Preguntarle a tu vida desde Claude (MCP)

Prisma expone tu base de conocimiento como un **servidor MCP**, para que Claude
conteste con tu contexto real. Herramientas: `search_context`, `get_timeline`,
`get_thread`, `summarize_period`, `stats`.

Para conectarlo a **Claude Desktop**, añade a su configuración de MCP servers:

```json
{
  "mcpServers": {
    "prisma": { "command": "prisma", "args": ["mcp"] }
  }
}
```

Luego pregúntale en lenguaje natural: *"¿qué hablé con Juan sobre el contrato?"*,
*"resúmeme febrero"*, *"enséñame lo del viaje"*. Todo se resuelve en local: el
servidor solo lee tu base y devuelve texto; la inteligencia la pone Claude.

## Probarlo desde el repo (sin instalar)

Funciona solo con la biblioteca estándar de Python (≥3.10):

```bash
export PYTHONPATH=$(pwd)
export PRISMA_HOME=./prisma_data        # dónde se guardan tus datos (gitignored)

python -m prisma.cli init                                   # crea inbox/ y data/
python -m prisma.cli ingest --importer jsonl examples/sample.jsonl
python -m prisma.cli stats                                  # eventos por fuente
python -m prisma.cli search contrato                        # busca cruzando fuentes
python -m prisma.cli timeline --since 2026-02-01T00:00:00Z  # línea temporal unificada
```

Con tus exports reales (acepta el `.zip` tal cual, una carpeta, o el `.json`):

```bash
python -m prisma.cli ingest --importer chatgpt ~/Descargas/chatgpt-export.zip
python -m prisma.cli ingest --importer claude  ~/Descargas/claude-export.zip
```

Fotos y vídeos (de una carpeta o un export de Google Takeout). Extrae fecha y GPS
del *sidecar* de Takeout o del EXIF; el binario se guarda deduplicado:

```bash
python -m prisma.cli ingest --importer photos ~/Fotos
# El análisis de imagen/audio (caption, OCR, transcripción) es enchufable:
#   --analyzer null    (por defecto) no analiza; solo metadatos
#   --analyzer <local|online>  (fases futuras) describe/transcribe el contenido
```

Reejecutar `ingest` sobre el mismo archivo no duplica nada (ingesta idempotente).

Tests:

```bash
python -m unittest discover -s tests
```

## Estructura del proyecto

```
prisma/
  schema.py            # Event: el esquema común (corazón del sistema)
  config.py            # rutas: inbox (buzón) + data
  ingest.py            # orquestador: importador → análisis → dedupe → persistencia
  cli.py               # CLI: setup/doctor/connect/init/ingest/stats/search/timeline/secret
  onboarding.py        # diagnóstico de entorno + guías amenas por fuente
  secrets.py           # secretos seguros: Llavero de macOS (opt-in) o solo memoria
  storage/
    metadata.py        # eventos / línea temporal (SQLite)
    objects.py         # object store content-addressed (deduplica binarios)
  importers/
    base.py            # interfaz común de importadores
    util.py            # apertura de exports (zip/carpeta/json) + fechas
    jsonl.py           # importador genérico (para probar el pipeline)
    chatgpt.py         # importador del export de ChatGPT
    claude.py          # importador del export de Claude
    whatsapp.py        # importador del _chat.txt de WhatsApp (iOS/Android)
    photos.py          # importador de fotos/vídeos (carpeta + sidecar Takeout)
    notes.py           # importador de notas de texto/Markdown (Apple Notes export…)
    keep.py            # importador de Google Keep (Takeout)
  analysis/
    base.py            # interfaz Analyzer (caption/OCR/transcripción) + registro
    null.py            # analizador por defecto (no analiza; solo metadatos)
    ollama.py          # visión local: describe imágenes con Ollama (llava)
    ocr.py             # OCR local: texto dentro de imágenes con Tesseract
    whisper.py         # transcripción local de audio/vídeo con Whisper
    local.py           # compuesto: visión + OCR + transcripción (todo local)
    exif.py            # parser EXIF mínimo sin dependencias (fecha + GPS)
  embeddings/
    base.py            # interfaz Embedder + registro
    ollama.py          # embeddings locales (nomic-embed-text) para búsqueda semántica
    hashing.py         # embedder léxico de respaldo, offline y sin dependencias
  mcp/
    server.py          # servidor MCP (JSON-RPC sobre stdio) que expone tu contexto
examples/sample.jsonl  # datos de ejemplo multi-fuente
tests/                 # tests: 96 casos
docs/ARCHITECTURE.md   # diseño técnico completo
```

## Documentación

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — diseño técnico completo,
  esquema común, pipeline, seguridad y roadmap.
