"""Enrich a library index.json with metadata from Semantic Scholar.

For each paper's DOI, fills in missing fields (abstract, year, authors) and
refreshes citation_count. Entries already having ``citation_count`` are skipped
(idempotent). The ``requests`` dependency is imported lazily inside the fetch
function so importing this module never requires the ``manage`` extra.

Semantic Scholar's public API requires no key for basic lookups; set the
``S2_API_KEY`` env var for higher rate limits. A 1 s sleep between calls keeps
usage within limits.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from litkit.config import get_s2_api_key

log = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1/paper"
FIELDS = "title,abstract,year,authors,citationCount"
REQUEST_TIMEOUT = 15  # seconds
INTER_REQUEST_SLEEP = 1.0  # seconds between API calls


def fetch_from_semantic_scholar(doi: str) -> dict[str, Any] | None:
    """Fetch paper metadata from Semantic Scholar by DOI (or None on failure)."""
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - depends on extras
        raise ImportError(
            "requests is required for metadata enrichment. "
            "Install it with: pip install 'litkit[manage]'"
        ) from exc

    url = f"{SEMANTIC_SCHOLAR_BASE}/{doi}?fields={FIELDS}"
    headers: dict[str, str] = {}
    api_key = get_s2_api_key()
    if api_key:
        headers["x-api-key"] = api_key

    try:
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if r.status_code == 404:
            log.warning("Semantic Scholar: DOI not found: %s", doi)
            return None
        r.raise_for_status()
        data = r.json()
        log.info("Fetched S2 metadata for %s: %s", doi, data.get("title", "(no title)"))
        return data
    except Exception as e:  # requests.RequestException + JSON errors
        log.error("Semantic Scholar request failed for %s: %s", doi, e)
        return None


def enrich_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Enrich a single index.json entry in-place using Semantic Scholar.

    Only missing fields are filled; ``citation_count`` is always refreshed when
    S2 returns a value. Returns the (possibly modified) entry.
    """
    doi = entry.get("doi", "").strip()
    if not doi:
        return entry

    if entry.get("citation_count") is not None:
        return entry

    ss = fetch_from_semantic_scholar(doi)
    if ss is None:
        return entry

    if not entry.get("abstract") and ss.get("abstract"):
        entry["abstract"] = ss["abstract"]
    if not entry.get("year") and ss.get("year"):
        entry["year"] = ss["year"]
    if not entry.get("authors") and ss.get("authors"):
        entry["authors"] = [a.get("name", "") for a in ss["authors"]]
    if ss.get("citationCount") is not None:
        entry["citation_count"] = ss["citationCount"]

    return entry


def enrich_index(entries: list[dict[str, Any]], dry_run: bool = False) -> dict:
    """Enrich a list of index entries. Mutates ``entries`` and returns a summary.

    Returns ``{total, enriched, skipped, dry_run}``.
    """
    total = len(entries)
    enriched_count = 0
    skipped = 0

    for i, entry in enumerate(entries):
        doi = entry.get("doi", "").strip()
        if not doi:
            skipped += 1
            continue
        if entry.get("citation_count") is not None:
            skipped += 1
            continue

        log.info("[%d/%d] Enriching: %s", i + 1, total, doi)
        if not dry_run:
            enrich_entry(entry)
            enriched_count += 1
        else:
            log.info("  [dry-run] Would enrich %s", doi)
            enriched_count += 1

        if i < total - 1 and not dry_run:
            time.sleep(INTER_REQUEST_SLEEP)

    log.info("Enriched %d/%d entries.", enriched_count, total)
    return {
        "total": total,
        "enriched": enriched_count,
        "skipped": skipped,
        "dry_run": dry_run,
    }


def _load_index(path: Path) -> tuple[list[dict[str, Any]], dict | None]:
    """Load index.json, supporting a bare list or ``{"papers": [...]}``."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and "papers" in data:
        return data["papers"], data
    raise ValueError("Unrecognised index.json format (expected list or {papers: [...]})")


def enrich_library(
    library_dir: str | None = None,
    index_path: str | None = None,
    output_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Enrich a library's ``index.json`` from Semantic Scholar and write it back.

    Provide either ``library_dir`` (the index is ``<library_dir>/index.json``)
    or an explicit ``index_path``. ``output_path`` defaults to the input path
    (in-place update). Returns the enrichment summary plus the resolved paths.
    """
    if index_path:
        in_path = Path(index_path)
    elif library_dir:
        in_path = Path(library_dir) / "index.json"
    else:
        raise ValueError("Provide either library_dir or index_path.")

    if not in_path.exists():
        raise FileNotFoundError(f"index.json not found: {in_path}")

    out_path = Path(output_path) if output_path else in_path

    entries, wrapper = _load_index(in_path)
    log.info("Loaded %d entries from %s", len(entries), in_path)
    summary = enrich_index(entries, dry_run=dry_run)

    if not dry_run:
        output_data: Any = entries
        if wrapper is not None:
            wrapper["papers"] = entries
            output_data = wrapper
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        log.info("Wrote enriched index to %s", out_path)

    summary["index_path"] = str(in_path)
    summary["output_path"] = str(out_path)
    return summary
