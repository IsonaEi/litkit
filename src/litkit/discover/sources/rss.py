"""Journal RSS source — parses journal RSS feeds and filters by keyword.

The feedparser dependency is imported lazily inside :func:`query`.
"""

from __future__ import annotations

import datetime
import logging
import re

from litkit.discover.sources.common import keyword_hits, paper_schema

log = logging.getLogger(__name__)

NAME = "rss"


def _paper_schema_rss(
    title: str,
    authors: list[str],
    date: str,
    url: str,
    doi: str | None,
    abstract_snippet: str,
    keyword_hits_list: list[str],
    feed_name: str,
) -> dict:
    """Extended paper schema for RSS entries (adds a 'feed' field)."""
    base = paper_schema(
        title=title,
        authors=authors,
        date=date,
        url=url,
        doi=doi,
        abstract_snippet=abstract_snippet,
        citation_count=None,
        keyword_hits_list=keyword_hits_list,
        source="journal_rss",
    )
    base["feed"] = feed_name
    return base


def _extract_doi(link: str, entry: object) -> str | None:
    """Try to extract a DOI from the link URL or entry fields."""
    if not link:
        return None

    doi_match = re.search(r"10\.\d{4,}/\S+", link)
    if doi_match:
        return doi_match.group(0).rstrip(")")

    if hasattr(entry, "prism_doi"):
        return entry.prism_doi
    if hasattr(entry, "dc_identifier"):
        ident = entry.dc_identifier
        if ident and ident.startswith("10."):
            return ident

    return None


def _parse_entry_date(entry) -> datetime.date | None:
    """Parse a publication date from a feedparser entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime.date(*entry.published_parsed[:3])
        except Exception:
            pass

    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            return datetime.date(*entry.updated_parsed[:3])
        except Exception:
            pass

    published = getattr(entry, "published", "") or ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(published[:len(fmt)], fmt).date()
        except Exception:
            pass

    return None


def dummy_papers() -> list[dict]:
    """Two offline dummy papers for the no-network smoke test."""
    today = datetime.date.today().isoformat()
    return [
        _paper_schema_rss(
            title="[TEST] Dendritic integration in hippocampal CA1 pyramidal neurons",
            authors=["Test Author J", "Test Author K"],
            date=today,
            url="https://www.nature.com/articles/test-neuro-1",
            doi="10.1038/s41593-026-00001-1",
            abstract_snippet="A test abstract about dendritic integration in CA1.",
            keyword_hits_list=["dendritic integration", "CA1", "hippocampus"],
            feed_name="nature_neuro",
        ),
        _paper_schema_rss(
            title="[TEST] Calcium imaging of place cells in freely moving mice",
            authors=["Test Author L"],
            date=today,
            url="https://www.cell.com/neuron/fulltext/S0896-6273(26)00001-0",
            doi="10.1016/j.neuron.2026.01.001",
            abstract_snippet="A test abstract about calcium imaging of place cells.",
            keyword_hits_list=["calcium imaging", "place cells", "freely moving"],
            feed_name="neuron",
        ),
    ]


def _parse_feed(
    feedparser,
    feed_name: str,
    feed_url: str,
    keywords: list[str],
    cutoff: datetime.date,
    max_results: int,
) -> list[dict]:
    log.info("Fetching %s: %s", feed_name, feed_url)

    try:
        parsed = feedparser.parse(feed_url)
    except Exception as exc:
        log.error("error parsing %s: %s", feed_name, exc)
        return []

    if parsed.bozo:
        log.warning("bozo parse for %s: %s", feed_name, parsed.bozo_exception)

    results: list[dict] = []

    for entry in parsed.entries:
        try:
            title = (getattr(entry, "title", "") or "").strip()
            link = (getattr(entry, "link", "") or "").strip()

            summary = (getattr(entry, "summary", "") or "").strip()
            summary_clean = re.sub(r"<[^>]+>", "", summary).strip()

            pub_date = _parse_entry_date(entry)
            if pub_date is None:
                pub_date = datetime.date.today()
            if pub_date < cutoff:
                continue

            hits = keyword_hits(title, summary_clean, keywords)
            if not hits:
                continue

            authors: list[str] = []
            for author in getattr(entry, "authors", []):
                name = author.get("name", "").strip()
                if name:
                    authors.append(name)
            if not authors and hasattr(entry, "author"):
                authors = [entry.author.strip()]

            doi = _extract_doi(link, entry)

            results.append(
                _paper_schema_rss(
                    title=title,
                    authors=authors,
                    date=pub_date.isoformat(),
                    url=link,
                    doi=doi,
                    abstract_snippet=summary_clean[:300],
                    keyword_hits_list=hits,
                    feed_name=feed_name,
                )
            )

            if len(results) >= max_results:
                break

        except Exception as exc:
            log.warning("skipping entry in %s: %s", feed_name, exc)

    log.info("%s: %d matched entries.", feed_name, len(results))
    return results


def query(
    keywords: list[str],
    since_date: str,
    max_results: int,
    feed_config: dict | None = None,
    lookback_days: int = 7,
) -> list[dict]:
    """Parse all configured RSS feeds and return matching, deduplicated entries.

    ``feed_config`` maps a feed name to its URL; it comes from the discover
    search config (``rss_feeds``). ``since_date`` is accepted for a uniform
    source signature but RSS filters by ``lookback_days`` internally.
    """
    try:
        import feedparser
    except ImportError as exc:  # pragma: no cover - depends on extras
        raise ImportError(
            "feedparser is required for the journal RSS source. "
            "Install it with: pip install 'litkit[discover]'"
        ) from exc

    feed_config = feed_config or {}
    cutoff = datetime.date.today() - datetime.timedelta(days=lookback_days)
    all_results: list[dict] = []
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()

    per_feed_limit = max(max_results // len(feed_config), 5) if feed_config else max_results

    for feed_name, feed_url in feed_config.items():
        papers = _parse_feed(feedparser, feed_name, feed_url, keywords, cutoff, per_feed_limit)
        for paper in papers:
            doi = paper.get("doi")
            title = paper.get("title", "").lower()

            if doi and doi in seen_dois:
                continue
            if title in seen_titles:
                continue

            if doi:
                seen_dois.add(doi)
            seen_titles.add(title)
            all_results.append(paper)

            if len(all_results) >= max_results:
                break

        if len(all_results) >= max_results:
            break

    log.info("Done — %d total papers.", len(all_results))
    return all_results
