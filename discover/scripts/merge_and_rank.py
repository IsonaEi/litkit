#!/usr/bin/env python3
"""merge_and_rank.py — Dedup, score, and rank papers from all scouts.

## Scoring Architecture (v2 — BM25 + Corpus Affinity)

### Stage 1: Improved BM25 Scoring
Replaces the old simple substring-counting base score with a TF-IDF
inspired approach:
  - TF: keyword frequency in title (weight×2) + abstract (weight×1)
  - IDF: log((N+1)/(df+1)) where N = total papers in batch, df = papers
         containing that keyword. Rare-but-specific keywords score higher.
  - Cluster-aware bonus: if ≥2 keywords from the same cluster appear,
    add a cluster bonus (up to +1.5 per cluster) to reward semantic focus.
  - Citation bonus: log(citations+1)/log(100), capped at 1.0 (log scale
    rather than a step function).
  - Recency bonus: +1.0 if ≤3 days old, +0.5 if ≤7 days old.

### Stage 2: Corpus Affinity Scoring (optional, requires sentence-transformers)
Re-ranks candidates by their semantic similarity to a corpus of papers you
already consider relevant (e.g. a folder of reading notes or markdown papers).
This boosts new papers that are close in topic to your existing library:
  - The corpus directory is read from the LITKIT_CORPUS_DIR environment
    variable (a directory of .md files; README.md files are skipped).
  - Corpus embeddings are pre-computed and cached as `corpus_embeddings.pkl`
    next to your search config (the directory containing LITKIT_CONFIG).
  - Model: all-MiniLM-L6-v2 (lightweight, no GPU needed)
  - corpus_affinity_score = mean of top-3 cosine similarities vs corpus
  - final_score = bm25_score × 0.6 + corpus_affinity_score × 10 × 0.4

### Graceful Fallback
Stage 2 is entirely optional. It is skipped automatically (with only the BM25
score used, and a warning printed to stderr) when either:
  - sentence-transformers is not installed, or
  - LITKIT_CORPUS_DIR is not set / points to an empty or missing directory.

### Threshold
Read from config as `relevance_threshold` (default 3.5 after this update).
Set in your search config (LITKIT_CONFIG), not hard-coded here.

Reads JSON files (one per scout) passed as CLI args, deduplicates by DOI
and fuzzy title match, scores 0-10, and writes output files.

Usage:
    python3 merge_and_rank.py scout1.json scout2.json ...
    python3 merge_and_rank.py --test    # process dummy data, no file I/O
    python3 merge_and_rank.py --output-dir /path/to/dir scout1.json ...
    python3 merge_and_rank.py --build-corpus-cache  # precompute corpus embeddings
"""

import json
import sys
import math
import datetime
import pickle
import os
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from config import LITKIT_CONFIG, LITKIT_OUTPUT
from scout_utils import load_config, all_keywords

# ── Corpus embedding cache path ───────────────────────────────────────────────

def _corpus_cache_path() -> Path:
    """Resolve path to the corpus embeddings pickle cache.

    The cache lives next to the active search config (the directory containing
    LITKIT_CONFIG), so each config keeps its own corpus cache.
    """
    return Path(LITKIT_CONFIG).parent / "corpus_embeddings.pkl"


def _corpus_notes_dir() -> Path | None:
    """Resolve the corpus directory from the LITKIT_CORPUS_DIR env var.

    Returns None when the variable is unset — callers that need it must raise a
    clear error in that case (Stage 2 corpus affinity is optional)."""
    raw = os.environ.get("LITKIT_CORPUS_DIR", "").strip()
    return Path(raw) if raw else None

# ── Optional sentence-transformers import ────────────────────────────────────

_ST_AVAILABLE = False
_SentenceTransformer = None

try:
    from sentence_transformers import SentenceTransformer as _ST
    import numpy as _np
    _SentenceTransformer = _ST
    _ST_AVAILABLE = True
except ImportError:
    pass


# ── Corpus embedding helpers ──────────────────────────────────────────────────

def _load_corpus_texts(notes_dir: Path, max_chars: int = 800) -> list[tuple[str, str]]:
    """Read all .md files under notes_dir, return list of (filepath, text[:max_chars]).
    Skips README files and files that can't be read."""
    results = []
    if not notes_dir.exists():
        return results
    for md_file in notes_dir.rglob("*.md"):
        if md_file.name.lower() == "readme.md":
            continue
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")[:max_chars]
            if text.strip():
                results.append((str(md_file), text))
        except Exception:
            pass
    return results


