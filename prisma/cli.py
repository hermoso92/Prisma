"""CLI de Prisma.

Comandos de la Fase 0:

    prisma init                          Crea la estructura de carpetas (buzón + datos).
    prisma ingest --importer jsonl FILE  Ingiere un archivo con un importador.
    prisma stats                         Muestra el conteo de eventos por fuente.
    prisma search "texto"                Busca por subcadena (provisional, pre-embeddings).
    prisma timeline [--since ... --until ...]   Lista eventos por orden cronológico.

La raíz de datos se controla con ``--home`` o la variable ``PRISMA_HOME``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from prisma.config import Config
from prisma.importers import REGISTRY
from prisma.ingest import Pipeline
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
    importer = importer_cls(source_path=path, objects=objects)
    with _store(cfg) as store:
        result = Pipeline(store).ingest(importer)
    print(result)
    return 0


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


def cmd_search(args: argparse.Namespace, cfg: Config) -> int:
    with _store(cfg) as store:
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="prisma", description="Tu cerebro de contexto personal.")
    p.add_argument("--home", help="Raíz de datos (o variable PRISMA_HOME).")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Crea la estructura de carpetas.")

    pi = sub.add_parser("ingest", help="Ingiere un archivo con un importador.")
    pi.add_argument("--importer", default="jsonl", help="Nombre del importador.")
    pi.add_argument("path", help="Ruta al export/archivo a ingerir.")

    sub.add_parser("stats", help="Conteo de eventos por fuente.")

    ps = sub.add_parser("search", help="Búsqueda por subcadena (provisional).")
    ps.add_argument("query")
    ps.add_argument("--limit", type=int, default=50)

    pt = sub.add_parser("timeline", help="Lista eventos por orden cronológico.")
    pt.add_argument("--since")
    pt.add_argument("--until")
    pt.add_argument("--source")
    pt.add_argument("--limit", type=int, default=100)

    return p


_DISPATCH = {
    "init": cmd_init,
    "ingest": cmd_ingest,
    "stats": cmd_stats,
    "search": cmd_search,
    "timeline": cmd_timeline,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.from_env(args.home)
    return _DISPATCH[args.command](args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
