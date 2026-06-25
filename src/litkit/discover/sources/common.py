"""Shared helpers for discover sources — config loading and the paper schema."""

from __future__ import annotations

import json
from pathlib import Path


def load_config(path: Path) -> dict:
    """Load and parse the JSON search config file."""
    return json.loads(Path(path).read_text())


def all_keywords(cfg: dict) -> list[str]:
    """Expand all keyword clusters from config into a flat list."""
    kws: list[str] = []
    for cluster in cfg.get("keyword_clusters", {}).values():
        kws.extend(cluster)
    return kws


def keyword_hits(title: str, abstract: str, keywords: list[str]) -> list[str]:
    """Return the subset of keywords that appear in title or abstract."""
    text = (title + " " + abstract).lower()
    return [kw for kw in keywords if kw.lower() in text]


def paper_schema(
    title: str,
    authors: list[str],
    date: str,
    url: str,
    doi: str | None,
    abstract_snippet: str,
    citation_count: int | None,
    keyword_hits_list: list[str],
    source: str,
) -> dict:
    """Return a standardized paper dict for use across all sources."""
    return {
        "title": title,
        "authors": authors,
        "date": date,
        "source": source,
        "url": url,
        "doi": doi,
        "abstract_snippet": abstract_snippet[:300],
        "citation_count": citation_count,
        "relevance_score": 0.0,
        "keyword_hits": keyword_hits_list,
        "ingestion_candidate": False,
    }