def build_corpus_cache(cache_path: Path) -> bool:
    """Pre-compute and cache corpus embeddings. Returns True on success."""
    if not _ST_AVAILABLE:
        print("[merge_and_rank] sentence-transformers not available — cannot build cache.", file=sys.stderr)
        return False

    notes_dir = _corpus_notes_dir()
    if notes_dir is None:
        print("[merge_and_rank] LITKIT_CORPUS_DIR is not set — cannot build corpus cache.\n"
              "         Set it to a directory of .md files to enable corpus-affinity scoring, e.g.:\n"
              "             export LITKIT_CORPUS_DIR=/path/to/your/notes",
              file=sys.stderr)
        return False

    print(f"[merge_and_rank] Loading corpus from {notes_dir} ...", file=sys.stderr)
    corpus_texts = _load_corpus_texts(notes_dir)
    if not corpus_texts:
        print(f"[merge_and_rank] No corpus texts found at {notes_dir}", file=sys.stderr)
        return False

    print(f"[merge_and_rank] Computing embeddings for {len(corpus_texts)} corpus documents...", file=sys.stderr)
    model = _SentenceTransformer("all-MiniLM-L6-v2")
    texts = [t for _, t in corpus_texts]
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=True)

    cache_data = {
        "filepaths": [fp for fp, _ in corpus_texts],
        "embeddings": embeddings,  # numpy array
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(cache_data, f)

    print(f"[merge_and_rank] Corpus cache saved → {cache_path} ({len(corpus_texts)} docs)", file=sys.stderr)
    return True


def _load_corpus_cache(cache_path: Path):
    """Load cached corpus embeddings. Returns numpy array or None."""
    if not _ST_AVAILABLE:
        return None
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "rb") as f:
            data = pickle.load(f)
        return data.get("embeddings")
    except Exception as exc:
        print(f"[merge_and_rank] Could not load corpus cache: {exc}", file=sys.stderr)
        return None


def _compute_corpus_affinity(paper_text: str, model, corpus_embeddings) -> float:
    """Compute mean cosine similarity of paper to top-3 most similar corpus docs."""
    if corpus_embeddings is None or not _ST_AVAILABLE:
        return 0.0
    try:
        paper_emb = model.encode([paper_text])[0]
        # cosine similarity = dot(a,b) / (|a||b|)
        # Both embeddings from SentenceTransformer are already normalized (L2)
        # so dot product = cosine similarity
        norms_corpus = _np.linalg.norm(corpus_embeddings, axis=1, keepdims=True)
        corpus_normed = corpus_embeddings / (_np.maximum(norms_corpus, 1e-9))
        paper_norm = paper_emb / max(_np.linalg.norm(paper_emb), 1e-9)
        sims = corpus_normed @ paper_norm
        # Top-3 mean
        top3 = sorted(sims, reverse=True)[:3]
        return float(sum(top3) / len(top3)) if top3 else 0.0
    except Exception as exc:
        print(f"[merge_and_rank] corpus_affinity error: {exc}", file=sys.stderr)
        return 0.0


# ── Helpers ─────────────────────────────────────────────────────────────────


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


# ── Deduplication ─────────────────────────────────────────────────────────────


def deduplicate(papers: list[dict]) -> list[dict]:
    """Dedup by DOI (exact) then by title fuzzy match >= 85%."""
    unique: list[dict] = []
    seen_dois: set[str] = set()
    seen_titles: list[str] = []

    for paper in papers:
        doi = (paper.get("doi") or "").strip().lower()
        title = (paper.get("title") or "").strip()

        if doi:
            if doi in seen_dois:
                continue
            seen_dois.add(doi)

        is_dup = False
        for existing_title in seen_titles:
            if title_similarity(title, existing_title) >= 0.85:
                is_dup = True
                break

        if is_dup:
            continue

        seen_titles.append(title)
        unique.append(paper)

    return unique


# ── IDF computation ───────────────────────────────────────────────────────────

def compute_idf(papers: list[dict], keywords: list[str]) -> dict[str, float]:
    """Compute IDF for each keyword over the paper batch."""
    total = len(papers)
    idf = {}
    for kw in keywords:
        kw_lower = kw.lower()
        df = sum(
            1 for p in papers
            if kw_lower in (p.get("title", "") + " " + p.get("abstract_snippet", "")).lower()
        )
        idf[kw] = math.log((total + 1) / (df + 1))
    return idf


# ── Scoring ───────────────────────────────────────────────────────────────────


