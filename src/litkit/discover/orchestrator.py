"""Orchestrator for the discover stage.

Runs all enabled sources (in parallel), merges + ranks the results, and returns
structured data. The CLI and MCP server both call :func:`discover_papers`; the
CLI additionally uses :func:`format_digest`, :func:`run_once`, and
:func:`run_cron` to preserve the original ``run_scout.py`` UX.
"""

from __future__ import annotations

import datetime
import json
import logging
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from litkit.config import (
    get_discover_config_path,
    get_discover_output_dir,
    get_notify_cmd,
)
from litkit.discover import rank
from litkit.discover.sources import arxiv, biorxiv, common, pubmed, rss, semantic

log = logging.getLogger(__name__)

# Registered sources, by canonical name. Each value is the source module.
SOURCES = {
    "pubmed": pubmed,
    "biorxiv": biorxiv,
    "arxiv": arxiv,
    "semantic_scholar": semantic,
    "rss": rss,
}

# Friendly aliases accepted on the ``sources`` argument / --sources CLI flag.
SOURCE_ALIASES = {
    "pubmed": "pubmed",
    "biorxiv": "biorxiv",
    "arxiv": "arxiv",
    "semantic": "semantic_scholar",
    "semantic_scholar": "semantic_scholar",
    "rss": "rss",
}


def _resolve_sources(sources: list[str] | None) -> list[str]:
    """Map a list of source names/aliases to canonical names (default: all)."""
    if not sources:
        return list(SOURCES.keys())
    resolved: list[str] = []
    for s in sources:
        key = SOURCE_ALIASES.get(s.strip().lower())
        if key and key not in resolved:
            resolved.append(key)
    return resolved or list(SOURCES.keys())


def _run_source(
    name: str,
    keywords: list[str],
    since_date: str,
    max_results: int,
    cfg: dict,
    test_mode: bool,
) -> list[dict] | None:
    """Run one source; return its papers, or None on failure."""
    module = SOURCES[name]
    try:
        if test_mode:
            return module.dummy_papers()
        if name == "rss":
            return module.query(
                keywords,
                since_date,
                max_results,
                feed_config=cfg.get("rss_feeds", {}),
                lookback_days=cfg.get("lookback_days", 7),
            )
        return module.query(keywords, since_date, max_results)
    except Exception as exc:
        log.error("%s source failed: %s", name, exc)
        return None


def discover_papers(
    keywords: list[str] | None = None,
    sources: list[str] | None = None,
    max_results: int = 20,
    test_mode: bool = False,
    config_path: Path | None = None,
) -> list[dict]:
    """Search the enabled sources, dedup + rank, and return ranked paper dicts.

    Parameters
    ----------
    keywords:
        Keywords to search for. When ``None``, the keyword clusters from the
        search config are used (the recommended default).
    sources:
        Source names/aliases to run (pubmed, biorxiv, arxiv, semantic, rss).
        ``None`` runs all five.
    max_results:
        Maximum number of ranked papers to return.
    test_mode:
        Use offline dummy data from every source (no network, no API keys).
    config_path:
        Override the discover search config path.

    Returns
    -------
    list[dict]
        Papers ranked high→low by ``relevance_score`` (truncated to
        ``max_results``), each following the discover paper schema plus the
        ``bm25_score`` / ``corpus_affinity_score`` / ``relevance_score`` /
        ``ingestion_candidate`` fields.
    """
    cfg = common.load_config(config_path or get_discover_config_path())

    config_keywords = common.all_keywords(cfg)
    # Caller keywords override the config clusters; the config clusters are still
    # used for the cluster-bonus part of ranking.
    search_keywords = keywords if keywords else config_keywords
    clusters = cfg.get("keyword_clusters", {})
    threshold = cfg.get("relevance_threshold", 3.5)

    lookback = cfg.get("lookback_days", 7)
    since_date = (datetime.date.today() - datetime.timedelta(days=lookback)).isoformat()

    selected = _resolve_sources(sources)
    # Fetch generously per source, then truncate after ranking.
    per_source = max(max_results, 30)

    raw: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(selected)) as executor:
        futures = {
            executor.submit(
                _run_source, name, search_keywords, since_date, per_source, cfg, test_mode
            ): name
            for name in selected
        }
        for future in as_completed(futures):
            name = futures[future]
            papers = future.result()
            if papers:
                raw.extend(papers)
                log.info("%s: %d papers", name, len(papers))

    ranked = rank.rank_papers(
        raw,
        keywords=config_keywords if not keywords else (config_keywords + keywords),
        clusters=clusters,
        threshold=threshold,
    )
    return ranked[:max_results]


