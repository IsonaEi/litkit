"""Semantic Scholar source — searches the S2 graph API for recent papers.

Includes citation counts in its output for relevance scoring. Uses only the
standard library (urllib) plus the optional S2_API_KEY.
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from litkit.config import get_s2_api_key
from litkit.discover.sources.common import keyword_hits, paper_schema

log = logging.getLogger(__name__)

NAME = "semantic_scholar"

SS_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SS_FIELDS = "title,authors,year,publicationDate,externalIds,abstract,citationCount,url"


def dummy_papers() -> list[dict]:
    """Two offline dummy papers for the no-network smoke test."""
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


def _search_keyword(keyword: str, since_date: str, limit: int = 10) -> list[dict]:
    """Search one keyword, return raw S2 results."""
    params = {
        "query": keyword,
        "fields": SS_FIELDS,
        "limit": limit,
        "publicationDateOrYear": f"{since_date}:",
    }
    url = f"{SS_SEARCH_URL}?{urlencode(params)}"

    headers = {"User-Agent": "litkit-discover/0.2"}
    api_key = get_s2_api_key()
    if api_key:
        headers["x-api-key"] = api_key

    req = Request(url, headers=headers)

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data.get("data", [])
    except HTTPError as exc:
        if exc.code == 429:
            log.warning("Rate limited, sleeping 5s…")
            time.sleep(5)
        else:
            log.warning("HTTP %s for keyword '%s'", exc.code, keyword)
    except URLError as exc:
        log.warning("URLError for '%s': %s", keyword, exc)
    except Exception as exc:
        log.error("error for '%s': %s", keyword, exc)

    return []


def query(keywords: list[str], since_date: str, max_results: int) -> list[dict]:
    """Search Semantic Scholar across a sample of keywords, dedup by paper id."""
    results: list[dict] = []
    seen_ids: set[str] = set()

    # Use representative keywords (first 15 to avoid rate limits).
    sample_keywords = keywords[:15]

    for kw in sample_keywords:
        if len(results) >= max_results:
            break

        raw = _search_keyword(kw, since_date, limit=10)
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

    log.info("Done — %d papers.", len(results))
    return results
