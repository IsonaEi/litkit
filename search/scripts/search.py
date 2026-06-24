"""
search.py — Hybrid semantic + lexical search over the ingested corpus.

Usage:
    python3 scripts/search.py "query text" [--top-k 8] [--format json|text] [--section-filter Methods]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    EMBEDDING_MODEL,
    LIT_QUERY_COLLECTION,
    LIT_QUERY_DB,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_sparse_vector(lexical_weights: dict):
    """Convert BGE-M3 lexical_weights dict to Qdrant SparseVector."""
    from qdrant_client import models

    indices = [int(k) for k in lexical_weights.keys()]
    values = list(lexical_weights.values())
    return models.SparseVector(indices=indices, values=values)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(
    query: str,
    top_k: int = 8,
    section_filter: str | None = None,
) -> list[dict]:
    """Run hybrid (dense + sparse RRF) search and return result dicts."""
    try:
        from FlagEmbedding import BGEM3FlagModel
        from qdrant_client import QdrantClient, models
    except ImportError as exc:
        print(f"[search] ERROR: missing dependency — {exc}", file=sys.stderr)
        print("         Run: pip install FlagEmbedding qdrant-client", file=sys.stderr)
        sys.exit(1)

    # --- Check DB exists ---
    if not LIT_QUERY_DB.exists():
        print(
            f"[search] ERROR: Qdrant DB not found at {LIT_QUERY_DB}\n"
            "         Run ingest first: python3 scripts/ingest.py",
            file=sys.stderr,
        )
        sys.exit(1)

    client = QdrantClient(path=str(LIT_QUERY_DB))

    # --- Check collection exists and has points ---
    existing = [c.name for c in client.get_collections().collections]
    if LIT_QUERY_COLLECTION not in existing:
        print(
            f"[search] ERROR: Collection '{LIT_QUERY_COLLECTION}' not found.\n"
            "         Run ingest first: python3 scripts/ingest.py",
            file=sys.stderr,
        )
        sys.exit(1)

    count = client.count(collection_name=LIT_QUERY_COLLECTION).count
    if count == 0:
        print(
            f"[search] ERROR: Collection '{LIT_QUERY_COLLECTION}' is empty.\n"
            "         Run ingest first: python3 scripts/ingest.py",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Embed query ---
    model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=True)
    output = model.encode(
        [query],
        return_dense=True,
        return_sparse=True,
    )
    query_dense = output["dense_vecs"][0].tolist()
    query_sparse = to_sparse_vector(output["lexical_weights"][0])

    # --- Build filter ---
    query_filter = None
    if section_filter:
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="section_type",
                    match=models.MatchValue(value=section_filter),
                )
            ]
        )

    # --- Hybrid search (RRF fusion) ---
    prefetch = [
        models.Prefetch(
            query=query_dense,
            using="dense",
            limit=top_k * 3,
        ),
        models.Prefetch(
            query=query_sparse,
            using="sparse",
            limit=top_k * 3,
        ),
    ]

    raw_results = client.query_points(
        collection_name=LIT_QUERY_COLLECTION,
        prefetch=prefetch,
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    ).points

    # --- Format output ---
    results = []
    for rank, point in enumerate(raw_results, start=1):
        p = point.payload or {}
        results.append({
            "rank": rank,
            "score": round(point.score, 6),
            "title": p.get("title", ""),
            "source": p.get("source", ""),
            "section_type": p.get("section_type", ""),
            "headings": p.get("headings"),
            "page": p.get("page"),
            "year": p.get("year"),
            "text": p.get("text", ""),
        })

    return results


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_json(results: list[dict]) -> str:
    return json.dumps(results, ensure_ascii=False, indent=2)


def format_text(query: str, results: list[dict]) -> str:
    lines = [f'Top {len(results)} results for: "{query}"\n']
    for r in results:
        page_str = f", p.{r['page']}" if r.get("page") is not None else ""
        year_str = f" ({r['year']})" if r.get("year") else ""
        lines.append(
            f"[{r['rank']}] {r['title']}{year_str}  "
            f"(score: {r['score']:.4f}, section: {r['section_type']}{page_str})"
        )
        lines.append(f"    Source: {r['source']}")
        snippet = r["text"][:200].replace("\n", " ")
        lines.append(f"    {snippet}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Search the ingested literature corpus.")
    parser.add_argument("query", help="Query text")
    parser.add_argument("--top-k", type=int, default=8, help="Number of results (default: 8)")
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format: json (default) or text",
    )
    parser.add_argument(
        "--section-filter",
        metavar="SECTION",
        help="Restrict to a section type (Abstract, Introduction, Methods, Results, Discussion, References)",
    )
    args = parser.parse_args()

    results = search(
        query=args.query,
        top_k=args.top_k,
        section_filter=args.section_filter,
    )

    if args.format == "json":
        print(format_json(results))
    else:
        print(format_text(args.query, results))


if __name__ == "__main__":
    main()
