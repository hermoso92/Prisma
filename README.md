# Prisma

> Tu **cerebro de contexto personal**: un asistente que conoce todo tu mundo digital
> —chats de ChatGPT y Claude, WhatsApp, notas, fotos y vídeos— lo entiende, lo
> indexa y te deja preguntarle cualquier cosa sobre tu propia vida.

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

1. **Local-first.** Tus datos son tuyos. Por defecto todo se procesa y guarda en
   local; lo que salga a la nube (p. ej. un modelo de visión) es decisión
   explícita y configurable.
2. **Esquema común antes que features.** El 80 % del valor está en normalizar
   todo a una misma línea temporal para poder *cruzar* fuentes.
3. **Rebanadas verticales.** Una fuente de punta a punta antes que diez a medias.
4. **Solo vías oficiales.** Nada de scraping ni de saltarse términos de servicio.
5. **Privacidad y consentimiento.** Cifrado en reposo, secretos en vault,
   consentimiento por conector. Cumplimiento GDPR (datos de terceros en WhatsApp).

---

## Estado actual

🚧 **Fase de diseño.** Este repositorio contiene de momento el documento de
arquitectura y el plan por fases. Ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
y el [roadmap](docs/ARCHITECTURE.md#9-plan-por-fases-roadmap).

## Documentación

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — diseño técnico completo,
  esquema común, pipeline, seguridad y roadmap.
