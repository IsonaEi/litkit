#!/usr/bin/env python3
"""scout_arxiv.py — arXiv scout for the discover tool.

Searches arXiv cs.NE, q-bio.NC, q-bio.QM for recent papers matching keywords.
Uses the arXiv Atom API directly (no external arxiv library required).
Outputs a JSON array of papers to stdout.

Usage:
    python3 scout_arxiv.py            # normal run
    python3 scout_arxiv.py --test     # return 2 dummy papers, no network
"""

import json
import sys
import datetime
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError

from config import LITKIT_CONFIG
from scout_utils import load_config, all_keywords, keyword_hits, paper_schema

ARXIV_API = "http://export.arxiv.org/api/query"
CATEGORIES = ["cs.NE", "q-bio.NC", "q-bio.QM"]
ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"

# ── Test mode ────────────────────────────────────────────────────────────────


def dummy_papers() -> list[dict]:
    today = datetime.date.today().isoformat()
    return [
        paper_schema(
            title="[TEST] Continuous attractor network model of grid cell formation",
            authors=["Test Author P", "Test Author Q"],
            date=today,
            url="https://arxiv.org/abs/2601.00001",
            doi=None,
            abstract_snippet="A test abstract about continuous attractor networks and grid cells.",
            citation_count=None,
            keyword_hits_list=["continuous attractor model", "grid cells"],
            source="arxiv",
        ),
        paper_schema(
            title="[TEST] Neural manifold dimensionality reduction for place cell decoding",
            authors=["Test Author R"],
            date=today,
            url="https://arxiv.org/abs/2601.00002",
            doi=None,
            abstract_snippet="A test abstract about neural manifolds and place cell decoding.",
            citation_count=None,
            keyword_hits_list=["neural manifold", "place cells", "neural decoding"],
            source="arxiv",
        ),
    ]


# ── arXiv query ───────────────────────────────────────────────────────────────


def query_arxiv(keywords: list[str], since_date: str, max_results: int) -> list[dict]:
    # Build category filter
    cat_filter = " OR ".join(f"cat:{c}" for c in CATEGORIES)

    # Fetch by category and filter locally by keyword
    search_query = f"({cat_filter})"

    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": min(max_results * 5, 300),  # fetch more, filter locally
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    url = f"{ARXIV_API}?{urlencode(params)}"
    print(f"[scout_arxiv] Fetching: {url[:120]}…", file=sys.stderr)

    try:
        with urlopen(url, timeout=60) as resp:
            xml_data = resp.read()
    except URLError as exc:
        print(f"[scout_arxiv] ERROR: {exc}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        print(f"[scout_arxiv] XML parse error: {exc}", file=sys.stderr)
        return []

    try:
        cutoff = datetime.date.fromisoformat(since_date)
    except ValueError:
        cutoff = datetime.date.today() - datetime.timedelta(days=7)

    results: list[dict] = []
    seen_ids: set[str] = set()

    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        try:
            title = (entry.findtext(f"{{{ATOM_NS}}}title") or "").strip().replace("\n", " ")
            abstract = (entry.findtext(f"{{{ATOM_NS}}}summary") or "").strip().replace("\n", " ")
            published = entry.findtext(f"{{{ATOM_NS}}}published") or ""
            arxiv_id_url = entry.findtext(f"{{{ATOM_NS}}}id") or ""

            # Date filter
            if published:
                pub_date = datetime.date.fromisoformat(published[:10])
                if pub_date < cutoff:
                    continue

            # Keyword filter
            hits = keyword_hits(title, abstract, keywords)
            if not hits:
                continue

            if arxiv_id_url in seen_ids:
                continue
            seen_ids.add(arxiv_id_url)

            # Authors
            authors = [
                (a.findtext(f"{{{ATOM_NS}}}name") or "").strip()
                for a in entry.findall(f"{{{ATOM_NS}}}author")
            ]

            # DOI from arxiv:doi element
            doi_el = entry.find(f"{{{ARXIV_NS}}}doi")
            doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

            results.append(
                paper_schema(
                    title=title,
                    authors=authors,
                    date=published[:10] if published else datetime.date.today().isoformat(),
                    url=arxiv_id_url,
                    doi=doi,
                    abstract_snippet=abstract[:300],
                    citation_count=None,
                    keyword_hits_list=hits,
                    source="arxiv",
                )
            )

            if len(results) >= max_results:
                break

        except Exception as exc:
            print(f"[scout_arxiv] WARN skipping entry: {exc}", file=sys.stderr)

    print(f"[scout_arxiv] Done — {len(results)} papers.", file=sys.stderr)
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

    papers = query_arxiv(keywords, since_date, max_results=30)
    print(json.dumps(papers, indent=2))


if __name__ == "__main__":
    main()
