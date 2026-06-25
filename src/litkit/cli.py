"""Human-facing command-line interface for litkit.

Thin wrappers that call the pure stage functions and print. Exposed both as the
``litkit-discover`` / ``litkit-search`` / ``litkit-ingest`` / ``litkit-enrich``
console scripts and as ``python -m litkit.cli <stage> ...``.

Preserves the original per-stage CLI UX:
- discover: --once (default), --cron, --test, --query, --output, --sources
- search:   query positional, --top-k, --format json|text, --section-filter
- ingest:   --corpus, --dry-run, --force
- enrich:   --input/--output (or --library), --dry-run, --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


# ── discover ──────────────────────────────────────────────────────────────────

def discover_main(argv: list[str] | None = None) -> int:
    from litkit.discover import orchestrator

    parser = argparse.ArgumentParser(prog="litkit-discover", description="litkit discover stage")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run once, print digest to stdout (default)")
    mode.add_argument("--cron", action="store_true", help="Scheduled run: write JSON + digest to LITKIT_OUTPUT")
    mode.add_argument("--test", action="store_true", help="Use dummy data from all sources (no network)")

    parser.add_argument("--query", type=str, default=None, help="Override search with a custom query term")
    parser.add_argument("--output", type=str, default=None, help="Write the digest to this path instead of stdout")
    parser.add_argument("--sources", type=str, default=None, help="Comma-separated sources (default: all)")
    args = parser.parse_args(argv)

    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    sources = [s for s in args.sources.split(",")] if args.sources else None

    if args.cron:
        summary = orchestrator.run_cron(sources=sources)
        print(f"[litkit-discover] Digest written to {summary['digest_path']}", file=sys.stderr)
        print(f"[litkit-discover] {summary['candidate_count']} candidates "
              f"→ {summary['candidates_path']}", file=sys.stderr)
        return 0

    digest = orchestrator.run_once(query=args.query, sources=sources, test_mode=args.test)
    if args.output:
        Path(args.output).write_text(digest)
        print(f"[litkit-discover] Digest written to {args.output}", file=sys.stderr)
    else:
        print(digest)
    return 0


# ── search ──────────────────────────────────────────────────────────────────

def search_main(argv: list[str] | None = None) -> int:
    from litkit.search.ingest import SearchDependencyError
    from litkit.search.query import SearchIndexError, format_text, search

    parser = argparse.ArgumentParser(prog="litkit-search", description="Search the ingested corpus")
    parser.add_argument("query", help="Query text")
    parser.add_argument("--top-k", type=int, default=8, help="Number of results (default: 8)")
    parser.add_argument("--format", choices=["json", "text"], default="json",
                        help="Output format: json (default) or text")
    parser.add_argument("--section-filter", metavar="SECTION", default=None,
                        help="Restrict to a section type (Abstract, Introduction, Methods, "
                             "Results, Discussion, References, Other)")
    args = parser.parse_args(argv)

    try:
        results = search(query=args.query, top_k=args.top_k, section=args.section_filter)
    except (SearchDependencyError, SearchIndexError) as exc:
        print(f"[litkit-search] ERROR: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(format_text(args.query, results))
    return 0


# ── ingest ──────────────────────────────────────────────────────────────────

def ingest_main(argv: list[str] | None = None) -> int:
    from litkit.search.ingest import SearchDependencyError, ingest

    parser = argparse.ArgumentParser(prog="litkit-ingest", description="Ingest a corpus into the search index")
    parser.add_argument("--corpus", default=None, help="Override LIT_QUERY_CORPUS")
    parser.add_argument("--dry-run", action="store_true", help="List files without embedding")
    parser.add_argument("--force", action="store_true", help="Re-ingest all files, ignoring the manifest")
    args = parser.parse_args(argv)

    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    try:
        summary = ingest(corpus_dir=args.corpus, dry_run=args.dry_run, force=args.force)
    except SearchDependencyError as exc:
        print(f"[litkit-ingest] ERROR: {exc}", file=sys.stderr)
        return 1

    status = summary.get("status")
    if status == "error":
        print(f"[litkit-ingest] ERROR: {summary.get('message')}", file=sys.stderr)
        return 1
    if status == "no_files":
        print("[litkit-ingest] No PDF or MD files found in any corpus path.")
        return 0
    if status == "up_to_date":
        print("[litkit-ingest] All files are up-to-date. Nothing to do.")
        return 0
    if status == "dry_run":
        print(f"[litkit-ingest] Would process {summary['to_process']} file(s):")
        for name in summary["files"]:
            print(f"  [dry-run] {name}")
        return 0

    print(f"[litkit-ingest] Done — processed {summary['processed']} file(s), "
          f"{summary['chunks']} chunks.")
    return 0


# ── enrich ──────────────────────────────────────────────────────────────────

def enrich_main(argv: list[str] | None = None) -> int:
    from litkit.manage.enrich import enrich_library

    parser = argparse.ArgumentParser(prog="litkit-enrich",
                                     description="Enrich a library index.json with Semantic Scholar metadata")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", metavar="FILE", help="Path to input index.json")
    src.add_argument("--library", metavar="DIR", help="Library directory (uses <DIR>/index.json)")
    parser.add_argument("--output", metavar="FILE", default=None,
                        help="Path to write enriched index.json (default: in-place)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print which entries would be enriched without calling the API or writing")
    parser.add_argument("--verbose", action="store_true", help="Enable debug-level logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    try:
        summary = enrich_library(
            library_dir=args.library,
            index_path=args.input,
            output_path=args.output,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[litkit-enrich] ERROR: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[litkit-enrich] [dry-run] Would enrich {summary['enriched']}/{summary['total']} "
              f"entries (skipped {summary['skipped']}). No files written.")
    else:
        print(f"[litkit-enrich] Enriched {summary['enriched']}/{summary['total']} entries "
              f"→ {summary['output_path']}")
    return 0


# ── Combined dispatcher (python -m litkit.cli <stage> ...) ────────────────────

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Usage: python -m litkit.cli {discover|search|ingest|enrich} [options]", file=sys.stderr)
        return 1
    stage, rest = argv[0], argv[1:]
    dispatch = {
        "discover": discover_main,
        "search": search_main,
        "ingest": ingest_main,
        "enrich": enrich_main,
    }
    if stage not in dispatch:
        print(f"Unknown stage '{stage}'. Choose from: {', '.join(dispatch)}", file=sys.stderr)
        return 1
    return dispatch[stage](rest)


if __name__ == "__main__":
    raise SystemExit(main())
