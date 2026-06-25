"""arXiv source — searches arXiv cs.NE, q-bio.NC, q-bio.QM via the Atom API.

Uses only the Python standard library (urllib + ElementTree), so it needs no
extra dependency.
"""

from __future__ import annotations

import datetime
import logging
import xml.etree.ElementTree as ET
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from litkit.discover.sources.common import keyword_hits, paper_schema

log = logging.getLogger(__name__)

NAME = "arxiv"

ARXIV_API = "http://export.arxiv.org/api/query"
CATEGORIES = ["cs.NE", "q-bio.NC", "q-bio.QM"]
ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"


def dummy_papers() -> list[dict]:
    """Two offline dummy papers for the no-network smoke test."""
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


def query(keywords: list[str], since_date: str, max_results: int) -> list[dict]:
    """Fetch recent arXiv entries in the configured categories, filter by keyword."""
    cat_filter = " OR ".join(f"cat:{c}" for c in CATEGORIES)
    search_query = f"({cat_filter})"

    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": min(max_results * 5, 300),  # fetch more, filter locally
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    url = f"{ARXIV_API}?{urlencode(params)}"
    log.info("Fetching: %s…", url[:120])

    try:
        with urlopen(url, timeout=60) as resp:
            xml_data = resp.read()
    except URLError as exc:
        log.error("request failed: %s", exc)
        return []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        log.error("XML parse error: %s", exc)
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

            if published:
                pub_date = datetime.date.fromisoformat(published[:10])
                if pub_date < cutoff:
                    continue

            hits = keyword_hits(title, abstract, keywords)
            if not hits:
                continue

            if arxiv_id_url in seen_ids:
                continue
            seen_ids.add(arxiv_id_url)

            authors = [
                (a.findtext(f"{{{ATOM_NS}}}name") or "").strip()
                for a in entry.findall(f"{{{ATOM_NS}}}author")
            ]

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
            log.warning("skipping entry: %s", exc)

    log.info("Done — %d papers.", len(results))
    return results