# ── Digest formatting + CLI helpers (preserve run_scout.py UX) ────────────────

def format_digest(ranked: list[dict], total_found: int, max_papers: int) -> str:
    """Format a ranked list as the human-readable markdown digest."""
    today = datetime.date.today().isoformat()
    candidates = [p for p in ranked if p.get("ingestion_candidate")]
    top = ranked[:max_papers]

    corpus_used = any(p.get("corpus_affinity_score") is not None for p in ranked)
    scoring_note = "BM25+cluster" + ("+corpus_affinity" if corpus_used else "")

    lines = [
        f"📚 **Literature Scout** — {today}",
        f"Found {total_found} papers across sources ({len(ranked)} after dedup) · Scoring: {scoring_note}",
        "",
        "**Top Papers:**",
    ]

    for i, paper in enumerate(top, 1):
        title = paper.get("title", "N/A")
        url = paper.get("url", "")
        authors = paper.get("authors", [])
        author_str = f"{authors[0].split()[-1]} et al." if authors else "Unknown"
        source = paper.get("source", "unknown")
        score = paper.get("relevance_score", 0.0)
        hits = paper.get("keyword_hits", [])[:3]
        hits_str = ", ".join(hits) if hits else "—"
        snippet = (paper.get("abstract_snippet") or "")[:120].replace("\n", " ")
        if len(paper.get("abstract_snippet") or "") > 120:
            snippet += "…"

        affinity_str = ""
        if corpus_used and paper.get("corpus_affinity_score") is not None:
            affinity_str = f" · Corpus: {paper['corpus_affinity_score']:.2f}"

        title_link = f"[{title}]({url})" if url else title

        lines.append(f"{i}. {title_link} — *{author_str}, {source}*")
        lines.append(f"   > {snippet} Relevance: {score}/10{affinity_str} · Keywords: {hits_str}")
        lines.append("")

    lines.append(f"🔬 **{len(candidates)} papers flagged for ingestion**")
    return "\n".join(lines)


def notify(text: str) -> None:
    """Fire the optional LITKIT_NOTIFY_CMD command (best-effort)."""
    notify_cmd = get_notify_cmd()
    if not notify_cmd:
        return
    try:
        subprocess.run(
            f"{notify_cmd} {shlex.quote(text)}",
            shell=True, capture_output=True, text=True, timeout=15,
        )
    except Exception as exc:
        log.warning("notification command failed: %s", exc)


def run_once(
    query: str | None = None,
    sources: list[str] | None = None,
    test_mode: bool = False,
) -> str:
    """Run discover once and return the markdown digest (CLI --once / --test)."""
    cfg = common.load_config(get_discover_config_path())
    max_digest = cfg.get("max_digest_papers", 10)
    keywords = [query] if query else None
    ranked = discover_papers(
        keywords=keywords,
        sources=sources,
        max_results=max(max_digest, 30),
        test_mode=test_mode,
    )
    return format_digest(ranked, total_found=len(ranked), max_papers=max_digest)


def run_cron(sources: list[str] | None = None) -> dict:
    """Scheduled run: write ranked JSON, candidates JSON, and the digest markdown.

    Returns a dict summary with the written paths and counts.
    """
    cfg = common.load_config(get_discover_config_path())
    max_digest = cfg.get("max_digest_papers", 10)
    output_dir = get_discover_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    today_str = datetime.date.today().isoformat()

    ranked = discover_papers(
        keywords=None, sources=sources, max_results=10_000, test_mode=False,
    )
    candidates = [p for p in ranked if p.get("ingestion_candidate")]

    scout_path = output_dir / f"scout-{today_str}.json"
    candidates_path = output_dir / f"candidates-{today_str}.json"
    digest_path = output_dir / f"digest-{today_str}.md"

    scout_path.write_text(json.dumps(ranked, indent=2))
    candidates_path.write_text(json.dumps(candidates, indent=2))
    digest = format_digest(ranked, total_found=len(ranked), max_papers=max_digest)
    digest_path.write_text(digest)

    notify(f"litkit discover complete — {today_str} digest ready")
    log.info("DONE: cron scout complete")

    return {
        "date": today_str,
        "ranked_count": len(ranked),
        "candidate_count": len(candidates),
        "scout_path": str(scout_path),
        "candidates_path": str(candidates_path),
        "digest_path": str(digest_path),
        "digest": digest,
    }


# Re-export for callers that want to (re)build the corpus cache (CLI/maintenance).
build_corpus_cache = rank.build_corpus_cache
