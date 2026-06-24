#!/usr/bin/env python3
"""scout_semantic.py — Semantic Scholar scout for the discover tool.

Searches Semantic Scholar graph API for recent papers matching config keywords.
Includes citation_count in output for relevance scoring.
Outputs a JSON array of papers to stdout.

Usage:
    python3 scout_semantic.py           # normal run
    python3 scout_semantic.py --test    # return 2 dummy papers, no network
"""

import json
import sys
import datetime
import time
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from config import LITKIT_CONFIG, S2_API_KEY
from scout_utils import load_config, all_keywords, keyword_hits, paper_schema

SS_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SS_FIELDS = "title,authors,year,publicationDate,externalIds,abstract,citationCount,url"

# ── Test mode ────────────────────────────────────────────────────────────────


def dummy_papers() -> list[dict]:
    today = datetime.date.today().isoformat()
    return [
        paper_schema(
            title="[TEST] Population vector decoding of hippocampal spatial representations",
            authors=["Test Author M", "Test Author N"],
            date=today,
            url="https://www.semanticscholar.org/paper/test1",
            doi="10.0000/test.semantic.1",
            abstract_snippet="A test abstract about population vector decoding and place cells.",
            citation_count=42,
            keyword_hits_list=["population vector decoding", "place cells", "hippocampus"],
            source="semantic_scholar",
        ),
        paper_schema(
            title="[TEST] Parvalbumin interneuron control of theta oscillations",
            authors=["Test Author O"],
            date=today,
            url="https://www.semanticscholar.org/paper/test2",
            doi="10.0000/test.semantic.2",
            abstract_snippet="A test abstract about parvalbumin interneurons and theta oscillations.",
            citation_count=7,
            keyword_hits_list=["parvalbumin", "interneuron", "theta oscillations"],
            source="semantic_scholar",
        ),
    ]


# ── Semantic Scholar query ────────────────────────────────────────────────────


def search_keyword(keyword: str, since_date: str, limit: int = 10) -> list[dict]:
    """Search one keyword, return raw SS results."""
    params = {
        "query": keyword,
        "fields": SS_FIELDS,
        "limit": limit,
        "publicationDateOrYear": f"{since_date}:",
    }
    url = f"{SS_SEARCH_URL}?{urlencode(params)}"

    headers = {"User-Agent": "litkit-discover/0.1"}
    if S2_API_KEY:
        headers["x-api-key"] = S2_API_KEY

    req = Request(url, headers=headers)

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data.get("data", [])
    except HTTPError as exc:
        if exc.code == 429:
            print(f"[scout_semantic] Rate limited, sleeping 5s…", file=sys.stderr)
            time.sleep(5)
        else:
            print(f"[scout_semantic] HTTP {exc.code} for keyword '{keyword}'", file=sys.stderr)
    except URLError as exc:
        print(f"[scout_semantic] URLError for '{keyword}': {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"[scout_semantic] ERROR for '{keyword}': {exc}", file=sys.stderr)

    return []


def query_semantic(keywords: list[str], since_date: str, max_results: int) -> list[dict]:
    results: list[dict] = []
    seen_ids: set[str] = set()

    # Use representative keywords (first 15 to avoid rate limits)
    sample_keywords = keywords[:15]

    for kw in sample_keywords:
        if len(results) >= max_results:
            break

        raw = search_keyword(kw, since_date, limit=10)
        time.sleep(0.5)  # respect rate limit

        for item in raw:
            paper_id = item.get("paperId", "")
            if paper_id in seen_ids:
                continue
            seen_ids.add(paper_id)

            title = (item.get("title") or "").strip()
            abstract = (item.get("abstract") or "").strip()

            pub_date = item.get("publicationDate") or ""
            if not pub_date:
                year = item.get("year")
                pub_date = f"{year}-01-01" if year else datetime.date.today().isoformat()

            authors = [
                (a.get("name") or "").strip()
                for a in (item.get("authors") or [])
            ]

            ext_ids = item.get("externalIds") or {}
            doi = ext_ids.get("DOI") or ext_ids.get("doi")

            url = item.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}"
            citation_count = item.get("citationCount")

            hits = keyword_hits(title, abstract, keywords)

            results.append(
                paper_schema(
                    title=title,
                    authors=authors,
                    date=pub_date[:10] if pub_date else datetime.date.today().isoformat(),
                    url=url,
                    doi=doi,
                    abstract_snippet=abstract[:300],
                    citation_count=citation_count,
                    keyword_hits_list=hits,
                    source="semantic_scholar",
                )
            )

            if len(results) >= max_results:
                break

    print(f"[scout_semantic] Done — {len(results)} papers.", file=sys.stderr)
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

    papers = query_semantic(keywords, since_date, max_results=30)
    print(json.dumps(papers, indent=2))


if __name__ == "__main__":
    main()