def score_paper(
    paper: dict,
    keywords: list[str],
    idf: dict[str, float],
    clusters: dict[str, list[str]],
    today: datetime.date,
) -> float:
    """Score a paper 0–10 using TF-IDF + cluster bonus + citation (log) + recency."""

    title = paper.get("title", "").lower()
    abstract = paper.get("abstract_snippet", "").lower()

    # 1. TF-IDF base score
    tfidf_score = 0.0
    all_hits: list[str] = []
    hits_by_cluster: dict[str, int] = defaultdict(int)

    for kw in keywords:
        kw_lower = kw.lower()
        tf_title = title.count(kw_lower)
        tf_abstract = abstract.count(kw_lower)
        # Title matches weighted 2×
        tf = tf_title * 2 + tf_abstract

        if tf > 0:
            all_hits.append(kw)
            idf_val = idf.get(kw, 0.0)
            tfidf_score += tf * idf_val

            # Track which clusters this keyword belongs to
            for cluster_name, kw_list in clusters.items():
                if kw in kw_list:
                    hits_by_cluster[cluster_name] += 1

    paper["keyword_hits"] = all_hits

    # Normalize TF-IDF score roughly to 0-8 range
    # Divide by 2 to bring into a reasonable range
    base_score = min(8.0, tfidf_score / 2.0)

    # 2. Cluster-aware bonus
    cluster_bonus = 0.0
    for cluster_name, hit_count in hits_by_cluster.items():
        if hit_count >= 2:
            # Each additional hit in same cluster adds bonus, capped at 1.5
            cluster_bonus += min(hit_count * 0.3, 1.5)
    # Total cluster bonus capped at 3.0
    cluster_bonus = min(3.0, cluster_bonus)

    # 3. Citation bonus (log scale, normalized to 0-1)
    citation_bonus = 0.0
    citation_count = paper.get("citation_count")
    if isinstance(citation_count, (int, float)) and citation_count > 0:
        # log(citations+1)/log(100) → ~1.0 at 99 citations
        citation_bonus = min(1.0, math.log(citation_count + 1) / math.log(100))

    # 4. Recency bonus
    recency_bonus = 0.0
    date_str = paper.get("date", "")
    if date_str:
        try:
            pub_date = datetime.date.fromisoformat(date_str[:10])
            days_old = (today - pub_date).days
            if days_old <= 3:
                recency_bonus = 1.0
            elif days_old <= 7:
                recency_bonus = 0.5
        except ValueError:
            pass

    score = base_score + cluster_bonus + citation_bonus + recency_bonus
    return round(min(10.0, score), 2)


# ── Digest formatter ──────────────────────────────────────────────────────────


def format_digest(
    ranked: list[dict],
    total_found: int,
    max_papers: int,
    today: str,
    threshold: float,
    corpus_affinity_used: bool = False,
) -> str:
    candidates = [p for p in ranked if p.get("ingestion_candidate")]
    top = ranked[:max_papers]

    scoring_note = "BM25+cluster"
    if corpus_affinity_used:
        scoring_note += "+corpus_affinity"

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

        # Show corpus affinity if available
        affinity_str = ""
        if corpus_affinity_used and "corpus_affinity_score" in paper:
            affinity_str = f" · Corpus: {paper['corpus_affinity_score']:.2f}"

        if url:
            title_link = f"[{title}]({url})"
        else:
            title_link = title

        lines.append(f"{i}. {title_link} — *{author_str}, {source}*")
        lines.append(f"   > {snippet} Relevance: {score}/10{affinity_str} · Keywords: {hits_str}")
        lines.append("")

    lines.append(f"🔬 **{len(candidates)} papers flagged for ingestion**")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────


