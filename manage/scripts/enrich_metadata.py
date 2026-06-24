"""
enrich_metadata.py — Enrich index.json entries with metadata from Semantic Scholar.

Reads a library index.json, queries Semantic Scholar for each paper's
DOI, and fills in missing fields (abstract, citation_count, year, authors).
Entries already having `citation_count` are skipped (idempotent).

Semantic Scholar public API requires no key for basic lookups.
Rate limit: ~100 req/5 min unauthenticated; set S2_API_KEY env var for higher limits.
A 1 s sleep between calls keeps usage well within limits.

Usage:
    python3 enrich_metadata.py --input index.json --output index.json
    python3 enrich_metadata.py --input index.json --output enriched.json --dry-run

Environment variables:
    S2_API_KEY   — Semantic Scholar API key (optional, raises rate limits)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1/paper"
FIELDS = "title,abstract,year,authors,citationCount"
REQUEST_TIMEOUT = 15  # seconds
INTER_REQUEST_SLEEP = 1.0  # seconds between API calls


# ---------------------------------------------------------------------------
# Semantic Scholar fetch
# ---------------------------------------------------------------------------

def fetch_from_semantic_scholar(doi: str) -> dict[str, Any] | None:
    """Fetch paper metadata from Semantic Scholar by DOI.

    Returns a dict with keys: title, abstract, year, authors, citationCount,
    or None if the paper is not found or the request fails.
    """
    url = f"{SEMANTIC_SCHOLAR_BASE}/{doi}?fields={FIELDS}"
    headers: dict[str, str] = {}
    api_key = os.environ.get("S2_API_KEY", "")
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
    except requests.exceptions.RequestException as e:
        log.error("Semantic Scholar request failed for %s: %s", doi, e)
        return None


# ---------------------------------------------------------------------------
# Enrich a single index entry
# ---------------------------------------------------------------------------

def enrich_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Enrich a single index.json entry in-place using Semantic Scholar.

    Fields updated (only when missing/empty):
      - abstract
      - year
      - authors
      - citation_count   (always refreshed if S2 returns a value)

    Returns the (possibly modified) entry.
    """
    doi = entry.get("doi", "").strip()
    if not doi:
        log.debug("Entry '%s' has no DOI; skipping.", entry.get("id", "?"))
        return entry

    # Skip if already fully enriched
    if entry.get("citation_count") is not None:
        log.debug("Entry '%s' already has citation_count; skipping.", entry.get("id", doi))
        return entry

    ss = fetch_from_semantic_scholar(doi)
    if ss is None:
        return entry

    # Fill missing fields (don't overwrite existing values)
    if not entry.get("abstract") and ss.get("abstract"):
        entry["abstract"] = ss["abstract"]

    if not entry.get("year") and ss.get("year"):
        entry["year"] = ss["year"]

    if not entry.get("authors") and ss.get("authors"):
        entry["authors"] = [a.get("name", "") for a in ss["authors"]]

    # citation_count is always refreshed (it changes over time)
    if ss.get("citationCount") is not None:
        entry["citation_count"] = ss["citationCount"]

    return entry


# ---------------------------------------------------------------------------
# Batch enrichment
# ---------------------------------------------------------------------------

def enrich_index(entries: list[dict[str, Any]], dry_run: bool = False) -> list[dict[str, Any]]:
    """Enrich a list of index entries. Returns updated entries."""
    total = len(entries)
    enriched_count = 0

    for i, entry in enumerate(entries):
        doi = entry.get("doi", "").strip()
        if not doi:
            continue

        if entry.get("citation_count") is not None:
            log.debug("[%d/%d] Skipping (already enriched): %s", i + 1, total, doi)
            continue

        log.info("[%d/%d] Enriching: %s", i + 1, total, doi)

        if not dry_run:
            enrich_entry(entry)
            enriched_count += 1
        else:
            log.info("  [dry-run] Would enrich %s", doi)

        if i < total - 1:
            time.sleep(INTER_REQUEST_SLEEP)

    log.info("Enriched %d/%d entries.", enriched_count, total)
    return entries


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich a library index.json with Semantic Scholar metadata."
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="FILE",
        help="Path to input index.json.",
    )
    parser.add_argument(
        "--output",
        required=True,
        metavar="FILE",
        help="Path to write enriched index.json (may be same as --input for in-place update).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print which entries would be enriched without calling the API or writing files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        sys.exit(1)

    with input_path.open(encoding="utf-8") as f:
        data = json.load(f)

    # Support both a bare list and a dict with a "papers" key
    if isinstance(data, list):
        entries = data
        wrapper = None
    elif isinstance(data, dict) and "papers" in data:
        entries = data["papers"]
        wrapper = data
    else:
        log.error("Unrecognised index.json format (expected list or {papers: [...]})")
        sys.exit(1)

    log.info("Loaded %d entries from %s", len(entries), input_path)
    enrich_index(entries, dry_run=args.dry_run)

    if not args.dry_run:
        if wrapper is not None:
            wrapper["papers"] = entries
            output_data = wrapper
        else:
            output_data = entries

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        log.info("Wrote enriched index to %s", output_path)
    else:
        log.info("[dry-run] No files written.")


if __name__ == "__main__":
    main()
