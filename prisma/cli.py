"""CLI de Prisma.

Comandos:

    prisma setup                         Asistente inicial: te lleva de la mano.
    prisma doctor                        Comprueba el entorno (Python, Ollama, etc.).
    prisma connect FUENTE                Te explica cómo exportar de cada app.
    prisma init                          Crea la estructura de carpetas (buzón + datos).
    prisma ingest --importer X RUTA      Ingiere un archivo/carpeta con un importador.
    prisma stats                         Muestra el conteo de eventos por fuente.
    prisma search "texto"                Busca por subcadena (provisional, pre-embeddings).
    prisma timeline [--since ... --until ...]   Lista eventos por orden cronológico.
    prisma secret set|get|rm NOMBRE      Guarda secretos en el Llavero (macOS).

La raíz de datos se controla con ``--home`` o la variable ``PRISMA_HOME``.
Todo corre en local: tus datos no salen de tu equipo.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from prisma import __version__
from prisma.analysis import get_analyzer
from prisma.embeddings import get_embedder
from prisma.config import Config
from prisma.importers import REGISTRY
from prisma.ingest import Pipeline
from prisma.onboarding import check_environment, connect_guide, CONNECT_GUIDES
from prisma.secrets import get_secret_store, keychain_available
from prisma.storage import MetadataStore, ObjectStore


def _store(cfg: Config) -> MetadataStore:
    cfg.ensure_dirs()
    return MetadataStore(cfg.db_path)


def cmd_init(args: argparse.Namespace, cfg: Config) -> int:
    cfg.ensure_dirs()
    print(f"Prisma inicializado en {cfg.home}")
    print(f"  buzón (inbox): {cfg.inbox}")
    print(f"  datos:         {cfg.data}")
    print("\nSuelta tus exports en el buzón y luego usa `prisma ingest`.")
    return 0


def cmd_ingest(args: argparse.Namespace, cfg: Config) -> int:
    importer_cls = REGISTRY.get(args.importer)
    if importer_cls is None:
        print(
            f"Importador desconocido: {args.importer!r}. "
            f"Disponibles: {', '.join(sorted(REGISTRY))}",
            file=sys.stderr,
        )
        return 2
    path = Path(args.path)
    if not path.exists():
        print(f"No existe la ruta: {path}", file=sys.stderr)
        return 2

    cfg.ensure_dirs()
    objects = ObjectStore(cfg.objects_dir)

    # Opciones específicas de algunos importadores (p. ej. WhatsApp).
    extra = {}
    if args.importer == "whatsapp":
        if args.me:
            extra["me"] = args.me
        if args.chat_name:
            extra["chat_name"] = args.chat_name
    importer = importer_cls(source_path=path, objects=objects, **extra)

    try:
        analyzer = get_analyzer(args.analyzer)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 2
    analyzer.configure(cfg)  # p. ej. el reconocimiento facial necesita cfg.faces_dir
    with _store(cfg) as store:
        result = Pipeline(store, objects=objects, analyzer=analyzer).ingest(importer)
    print(result)
    return 0


def cmd_doctor(args: argparse.Namespace, cfg: Config) -> int:
    print("🩺 Diagnóstico del entorno de Prisma\n")
    statuses = check_environment()
    for s in statuses:
        print(f"  {s.mark}  {s.name} — {s.detail}")
        if not s.ok:
            print(f"        ↳ {s.why}")
            print(f"        ↳ instalar: {s.install_hint}")
    required_ok = all(s.ok for s in statuses if s.required)
    print()
    if required_ok:
        print("✅ Lo esencial está listo. Lo demás es opcional (mejora la 'magia').")
    else:
        print("❌ Falta algo esencial; revisa lo marcado arriba.")
    return 0 if required_ok else 1


def cmd_setup(args: argparse.Namespace, cfg: Config) -> int:
    print("👋 ¡Bienvenido a Prisma! Voy a dejarte todo a punto.\n")
    cfg.ensure_dirs()
    print(f"📂 Tu carpeta buzón es:  {cfg.inbox}")
    print("   (deja ahí los exports que vayas descargando)\n")
    cmd_doctor(args, cfg)
    print("\n🔐 Secretos:", "Llavero de macOS disponible." if keychain_available()
          else "se usarán solo en memoria (no se escriben a disco).")
    print("\n👉 Siguiente paso: elige una fuente y te guío para exportarla:")
    for src in CONNECT_GUIDES:
        print(f"     prisma connect {src}")
    return 0


def cmd_connect(args: argparse.Namespace, cfg: Config) -> int:
    guide = connect_guide(args.source)
    if guide is None:
        print(f"No tengo guía para {args.source!r}. "
              f"Disponibles: {', '.join(CONNECT_GUIDES)}", file=sys.stderr)
        return 2
    print(guide)
    return 0


def cmd_mcp(args: argparse.Namespace, cfg: Config) -> int:
    """Arranca el servidor MCP (stdio) para conectar tu contexto a Claude."""
    from prisma.mcp import McpServer
    # Aviso por stderr (stdout queda reservado para el protocolo JSON-RPC).
    print("🧠 Prisma MCP en marcha (stdio). Conéctalo desde tu cliente MCP.",
          file=sys.stderr)
    cfg.ensure_dirs()
    objects = ObjectStore(cfg.objects_dir)
    with _store(cfg) as store:
        McpServer(store, embedder_name=args.embedder,
                  objects=objects, render_dir=cfg.render_dir).serve_stdio()
    return 0


def cmd_secret(args: argparse.Namespace, cfg: Config) -> int:
    store = get_secret_store(use_keychain=not args.no_keychain)
    where = "Llavero de macOS" if store.persistent else "memoria (efímero)"
    if args.action == "set":
        value = getpass.getpass(f"Valor para «{args.name}» (no se mostrará): ")
        store.set(args.name, value)
        print(f"✅ Guardado en {where}.")
        if not store.persistent:
            print("ℹ️  Es efímero: apúntalo en tu libreta; no se guarda en disco.")
        return 0
    if args.action == "get":
        val = store.get(args.name)
        if val is None:
            print(f"No hay secreto «{args.name}» en {where}.", file=sys.stderr)
            return 1
        print(val)
        return 0
    if args.action == "rm":
        ok = store.delete(args.name)
        print("✅ Borrado." if ok else "No existía.")
        return 0
    return 2


def cmd_stats(args: argparse.Namespace, cfg: Config) -> int:
    with _store(cfg) as store:
        counts = store.counts_by_source()
        total = store.count()
    if not counts:
        print("Aún no hay eventos. Usa `prisma ingest` para añadir datos.")
        return 0
    width = max(len(s) for s in counts)
    for source, n in counts.items():
        print(f"  {source.ljust(width)}  {n}")
    print(f"  {'TOTAL'.ljust(width)}  {total}")
    return 0


def cmd_index(args: argparse.Namespace, cfg: Config) -> int:
    """Genera embeddings de los eventos que aún no los tienen (incremental)."""
    try:
        embedder = get_embedder(args.embedder)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 2
    space = embedder.key
    done = failed = 0
    with _store(cfg) as store:
        pending = list(store.iter_unembedded(space))
        if not pending:
            print(f"Nada que indexar: todo al día en el espacio «{space}».")
            return 0
        print(f"Indexando {len(pending)} eventos con «{space}»…")
        for ev in pending:
            text = ev.content if not ev.title else f"{ev.title}\n{ev.content}"
            try:
                store.add_embedding(ev.id, space, embedder.embed(text))
                done += 1
            except Exception as exc:  # p. ej. Ollama no disponible
                print(f"⚠️  {exc}", file=sys.stderr)
                failed += 1
                if failed == 1 and args.embedder == "ollama":
                    print("   ↳ ¿Está Ollama en marcha? "
                          "brew install ollama && ollama pull nomic-embed-text",
                          file=sys.stderr)
                    break
        total = store.count_embeddings(space)
    print(f"✅ {done} indexados ({total} en total).")
    return 0 if failed == 0 else 1


def cmd_search(args: argparse.Namespace, cfg: Config) -> int:
    with _store(cfg) as store:
        if args.semantic:
            try:
                embedder = get_embedder(args.embedder)
            except KeyError as exc:
                print(exc, file=sys.stderr)
                return 2
            try:
                qvec = embedder.embed(args.query)
            except Exception as exc:  # p. ej. Ollama no disponible
                print(f"No pude generar el embedding de la consulta: {exc}\n"
                      f"   ↳ ¿Está Ollama en marcha? Prueba con "
                      f"--embedder hashing para una búsqueda léxica offline.",
                      file=sys.stderr)
                return 1
            scored = store.vector_search(qvec, embedder.key, limit=args.limit)
            if not scored:
                print("Sin resultados. ¿Has ejecutado `prisma index` primero?")
                return 0
            for ev, score in scored:
                snippet = (ev.content or ev.title or "").replace("\n", " ")
                if len(snippet) > 90:
                    snippet = snippet[:87] + "..."
                print(f"  {score:.2f}  {ev.timestamp}  [{ev.source}/{ev.type}]  {snippet}")
            return 0
        results = store.search(args.query, limit=args.limit)
    if not results:
        print("Sin resultados.")
        return 0
    for ev in results:
        snippet = (ev.content or ev.title or "").replace("\n", " ")
        if len(snippet) > 100:
            snippet = snippet[:97] + "..."
        print(f"  {ev.timestamp}  [{ev.source}/{ev.type}]  {snippet}")
    return 0


def cmd_timeline(args: argparse.Namespace, cfg: Config) -> int:
    with _store(cfg) as store:
        events = list(
            store.timeline(
                since=args.since, until=args.until,
                source=args.source, limit=args.limit,
            )
        )
    if not events:
        print("Sin eventos en ese rango.")
        return 0
    for ev in events:
        snippet = (ev.content or ev.title or "").replace("\n", " ")
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        print(f"  {ev.timestamp}  [{ev.source}/{ev.type}]  {snippet}")
    return 0


def cmd_enroll(args: argparse.Namespace, cfg: Config) -> int:
    """Enrola una cara (p. ej. la tuya, 'me') desde fotos de referencia."""
    from prisma.analysis.faces import FaceRecognitionMatcher, FaceStore
    cfg.ensure_dirs()
    paths = []
    for raw in args.images:
        p = Path(raw)
        if p.is_dir():
            paths += [q for q in sorted(p.rglob("*"))
                      if q.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".heic")]
        elif p.is_file():
            paths.append(p)
    if not paths:
        print("No encontré imágenes de referencia.", file=sys.stderr)
        return 2
    matcher = FaceRecognitionMatcher(FaceStore(cfg.faces_dir))
    added = matcher.enroll(args.name, paths)
    if added == 0:
        print("No pude enrolar ninguna cara. ¿Está instalado face_recognition y "
              "se ven caras claras en las fotos?", file=sys.stderr)
        return 1
    print(f"✅ Enrolé «{args.name}» con {added} cara(s) de {len(paths)} foto(s).")
    return 0


def _photo_filter_events(store, args):
    return store.photos_where(
        only_me=True if args.only_me else None,
        max_people=args.max_people,
        no_animals=args.no_animals,
        limit=args.limit,
    )


def cmd_photos(args: argparse.Namespace, cfg: Config) -> int:
    """Lista fotos por atributos (p. ej. --only-me --no-animals)."""
    with _store(cfg) as store:
        events = _photo_filter_events(store, args)
    if not events:
        print("Sin fotos que cumplan el filtro. ¿Ingeriste con --analyzer attrs/local?")
        return 0
    for ev in events:
        d = ev.derived
        tag = []
        if "people_count" in d:
            tag.append(f"{d['people_count']}p")
        if d.get("animals"):
            tag.append("animales:" + ",".join(d["animals"]))
        if d.get("is_only_me"):
            tag.append("solo-yo")
        meta = ev.source_meta.get("filename", "")
        print(f"  {ev.timestamp}  {meta}  [{' '.join(tag)}]")
    return 0


def _gather_images(store, objects, events) -> list[bytes]:
    blobs = []
    for ev in events:
        if ev.media:
            try:
                blobs.append(objects.get(ev.media[0]["ref"]))
            except (KeyError, OSError):
                pass
    return blobs


def cmd_collage(args: argparse.Namespace, cfg: Config) -> int:
    from prisma.render import make_collage, RenderError
    cfg.ensure_dirs()
    objects = ObjectStore(cfg.objects_dir)
    with _store(cfg) as store:
        events = _photo_filter_events(store, args)
        images = _gather_images(store, objects, events)
    out = Path(args.out) if args.out else cfg.render_dir / "collage.jpg"
    try:
        path = make_collage(images, out, cols=args.cols)
    except RenderError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    print(f"✅ Collage con {len(images)} fotos → {path}")
    return 0


def cmd_video(args: argparse.Namespace, cfg: Config) -> int:
    from prisma.render import make_video, RenderError
    cfg.ensure_dirs()
    objects = ObjectStore(cfg.objects_dir)
    with _store(cfg) as store:
        events = _photo_filter_events(store, args)
        images = _gather_images(store, objects, events)
    out = Path(args.out) if args.out else cfg.render_dir / "video.mp4"
    try:
        path = make_video(images, out, seconds_per_image=args.secs)
    except RenderError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    print(f"✅ Vídeo con {len(images)} fotos → {path}")
    return 0


def _add_photo_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--only-me", dest="only_me", action="store_true",
                        help="Solo fotos donde apareces tú solo (requiere enroll).")
    parser.add_argument("--max-people", dest="max_people", type=int,
                        help="Máximo de personas en la foto.")
    parser.add_argument("--no-animals", dest="no_animals", action="store_true",
                        help="Sin animales detectados.")
    parser.add_argument("--limit", type=int, default=500)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="prisma", description="Tu cerebro de contexto personal (100% local).")
    p.add_argument("--home", help="Raíz de datos (o variable PRISMA_HOME).")
    p.add_argument("--version", action="version", version=f"prisma {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="Asistente inicial: te lleva de la mano.")
    sub.add_parser("doctor", help="Comprueba el entorno (Python, Ollama, etc.).")

    pc = sub.add_parser("connect", help="Te explica cómo exportar de cada app.")
    pc.add_argument("source", help=f"Fuente: {', '.join(CONNECT_GUIDES)}")

    sub.add_parser("init", help="Crea la estructura de carpetas.")

    pi = sub.add_parser("ingest", help="Ingiere un archivo/carpeta con un importador.")
    pi.add_argument("--importer", default="jsonl", help="Nombre del importador.")
    pi.add_argument(
        "--analyzer", default="null",
        help="Análisis de medios: null (def.) | ollama | ocr | whisper | detect | attrs | local.",
    )
    pi.add_argument("--me", help="(WhatsApp) Tu nombre tal cual aparece, para marcarte como «yo».")
    pi.add_argument("--chat-name", dest="chat_name", help="(WhatsApp) Nombre del chat/grupo.")
    pi.add_argument("path", help="Ruta al export/archivo/carpeta a ingerir.")

    sub.add_parser("stats", help="Conteo de eventos por fuente.")

    pidx = sub.add_parser("index", help="Genera embeddings para la búsqueda semántica.")
    pidx.add_argument("--embedder", default="ollama",
                      help="Embedder: ollama (IA local, def.) | hashing (offline).")

    ps = sub.add_parser("search", help="Busca por texto o por significado (--semantic).")
    ps.add_argument("query")
    ps.add_argument("--semantic", action="store_true",
                    help="Búsqueda por significado (requiere `prisma index` antes).")
    ps.add_argument("--embedder", default="ollama", help="Embedder a usar con --semantic.")
    ps.add_argument("--limit", type=int, default=50)

    pt = sub.add_parser("timeline", help="Lista eventos por orden cronológico.")
    pt.add_argument("--since")
    pt.add_argument("--until")
    pt.add_argument("--source")
    pt.add_argument("--limit", type=int, default=100)

    pmcp = sub.add_parser("mcp", help="Arranca el servidor MCP para conectar a Claude.")
    pmcp.add_argument("--embedder", default="ollama",
                      help="Embedder para la búsqueda semántica del MCP.")

    psec = sub.add_parser("secret", help="Gestiona secretos en el Llavero (macOS).")
    psec.add_argument("action", choices=["set", "get", "rm"])
    psec.add_argument("name")
    psec.add_argument("--no-keychain", action="store_true",
                      help="No usar el Llavero; mantener el secreto solo en memoria.")

    pen = sub.add_parser("enroll", help="Enrola una cara (p. ej. la tuya) desde fotos.")
    pen.add_argument("name", help="Etiqueta de identidad (usa 'me' para ti).")
    pen.add_argument("images", nargs="+", help="Fotos o carpeta de referencia.")

    pph = sub.add_parser("photos", help="Lista fotos por atributos (--only-me, etc.).")
    _add_photo_filters(pph)

    pcol = sub.add_parser("collage", help="Crea un collage con las fotos del filtro.")
    _add_photo_filters(pcol)
    pcol.add_argument("--out", help="Fichero de salida (por defecto en render/).")
    pcol.add_argument("--cols", type=int, help="Nº de columnas del collage.")

    pvid = sub.add_parser("video", help="Crea un vídeo/slideshow con las fotos del filtro.")
    _add_photo_filters(pvid)
    pvid.add_argument("--out", help="Fichero de salida (por defecto en render/).")
    pvid.add_argument("--secs", type=float, default=2.0, help="Segundos por foto.")

    return p


_DISPATCH = {
    "setup": cmd_setup,
    "doctor": cmd_doctor,
    "connect": cmd_connect,
    "init": cmd_init,
    "ingest": cmd_ingest,
    "stats": cmd_stats,
    "index": cmd_index,
    "search": cmd_search,
    "timeline": cmd_timeline,
    "mcp": cmd_mcp,
    "secret": cmd_secret,
    "enroll": cmd_enroll,
    "photos": cmd_photos,
    "collage": cmd_collage,
    "video": cmd_video,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.from_env(args.home)
    return _DISPATCH[args.command](args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
