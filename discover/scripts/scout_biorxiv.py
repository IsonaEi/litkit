#!/usr/bin/env python3
"""scout_biorxiv.py — bioRxiv scout for the discover tool.

Fetches recent preprints from the bioRxiv REST API and filters by keyword.
Outputs a JSON array of papers to stdout.

Usage:
    python3 scout_biorxiv.py          # normal run
    python3 scout_biorxiv.py --test   # return 2 dummy papers, no network
"""

import json
import sys
import datetime

from config import LITKIT_CONFIG
from scout_utils import load_config, all_keywords, keyword_hits, paper_schema

# ── Dependency imports ──────────────────────────────────────────────────────

try:
    import requests
except ImportError:
    requests = None
    print("[scout_biorxiv] WARNING: requests not installed. Run: pip install requests", file=sys.stderr)

# ── Test mode ────────────────────────────────────────────────────────────────


def dummy_papers() -> list[dict]:
    today = datetime.date.today().isoformat()
    return [
        paper_schema(
            title="[TEST] Theta-gamma coupling during spatial navigation in the entorhinal cortex",
            authors=["Test Author X", "Test Author Y"],
            date=today,
            url="https://www.biorxiv.org/content/10.1101/2026.01.01.000001",
            doi="10.1101/2026.01.01.000001",
            abstract_snippet="A test abstract about theta-gamma coupling and entorhinal cortex.",
            citation_count=None,
            keyword_hits_list=["theta-gamma coupling", "entorhinal cortex", "spatial navigation"],
            source="biorxiv",
        ),
        paper_schema(
            title="[TEST] Optogenetic dissection of hippocampal circuits during remapping",
            authors=["Test Author Z"],
            date=today,
            url="https://www.biorxiv.org/content/10.1101/2026.01.01.000002",
            doi="10.1101/2026.01.01.000002",
            abstract_snippet="A test abstract about optogenetics and hippocampal remapping.",
            citation_count=None,
            keyword_hits_list=["optogenetics", "hippocampus", "remapping"],
            source="biorxiv",
        ),
    ]


# ── bioRxiv query ─────────────────────────────────────────────────────────────


def query_biorxiv(keywords: list[str], since_date: str, max_results: int) -> list[dict]:
    if requests is None:
        print("[scout_biorxiv] ERROR: requests not available.", file=sys.stderr)
        return []

    today = datetime.date.today().isoformat()
    # bioRxiv API interval format: YYYY-MM-DD/YYYY-MM-DD
    url = f"https://api.biorxiv.org/details/biorxiv/{since_date}/{today}/0"

    print(f"[scout_biorxiv] Fetching: {url}", file=sys.stderr)

    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"[scout_biorxiv] ERROR: {exc}", file=sys.stderr)
        return []

    collection = data.get("collection", [])
    print(f"[scout_biorxiv] {len(collection)} preprints in date window.", file=sys.stderr)

    results: list[dict] = []
    seen_dois: set[str] = set()

    for item in collection:
        title = item.get("title", "")
        abstract = item.get("abstract", "")
        doi = item.get("doi", "") or None

        combined_text = (title + " " + abstract).lower()
        if not any(kw.lower() in combined_text for kw in keywords):
            continue

        if doi and doi in seen_dois:
            continue
        if doi:
            seen_dois.add(doi)

        date_str = item.get("date", datetime.date.today().isoformat())

        # Authors: field is a single string "Last, First; Last2, First2"
        raw_authors = item.get("authors", "")
        authors = [a.strip() for a in raw_authors.split(";") if a.strip()] if raw_authors else []

        url_paper = f"https://www.biorxiv.org/content/{doi}" if doi else ""
        hits = keyword_hits(title, abstract, keywords)

        results.append(
            paper_schema(
                title=title,
                authors=authors,
                date=date_str,
                url=url_paper,
                doi=doi,
                abstract_snippet=abstract[:300],
                citation_count=None,
                keyword_hits_list=hits,
                source="biorxiv",
            )
        )

        if len(results) >= max_results:
            break

    print(f"[scout_biorxiv] Done — {len(results)} papers.", file=sys.stderr)
    return results


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    if "--test" in sys.argv:
        print(json.dumps(dummy_papers(), indent=2))
        return

    cfg = load_config(LITKIT_CONFIG)
    lookback = cfg.get("lookback_days", 7)
    since_date = (datetime.date.today() - datetime.timedelta(days=lookback)).isoformat()
    keywords = all_keywords(cfg)
    max_results = cfg.get("biorxiv_max_results", 30)

    papers = query_biorxiv(keywords, since_date, max_results)
    print(json.dumps(papers, indent=2))


if __name__ == "__main__":
    main()