def run(
    input_files: list[str],
    output_dir: Path | None = None,
    test_mode: bool = False,
) -> str:
    """Run dedup + scoring, return digest string. Write JSON files if output_dir given."""
    cfg = load_config(LITKIT_CONFIG)
    keywords = all_keywords(cfg)
    clusters = cfg.get("keyword_clusters", {})
    # Default threshold 3.5 (lowered from 7.0 to match new BM25 score range)
    threshold = cfg.get("relevance_threshold", 3.5)
    max_digest = cfg.get("max_digest_papers", 10)
    today = datetime.date.today()
    today_str = today.isoformat()

    all_papers: list[dict] = []

    if test_mode:
        try:
            import subprocess
            scouts = ["scout_pubmed.py", "scout_biorxiv.py", "scout_arxiv.py",
                      "scout_semantic.py", "scout_rss.py"]
            scripts_dir = Path(__file__).parent
            for scout in scouts:
                result = subprocess.run(
                    [sys.executable, str(scripts_dir / scout), "--test"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    all_papers.extend(json.loads(result.stdout))
        except Exception as exc:
            print(f"[merge_and_rank] Test mode error: {exc}", file=sys.stderr)
    else:
        for fpath in input_files:
            try:
                papers = json.loads(Path(fpath).read_text())
                if isinstance(papers, list):
                    all_papers.extend(papers)
                    print(f"[merge_and_rank] Loaded {len(papers)} papers from {fpath}", file=sys.stderr)
            except Exception as exc:
                print(f"[merge_and_rank] WARN could not load {fpath}: {exc}", file=sys.stderr)

    total_found = len(all_papers)
    print(f"[merge_and_rank] Total raw papers: {total_found}", file=sys.stderr)

    deduped = deduplicate(all_papers)
    print(f"[merge_and_rank] After dedup: {len(deduped)}", file=sys.stderr)

    # Compute IDF over the deduplicated batch
    idf = compute_idf(deduped, keywords)

    # ── Stage 1: BM25 scoring ──────────────────────────────────────────────
    for paper in deduped:
        paper["bm25_score"] = score_paper(paper, keywords, idf, clusters, today)

    # ── Stage 2: Corpus affinity (optional) ───────────────────────────────
    corpus_affinity_used = False
    corpus_embeddings = None
    corpus_model = None

    if not _ST_AVAILABLE:
        print("[merge_and_rank] sentence-transformers not available — using BM25 only.", file=sys.stderr)
    elif _corpus_notes_dir() is None:
        print("[merge_and_rank] LITKIT_CORPUS_DIR not set — using BM25 only "
              "(set it to enable corpus-affinity scoring).", file=sys.stderr)
    else:
        cache_path = _corpus_cache_path()
        corpus_embeddings = _load_corpus_cache(cache_path)

        if corpus_embeddings is None:
            # Build the cache on the fly from LITKIT_CORPUS_DIR
            print(f"[merge_and_rank] Corpus cache not found at {cache_path}, building...", file=sys.stderr)
            if build_corpus_cache(cache_path):
                corpus_embeddings = _load_corpus_cache(cache_path)

        if corpus_embeddings is not None:
            try:
                corpus_model = _SentenceTransformer("all-MiniLM-L6-v2")
                corpus_affinity_used = True
                print(f"[merge_and_rank] Corpus affinity enabled ({len(corpus_embeddings)} docs)", file=sys.stderr)
            except Exception as exc:
                print(f"[merge_and_rank] Could not load sentence-transformer model: {exc}", file=sys.stderr)

    # ── Combined scoring ───────────────────────────────────────────────────
    for paper in deduped:
        bm25 = paper["bm25_score"]

        if corpus_affinity_used and corpus_model is not None:
            paper_text = (paper.get("title", "") + " " + paper.get("abstract_snippet", "")).strip()
            affinity = _compute_corpus_affinity(paper_text, corpus_model, corpus_embeddings)
            paper["corpus_affinity_score"] = round(affinity, 4)
            final = bm25 * 0.6 + affinity * 10 * 0.4
        else:
            paper["corpus_affinity_score"] = None
            final = bm25

        paper["relevance_score"] = round(min(10.0, final), 2)
        paper["ingestion_candidate"] = paper["relevance_score"] >= threshold

    ranked = sorted(deduped, key=lambda p: p["relevance_score"], reverse=True)
    candidates = [p for p in ranked if p.get("ingestion_candidate")]

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

        scout_path = output_dir / f"scout-{today_str}.json"
        candidates_path = output_dir / f"candidates-{today_str}.json"

        scout_path.write_text(json.dumps(ranked, indent=2))
        candidates_path.write_text(json.dumps(candidates, indent=2))

        print(f"[merge_and_rank] Wrote {len(ranked)} papers → {scout_path}", file=sys.stderr)
        print(f"[merge_and_rank] Wrote {len(candidates)} candidates → {candidates_path}", file=sys.stderr)

    digest = format_digest(ranked, total_found, max_digest, today_str, threshold, corpus_affinity_used)
    return digest


def main():
    args = sys.argv[1:]

    # Handle --build-corpus-cache flag
    if "--build-corpus-cache" in args:
        cache_path = _corpus_cache_path()
        success = build_corpus_cache(cache_path)
        sys.exit(0 if success else 1)

    test_mode = "--test" in args
    args = [a for a in args if a != "--test"]

    output_dir = None
    if "--output-dir" in args:
        idx = args.index("--output-dir")
        output_dir = Path(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    if test_mode:
        digest = run([], output_dir=output_dir, test_mode=True)
        print(digest)
    elif args:
        digest = run(args, output_dir=output_dir)
        print(digest)
    else:
        print("[merge_and_rank] Usage: merge_and_rank.py [--output-dir DIR] file1.json file2.json ...", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
