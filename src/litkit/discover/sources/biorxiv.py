"""bioRxiv source — fetches recent preprints from the bioRxiv REST API.

The requests dependency is imported lazily inside :func:`query`.
"""

from __future__ import annotations

import datetime
import logging

from litkit.discover.sources.common import keyword_hits, paper_schema

log = logging.getLogger(__name__)

NAME = "biorxiv"


def dummy_papers() -> list[dict]:
    """Two offline dummy papers for the no-network smoke test."""
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


def query(keywords: list[str], since_date: str, max_results: int) -> list[dict]:
    """Fetch recent bioRxiv preprints in the date window and filter by keyword."""
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - depends on extras
        raise ImportError(
            "requests is required for the bioRxiv source. "
            "Install it with: pip install 'litkit[discover]'"
        ) from exc

    today = datetime.date.today().isoformat()
    url = f"https://api.biorxiv.org/details/biorxiv/{since_date}/{today}/0"

    log.info("Fetching: %s", url)

    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.error("request failed: %s", exc)
        return []

    collection = data.get("collection", [])
    log.info("%d preprints in date window.", len(collection))

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

    log.info("Done — %d papers.", len(results))
    return results
