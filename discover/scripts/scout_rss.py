#!/usr/bin/env python3
"""scout_rss.py — Journal RSS scout for the discover tool.

Parses journal RSS feeds and filters recent entries by keyword match.
Outputs a JSON array of papers to stdout.

Usage:
    python3 scout_rss.py           # normal run
    python3 scout_rss.py --test    # return 2 dummy papers, no network
"""

import json
import sys
import datetime
import re

from config import LITKIT_CONFIG
from scout_utils import load_config, all_keywords, keyword_hits, paper_schema

# ── Dependency imports ──────────────────────────────────────────────────────

try:
    import feedparser
except ImportError:
    feedparser = None
    print("[scout_rss] WARNING: feedparser not installed. Run: pip install feedparser", file=sys.stderr)

# ── Helpers ─────────────────────────────────────────────────────────────────


def paper_schema_rss(
    title: str,
    authors: list[str],
    date: str,
    url: str,
    doi: str | None,
    abstract_snippet: str,
    keyword_hits_list: list[str],
    feed_name: str,
) -> dict:
    """Extended paper schema for RSS entries (adds 'feed' field)."""
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


def extract_doi(link: str, entry: object) -> str | None:
    """Try to extract DOI from link URL or entry fields."""
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


def parse_entry_date(entry) -> datetime.date | None:
    """Parse publication date from a feedparser entry."""
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


# ── Test mode ────────────────────────────────────────────────────────────────


def dummy_papers() -> list[dict]:
    today = datetime.date.today().isoformat()
    return [
        paper_schema_rss(
            title="[TEST] Dendritic integration in hippocampal CA1 pyramidal neurons",
            authors=["Test Author J", "Test Author K"],
            date=today,
            url="https://www.nature.com/articles/test-neuro-1",
            doi="10.1038/s41593-026-00001-1",
            abstract_snippet="A test abstract about dendritic integration in CA1.",
            keyword_hits_list=["dendritic integration", "CA1", "hippocampus"],
            feed_name="nature_neuro",
        ),
        paper_schema_rss(
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


# ── RSS parsing ───────────────────────────────────────────────────────────────


def parse_feed(
    feed_name: str,
    feed_url: str,
    keywords: list[str],
    cutoff: datetime.date,
    max_results: int,
) -> list[dict]:
    if feedparser is None:
        return []

    print(f"[scout_rss] Fetching {feed_name}: {feed_url}", file=sys.stderr)

    try:
        parsed = feedparser.parse(feed_url)
    except Exception as exc:
        print(f"[scout_rss] ERROR parsing {feed_name}: {exc}", file=sys.stderr)
        return []

    if parsed.bozo:
        print(f"[scout_rss] WARN bozo parse for {feed_name}: {parsed.bozo_exception}", file=sys.stderr)

    results: list[dict] = []

    for entry in parsed.entries:
        try:
            title = (getattr(entry, "title", "") or "").strip()
            link = (getattr(entry, "link", "") or "").strip()

            summary = (getattr(entry, "summary", "") or "").strip()
            summary_clean = re.sub(r"<[^>]+>", "", summary).strip()

            pub_date = parse_entry_date(entry)
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

            doi = extract_doi(link, entry)

            results.append(
                paper_schema_rss(
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
            print(f"[scout_rss] WARN skipping entry in {feed_name}: {exc}", file=sys.stderr)

    print(f"[scout_rss] {feed_name}: {len(results)} matched entries.", file=sys.stderr)
    return results


def query_rss(
    feed_config: dict,
    keywords: list[str],
    lookback_days: int,
    max_results: int,
) -> list[dict]:
    cutoff = datetime.date.today() - datetime.timedelta(days=lookback_days)
    all_results: list[dict] = []
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()

    per_feed_limit = max(max_results // len(feed_config), 5) if feed_config else max_results

    for feed_name, feed_url in feed_config.items():
        papers = parse_feed(feed_name, feed_url, keywords, cutoff, per_feed_limit)
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

    print(f"[scout_rss] Done — {len(all_results)} total papers.", file=sys.stderr)
    return all_results


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    if "--test" in sys.argv:
        print(json.dumps(dummy_papers(), indent=2))
        return

    cfg = load_config(LITKIT_CONFIG)
    lookback = cfg.get("lookback_days", 7)
    keywords = all_keywords(cfg)
    feed_config = cfg.get("rss_feeds", {})

    papers = query_rss(feed_config, keywords, lookback, max_results=30)
    print(json.dumps(papers, indent=2))


if __name__ == "__main__":
    main()
