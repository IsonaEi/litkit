"""Hybrid semantic + lexical search over the ingested corpus.

The pure entry point is :func:`search`, which returns a list of hit dicts (each
with ``rank``, ``score``, ``source``, ``section_type``, ``text`` and more).
Heavy dependencies (FlagEmbedding, qdrant-client) are imported lazily.
"""

from __future__ import annotations

import logging

from litkit.config import get_collection_name, get_db_path, get_embedding_model
from litkit.search.ingest import SearchDependencyError

log = logging.getLogger(__name__)


class SearchIndexError(RuntimeError):
    """Raised when the search index is missing or empty (run ingest first)."""


def _to_sparse_vector(lexical_weights: dict):
    """Convert BGE-M3 lexical_weights dict to a Qdrant SparseVector."""
    from qdrant_client import models

    indices = [int(k) for k in lexical_weights.keys()]
    values = list(lexical_weights.values())
    return models.SparseVector(indices=indices, values=values)


def search(
    query: str,
    top_k: int = 8,
    section: str | None = None,
) -> list[dict]:
    """Run hybrid (dense + sparse, RRF-fused) search and return result dicts.

    Parameters
    ----------
    query:
        Natural-language query text.
    top_k:
        Number of results to return.
    section:
        Optional section-type filter — one of Abstract, Introduction, Methods,
        Results, Discussion, References, Other.

    Returns
    -------
    list[dict]
        One dict per hit with ``rank``, ``score`` (RRF), ``title``, ``source``,
        ``section_type``, ``headings``, ``page``, ``year`` and ``text``.

    Raises
    ------
    SearchDependencyError
        If the search extras are not installed.
    SearchIndexError
        If the index does not exist yet or is empty.
    """
    try:
        from FlagEmbedding import BGEM3FlagModel
        from qdrant_client import QdrantClient, models
    except ImportError as exc:
        raise SearchDependencyError(
            f"missing search dependency — {exc}. "
            "Install it with: pip install 'litkit[search]'"
        ) from exc

    db_path = get_db_path()
    collection_name = get_collection_name()
    embedding_model = get_embedding_model()

    if not db_path.exists():
        raise SearchIndexError(
            f"Qdrant DB not found at {db_path}. Run ingest first (litkit-ingest)."
        )

    client = QdrantClient(path=str(db_path))

    existing = [c.name for c in client.get_collections().collections]
    if collection_name not in existing:
        raise SearchIndexError(
            f"Collection '{collection_name}' not found. Run ingest first (litkit-ingest)."
        )

    if client.count(collection_name=collection_name).count == 0:
        raise SearchIndexError(
            f"Collection '{collection_name}' is empty. Run ingest first (litkit-ingest)."
        )

    model = BGEM3FlagModel(embedding_model, use_fp16=True)
    output = model.encode([query], return_dense=True, return_sparse=True)
    query_dense = output["dense_vecs"][0].tolist()
    query_sparse = _to_sparse_vector(output["lexical_weights"][0])

    query_filter = None
    if section:
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="section_type",
                    match=models.MatchValue(value=section),
                )
            ]
        )

    prefetch = [
        models.Prefetch(query=query_dense, using="dense", limit=top_k * 3),
        models.Prefetch(query=query_sparse, using="sparse", limit=top_k * 3),
    ]

    raw_results = client.query_points(
        collection_name=collection_name,
        prefetch=prefetch,
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    ).points

    results: list[dict] = []
    for rank_, point in enumerate(raw_results, start=1):
        p = point.payload or {}
        results.append({
            "rank": rank_,
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


# ── Text formatter (used by the CLI) ──────────────────────────────────────────

def format_text(query: str, results: list[dict]) -> str:
    """Format search results as scannable plain text."""
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
