# Prisma — Overview técnico

Resumen técnico de en qué se basa la aplicación, cómo se construyó desde cero y
cómo se verifica que funciona. Para el diseño extenso, ver
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Qué es

Un **pipeline local de ingesta + recuperación** de tu contexto personal. La pieza
central es un esquema único, el **`Event`**:

- `id` determinista = `sha256(source + "\0" + native_id)` → **dedup idempotente**
  (reimportar no duplica).
- `content` **siempre texto buscable** (el de una foto es su *caption*; el de un
  audio, su transcripción).
- `media` guarda **referencias** a binarios, no los binarios.

Todo —chat, foto, nota, audio— se normaliza a ese `Event` en una **línea temporal
común**. Esa uniformidad es lo que permite *cruzar* fuentes.

---

## Arquitectura (4 capas, interfaces enchufables)

```
Importer → [Analyzer] → MetadataStore (SQLite) + ObjectStore (content-addressed)
                          + Embeddings (coseno) → MCP server (JSON-RPC/stdio) → Claude
```

- **`Importer`** — uno por fuente: ChatGPT, Claude, WhatsApp, fotos/vídeos, notas,
  Google Keep, jsonl. Acepta ZIP / carpeta / fichero.
- **`Analyzer`** — visión (Ollama), OCR (Tesseract), transcripción (Whisper), o
  `local` (los tres). **100% local, gratis, con degradación elegante**: si falta
  una herramienta, el medio se ingiere igual (solo sin esa parte).
- **`Embedder`** — Ollama `nomic-embed-text` (semántico real) o `hashing` (léxico,
  offline, sin dependencias) para usar/probar la búsqueda vectorial sin Ollama.
- **Almacenamiento** — SQLite (eventos, timeline, búsqueda, embeddings) + object
  store *content-addressed* por SHA-256 (deduplica binarios idénticos). Secretos en
  el **Llavero de macOS** (opt-in) o solo en memoria; nunca en disco en texto plano.
- **MCP server** — JSON-RPC 2.0 sobre stdio, sin dependencias. Expone 5 tools
  (`search_context`, `get_timeline`, `get_thread`, `summarize_period`, `stats`).
  El servidor solo lee la base y devuelve texto; **la inteligencia la pone Claude**.

**Sin dependencias externas:** solo biblioteca estándar de Python (`sqlite3`,
`urllib`, `hashlib`, `array`, `struct`…). Local, gratis, instalable con `pipx`,
Mac-first.

---

## Cómo se construyó desde cero (verificando a la vez)

Estrategia: **rebanadas verticales**. Cada fase entrega algo usable de punta a
punta y **lleva sus tests antes de seguir** — por eso avanzar rápido no rompió
nada: la base `Event` ya sostenía todo lo demás.

| Fase | Entregable | Verificación |
|------|------------|--------------|
| 0 | Esquema `Event` + stores + CLI + ingesta idempotente | tests unit + e2e |
| 1 | Importadores ChatGPT / Claude (parse `conversations.json`) | parse ZIP, tests |
| 2 | Fotos/vídeos: EXIF + GPS + análisis enchufable | EXIF construido a mano en test |
| 3 | WhatsApp + onboarding guiado + secretos + Ollama | mocks de `security` / HTTP |
| 4 | Embeddings + búsqueda semántica (coseno) | ranking verificado |
| 5 | Servidor MCP | handshake + tools por stdio |
| 6 | Notas (texto/Markdown) + Google Keep (Takeout) | e2e |

---

## Cómo se comprueba que funciona (comprobado, no solo afirmado)

- **Tests:** 97 casos (`python -m unittest discover -s tests`), todos verdes.
- **CI:** GitHub Actions en Ubuntu (Python 3.10/3.11/3.12) + macOS 3.12.
- **Instalación limpia:** `pip install -e .` en un venv nuevo y comando `prisma`.
- **Integración real:** las **7 fuentes** ingeridas a la vez → 14 eventos en una
  base → `stats`, `timeline`, búsqueda semántica y MCP **cruzando fuentes**
  correctamente.

### Flujo completo (todo local)

```bash
prisma setup                                       # onboarding guiado
prisma connect whatsapp                            # te explica cómo exportar
prisma ingest --importer whatsapp ~/_chat.txt --me "Tú"
prisma ingest --importer photos ~/Fotos --analyzer local
prisma index                                       # embeddings locales
prisma search "lo del viaje" --semantic            # busca por significado
prisma mcp                                         # → Claude pregunta a tu vida
```

---

## Límites conocidos (por naturaleza, no roturas ocultas)

- La **calidad** de los modelos reales (Ollama/Whisper) solo se mide **en tu Mac**;
  aquí están aislados tras interfaces y degradan, así que su ausencia no rompe nada.
- Los **parsers** siguen el formato conocido de cada export; conviene contrastarlos
  con un export real.
- `hashing` es léxico (no semántico); la búsqueda de calidad necesita Ollama.
- El coseno en Python puro basta para una base personal, no para millones de
  vectores (sustituible por FAISS/Qdrant/pgvector).
