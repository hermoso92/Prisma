# Arquitectura de Prisma

> Cerebro de contexto personal. Este documento describe el diseño técnico, el
> esquema de datos común, el pipeline de ingesta/análisis, el modelo de
> seguridad y el plan de implementación por fases.

**Índice**

1. [Visión y objetivos](#1-visión-y-objetivos)
2. [Realidad técnica: por qué no hay un botón mágico](#2-realidad-técnica-por-qué-no-hay-un-botón-mágico)
3. [Fuentes: qué se puede sacar y cómo](#3-fuentes-qué-se-puede-sacar-y-cómo)
4. [Visión general de la arquitectura](#4-visión-general-de-la-arquitectura)
5. [El esquema común (corazón del sistema)](#5-el-esquema-común-corazón-del-sistema)
6. [Pipeline de ingesta y análisis](#6-pipeline-de-ingesta-y-análisis)
7. [Almacenamiento](#7-almacenamiento)
8. [El asistente: servidor MCP propio](#8-el-asistente-servidor-mcp-propio)
9. [Plan por fases (roadmap)](#9-plan-por-fases-roadmap)
10. [Seguridad, privacidad y cumplimiento](#10-seguridad-privacidad-y-cumplimiento)
11. [Stack tecnológico propuesto](#11-stack-tecnológico-propuesto)
12. [Riesgos y decisiones abiertas](#12-riesgos-y-decisiones-abiertas)

---

## 1. Visión y objetivos

Construir un **asistente que conozca todo el contexto digital del usuario** a lo
largo del tiempo: conversaciones (ChatGPT, Claude, WhatsApp), notas, fotos y
vídeos. El usuario podrá preguntar en lenguaje natural y obtener respuestas que
cruzan fuentes y momentos ("¿qué pasó en febrero?", "fotos + chats del viaje").

**Objetivos**

- Ingesta **incremental** y repetible (vuelves a exportar y solo entra lo nuevo).
- **Multimodal**: el texto, las imágenes, los audios y los vídeos acaban todos
  siendo buscables.
- **Línea temporal unificada**: cruzar fuentes por fecha, persona y lugar.
- **Local-first** y privado por defecto.
- Interfaz vía **MCP** para conectar a Claude sin reinventar un chat.

**No-objetivos (de momento)**

- No escanear el móvil "en vivo" (imposible por sandbox).
- No scraping ni automatización que viole términos de servicio.
- No una UI de chat propia en las primeras fases (se usa Claude vía MCP).

---

## 2. Realidad técnica: por qué no hay un botón mágico

iOS y Android aíslan las apps entre sí (*sandbox*): **ninguna app puede leer los
datos de otra**. Por tanto "todo el móvil" se consigue **fuente por fuente**,
combinando tres vías de extracción:

1. **API / MCP oficial** — datos vivos y automatizables (Google Photos, Gmail…).
2. **Export oficial de datos** — el histórico completo en ZIP/JSON (ChatGPT,
   Claude, Google Takeout).
3. **Export manual guiado** — para lo que no tiene API; Prisma da instrucciones
   paso a paso y procesa el archivo resultante (WhatsApp, Notas de Apple).

**Aclaración crítica:** la **API** de ChatGPT/Claude sirve para *generar* texto,
**no** para leer tu historial. El historial solo sale por el **export oficial**.
Esto en realidad simplifica el trabajo: los exports son estructurados.

---

## 3. Fuentes: qué se puede sacar y cómo

| Fuente | Vía | Qué obtienes | Dificultad | Notas |
|--------|-----|--------------|------------|-------|
| **ChatGPT** | Export oficial | ZIP con `conversations.json` (todos los chats + timestamps) | 🟢 Baja | Ajustes → Controles de datos → Exportar |
| **Claude** | Export oficial | ZIP con conversaciones y proyectos | 🟢 Baja | Ajustes → Privacidad → Exportar datos |
| **Fotos / vídeos (Google)** | API + Takeout | Archivos + EXIF (fecha, GPS, dispositivo) | 🟡 Media | Google Photos Library API / Takeout |
| **Fotos / vídeos (Apple)** | Export iCloud | Archivos + EXIF | 🟡 Media | Export manual o iCloud |
| **WhatsApp** | Export manual | `.txt` por chat + multimedia | 🟡 Media | "Exportar chat" (con/sin multimedia). **No hay API personal** |
| **Notas Apple** | Export manual | Texto/PDF | 🔴 Alta | Sistema cerrado; export limitado |
| **Google Keep** | Takeout | JSON/HTML | 🟡 Media | Google Takeout |
| **Gmail / Calendar / Drive** | API/MCP | Mensajes, eventos, archivos | 🟡 Media | OAuth |

**Estrategia de "a lápiz" (export manual guiado):** para WhatsApp y similares,
Prisma muestra instrucciones concretas ("Abre el chat → ⋮ → Más → Exportar chat
→ Incluir archivos"), el usuario suelta el resultado en la **carpeta buzón**, y
el importador correspondiente lo procesa. La automatización está en el
*procesado*, no en la extracción (que requiere acción humana por diseño).

---

## 4. Visión general de la arquitectura

Cuatro capas. La regla de oro: **construir el lago de contexto primero**, y
enchufar el LLM por encima al final.

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
                      Análisis multimodal
```

1. **Conectores/Importadores** — uno por fuente. Leen export/API y emiten
   *eventos crudos*.
2. **Normalizador** — convierte cada evento crudo al **esquema común**.
3. **Análisis multimodal** — visión, OCR y transcripción enriquecen los eventos
   con texto buscable.
4. **Almacenamiento** — metadatos + vectores + archivos.
5. **Asistente (MCP)** — expone la base de conocimiento como herramientas para
   Claude (RAG sobre la línea temporal).

---

## 5. El esquema común (corazón del sistema)

Todo —un WhatsApp, una foto, un chat de Claude, una nota— se normaliza al mismo
tipo de **evento**. Esto es lo que permite *cruzar* fuentes.

```jsonc
// Event: la unidad atómica de la línea temporal
{
  "id": "uuid",                  // id estable y determinista (ver dedupe)
  "source": "chatgpt",           // chatgpt | claude | whatsapp | photos | notes | ...
  "type": "message",             // message | photo | video | audio | note | event | file
  "timestamp": "2026-03-14T18:22:00Z",
  "title": null,                 // opcional (p. ej. título de conversación/nota)
  "content": "texto buscable",   // texto original o derivado (transcripción/caption)
  "people": ["Juan", "yo"],      // participantes / personas detectadas
  "location": {                  // si hay GPS/EXIF
    "lat": 40.41, "lon": -3.70, "place": "Madrid"
  },
  "media": [                     // refs a object store (no el binario)
    { "ref": "blob://sha256:...", "mime": "image/jpeg", "role": "primary" }
  ],
  "thread_id": "conv-123",       // agrupa mensajes de una misma conversación
  "source_meta": { },            // campos crudos específicos de la fuente
  "derived": {                   // resultado del análisis
    "caption": "playa al atardecer, dos personas",
    "ocr": null,
    "transcript": null,
    "entities": ["playa", "atardecer"],
    "embedding_id": "vec-456"
  },
  "ingested_at": "2026-05-31T10:00:00Z",
  "schema_version": 1
}
```

**Decisiones de diseño**

- **`id` determinista** = hash de `(source, source_native_id)` → reimportar el
  mismo export **no duplica** (idempotencia / dedupe).
- **`content` siempre texto.** Las fotos tienen `content` = su *caption*; los
  audios, su *transcripción*. Así una sola búsqueda cubre todo.
- **`media` guarda referencias**, no binarios (los binarios van al object store
  por hash → *content-addressed*, deduplica archivos idénticos).
- **`thread_id`** reconstruye conversaciones; **`timestamp`** ordena la vida.
- **`schema_version`** permite migraciones sin reimportar todo.

Entidades secundarias derivadas del flujo de eventos: `Person`, `Place`,
`Thread`, `Project` (para proyectos de Claude/ChatGPT), `Source` (estado de cada
conector: último import, cursor incremental).

---

## 6. Pipeline de ingesta y análisis

```
  carpeta buzón / API
        │
        ▼
  [1] Importador  ──▶ eventos crudos (JSON por fuente)
        │
        ▼
  [2] Normalizador ──▶ Event (esquema común)  ──┐
        │                                        │ dedupe por id
        ▼                                        ▼
  [3] Análisis multimodal:               (si ya existe, se omite)
        • Visión   → caption de fotos/frames de vídeo
        • OCR      → texto de capturas de pantalla
        • Whisper  → transcripción de audios y vídeos
        • NER      → personas, lugares, temas
        │
        ▼
  [4] Embeddings (texto + imagen) ──▶ Vector DB
        │
        ▼
  [5] Persistencia: Metadatos DB + Object store
```

- **Incremental:** cada `Source` guarda un cursor (fecha/última posición); al
  reimportar solo entra lo nuevo.
- **Idempotente:** reejecutar el pipeline sobre los mismos datos no cambia nada.
- **Reanudable:** el análisis multimodal (lo caro) se cachea por hash del medio.
- **Asíncrono:** la ingesta encola trabajos; el análisis corre en background.

---

## 7. Almacenamiento

Tres almacenes, simples al principio y sustituibles después:

| Almacén | Fase inicial | Escala posterior | Guarda |
|---------|--------------|------------------|--------|
| **Metadatos / Timeline** | SQLite | Postgres | Eventos, personas, threads, estado de fuentes |
| **Vectores** | sqlite-vec / FAISS local | Qdrant / pgvector | Embeddings de texto e imagen |
| **Object store** | Carpeta local content-addressed (`blob/<sha256>`) | S3/MinIO | Fotos, vídeos, audios, adjuntos |

*Content-addressed*: el nombre del archivo es su hash → la misma foto enviada por
WhatsApp y guardada en Photos se almacena **una sola vez**.

---

## 8. El asistente: servidor MCP propio

En lugar de construir otra UI de chat, Prisma expone su base de conocimiento como
un **servidor MCP**. Te conectas con Claude (en la app de Claude, en Claude Code,
o donde quieras) y Claude consulta tu "cerebro" mediante herramientas:

Herramientas MCP propuestas:

- `search_context(query, filtros)` — búsqueda semántica + por fecha/persona/fuente.
- `get_timeline(desde, hasta, fuentes)` — eventos de un rango (p. ej. "febrero").
- `get_thread(thread_id)` — reconstruye una conversación completa.
- `summarize_period(desde, hasta)` — resumen de un periodo cruzando fuentes.
- `get_media(event_id)` — devuelve la foto/audio asociado.

Ventajas: menos código que un chat propio, mejor resultado (usas Claude
directamente), y la base de conocimiento queda **reutilizable** por cualquier
cliente MCP.

---

## 9. Plan por fases (roadmap)

Rebanadas verticales: cada fase entrega algo usable de punta a punta.

| Fase | Objetivo | Entregable | Estado |
|------|----------|------------|--------|
| **0** | Cimientos | Esquema común + almacenamiento + carpeta buzón + CLI de ingesta | ✅ |
| **1** | Texto estructurado | Importadores de **ChatGPT** y **Claude** (ZIP → eventos) | ✅ |
| **2** | Multimodal | Pipeline de **fotos/vídeos**: EXIF/sidecar + análisis enchufable (caption/OCR/transcripción) | ✅ |
| **3** | Mensajería | Importador **WhatsApp** (export manual guiado) | ✅ |
| **4** | Recuperación | **Embeddings** locales (Ollama) + búsqueda semántica por coseno | ✅ |
| **5** | Asistente | **Servidor MCP** → conectado a Claude | ⬜ |
| **6+** | Más fuentes | Notas, Gmail, Calendar, Drive, Google Keep… | ⬜ |

**Por qué este orden:** ChatGPT/Claude primero = victoria rápida y motivadora
(JSON estructurado). Fotos después = donde se ve la "magia" multimodal. WhatsApp
cuando el pipeline ya esté maduro. El MCP al final, sobre datos ya ricos.

---

## 10. Seguridad, privacidad y cumplimiento

No es opcional, y menos operando desde España (GDPR).

- **Local-first por defecto.** El procesado y almacenamiento son locales salvo
  que el usuario active explícitamente un servicio en la nube.
- **Cifrado en reposo** del object store y la base de metadatos.
- **Secretos en vault** (tokens OAuth, claves API): nunca en el repo ni en claro.
- **Consentimiento por conector:** el usuario autoriza cada fuente por separado.
- **Datos de terceros:** los chats de WhatsApp contienen mensajes de otras
  personas. Para uso personal es legítimo, pero hay que tratarlos con cuidado,
  no compartirlos y permitir borrado selectivo.
- **Solo vías oficiales:** exports y APIs documentadas. **Nada de scraping** ni
  de eludir términos de servicio.
- **Derecho al olvido:** poder eliminar una fuente, un periodo o una persona y
  que se propague a metadatos, vectores y object store.
- **Si la visión/embeddings van a un proveedor externo**, debe quedar claro qué
  sale del dispositivo y ofrecer alternativa local (p. ej. modelos locales).

---

## 11. Stack tecnológico propuesto

Propuesta inicial, todo sustituible. Prioridad: empezar simple y local.

- **Lenguaje:** Python (ecosistema de IA/datos maduro).
- **Ingesta:** importadores como módulos con interfaz común
  (`Importer.iter_events() -> Iterable[RawEvent]`).
- **Metadatos:** SQLite (→ Postgres al escalar).
- **Vectores:** sqlite-vec o FAISS local (→ Qdrant/pgvector).
- **Object store:** carpeta content-addressed local (→ S3/MinIO).
- **Visión / captions:** modelo multimodal (local u online, configurable).
- **Transcripción:** Whisper (local).
- **OCR:** Tesseract o el propio modelo de visión.
- **Embeddings:** modelo de embeddings de texto (y de imagen para fotos).
- **Asistente:** servidor **MCP** (SDK de MCP) + Claude como LLM.

---

## 12. Riesgos y decisiones abiertas

- **¿Procesado de visión/transcripción local u online?** Afecta a coste,
  privacidad y velocidad. Recomendación: local por defecto, online opt-in.
- **Volumen de fotos/vídeos.** Miles de imágenes = coste de análisis y
  almacenamiento. Necesita batching, caché y priorización.
- **Calidad de la línea temporal de WhatsApp.** El `.txt` exportado tiene formato
  variable por idioma/plataforma; el parser debe ser robusto.
- **Resolución de identidad de personas** entre fuentes (el "Juan" de WhatsApp y
  el de las fotos). Empezar simple (por nombre/teléfono), mejorar después.
- **Detección de duplicados** entre fuentes (misma foto en Photos y WhatsApp):
  resuelto en parte por el object store content-addressed.
- **Migraciones de esquema** a medida que evoluciona `schema_version`.

---

## 13. Decisiones de producto (local, gratis, autoinstalable)

Prisma es deliberadamente **local-first, gratuito y privado**. Decisiones tomadas:

- **100% local y offline.** Toda la IA (descripción de imágenes, transcripción,
  embeddings) usa modelos locales gratuitos. **Nada de tus datos sale del equipo**
  y no hay APIs de pago. Backend de IA enchufable:
  - `null` (por defecto): no analiza; solo metadatos.
  - `ollama`: describe imágenes con un modelo de visión local (p. ej. `llava`),
    vía el servidor local de Ollama. Degrada con elegancia si Ollama no está.
  - (futuro) Whisper para audio/vídeo y Tesseract para OCR, también locales.
- **macOS primero.** El código es multiplataforma (Python puro), pero el
  onboarding, las pistas de instalación (Homebrew) y las pruebas se pulen para Mac
  primero; Windows/Linux después, reutilizando casi todo.
- **Instalación con pipx.** `pipx install prisma-context` deja el CLI `prisma`
  aislado y limpio. El propio CLI ayuda a instalar lo demás (Ollama, Whisper…).
- **Onboarding guiado.** `prisma setup` (asistente), `prisma doctor` (diagnóstico
  de entorno) y `prisma connect <fuente>` (guía amena, paso a paso, para exportar
  de cada app, con la nota de seguridad sobre tokens).
- **Secretos seguros (`prisma/secrets.py`).** Un token nunca se escribe en texto
  plano en disco. Dos backends: **Llavero de macOS** (opt-in, cifrado por el
  sistema) o **solo memoria** (efímero). El usuario apunta el secreto en su libreta;
  Prisma solo pide el valor al sistema en el momento de la petición.
- **VPS + dominio = distribución.** La infraestructura propia (p. ej. un VPS sin
  GPU) se reserva para alojar el instalador, la web/documentación y los modelos a
  descargar — **nunca para procesar datos personales**, que se quedan en el Mac
  (donde además la GPU integrada acelera los modelos locales).

---

*Documento vivo. Se actualizará conforme avancen las fases del roadmap.*
