"""Dedup, score, and rank papers from all discover sources.

## Scoring architecture (BM25 + corpus affinity)

### Stage 1: BM25-style scoring
A TF-IDF-inspired base score:
  - TF: keyword frequency in title (weight x2) + abstract (weight x1)
  - IDF: log((N+1)/(df+1)) where N = total papers in batch, df = papers
         containing that keyword. Rare-but-specific keywords score higher.
  - Cluster-aware bonus: if >=2 keywords from the same cluster appear,
    add a cluster bonus (up to +1.5 per cluster) to reward semantic focus.
  - Citation bonus: log(citations+1)/log(100), capped at 1.0.
  - Recency bonus: +1.0 if <=3 days old, +0.5 if <=7 days old.

### Stage 2: corpus affinity (optional)
Re-ranks candidates by semantic similarity to a corpus of papers you already
consider relevant (a folder of reading notes / markdown):
  - corpus directory comes from LITKIT_CORPUS_DIR (a directory of .md files;
    README.md files are skipped),
  - corpus embeddings are cached as ``corpus_embeddings.pkl`` next to the active
    search config,
  - model: all-MiniLM-L6-v2 (lightweight, no GPU needed),
  - corpus_affinity_score = mean of top-3 cosine similarities vs corpus,
  - final_score = bm25_score * 0.6 + corpus_affinity_score * 10 * 0.4.

Stage 2 is skipped automatically (BM25 only) when sentence-transformers is not
installed or LITKIT_CORPUS_DIR is unset/empty. ``sentence_transformers`` and
``numpy`` are imported lazily, so importing this module never needs the
``discover-rerank`` extra.
"""

from __future__ import annotations

import datetime
import logging
import math
import pickle
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from litkit.config import get_corpus_notes_dir, get_discover_config_path

log = logging.getLogger(__name__)


# ── Corpus cache resolution ───────────────────────────────────────────────────

def _corpus_cache_path() -> Path:
    """Resolve the corpus-embeddings pickle cache, next to the active config."""
    return Path(get_discover_config_path()).parent / "corpus_embeddings.pkl"


def _sentence_transformers_available() -> bool:
    """Whether sentence-transformers + numpy are importable (lazy check)."""
    try:
        import numpy  # noqa: F401
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


# ── Corpus embedding helpers ──────────────────────────────────────────────────

def _load_corpus_texts(notes_dir: Path, max_chars: int = 800) -> list[tuple[str, str]]:
    """Read all .md files under ``notes_dir``; return (filepath, text[:max_chars]).

    Skips README files and files that can't be read.
    """
    results: list[tuple[str, str]] = []
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


def build_corpus_cache(cache_path: Path | None = None) -> bool:
    """Pre-compute and cache corpus embeddings. Returns True on success."""
    if not _sentence_transformers_available():
        log.warning("sentence-transformers not available — cannot build cache.")
        return False

    from sentence_transformers import SentenceTransformer

    cache_path = cache_path or _corpus_cache_path()
    notes_dir = get_corpus_notes_dir()
    if notes_dir is None:
        log.warning(
            "LITKIT_CORPUS_DIR is not set — cannot build corpus cache. "
            "Set it to a directory of .md files to enable corpus-affinity scoring."
        )
        return False

    log.info("Loading corpus from %s …", notes_dir)
    corpus_texts = _load_corpus_texts(notes_dir)
    if not corpus_texts:
        log.warning("No corpus texts found at %s", notes_dir)
        return False

    log.info("Computing embeddings for %d corpus documents…", len(corpus_texts))
    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [t for _, t in corpus_texts]
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=False)

    cache_data = {
        "filepaths": [fp for fp, _ in corpus_texts],
        "embeddings": embeddings,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(cache_data, f)

    log.info("Corpus cache saved → %s (%d docs)", cache_path, len(corpus_texts))
    return True


def _load_corpus_cache(cache_path: Path):
    """Load cached corpus embeddings. Returns the embeddings array or None."""
    if not _sentence_transformers_available():
        return None
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "rb") as f:
            data = pickle.load(f)
        return data.get("embeddings")
    except Exception as exc:
        log.warning("Could not load corpus cache: %s", exc)
        return None


def _compute_corpus_affinity(paper_text: str, model, corpus_embeddings) -> float:
    """Mean cosine similarity of the paper to the top-3 most similar corpus docs."""
    if corpus_embeddings is None:
        return 0.0
    try:
        import numpy as np

        paper_emb = model.encode([paper_text])[0]
        norms_corpus = np.linalg.norm(corpus_embeddings, axis=1, keepdims=True)
        corpus_normed = corpus_embeddings / (np.maximum(norms_corpus, 1e-9))
        paper_norm = paper_emb / max(np.linalg.norm(paper_emb), 1e-9)
        sims = corpus_normed @ paper_norm
        top3 = sorted(sims, reverse=True)[:3]
        return float(sum(top3) / len(top3)) if len(top3) else 0.0
    except Exception as exc:
        log.warning("corpus_affinity error: %s", exc)
        return 0.0


# ── Dedup ─────────────────────────────────────────────────────────────────────

def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


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


# ── IDF + scoring ─────────────────────────────────────────────────────────────

def compute_idf(papers: list[dict], keywords: list[str]) -> dict[str, float]:
    """Compute IDF for each keyword over the paper batch."""
    total = len(papers)
    idf: dict[str, float] = {}
    for kw in keywords:
        kw_lower = kw.lower()
        df = sum(
            1 for p in papers
            if kw_lower in (p.get("title", "") + " " + p.get("abstract_snippet", "")).lower()
        )
        idf[kw] = math.log((total + 1) / (df + 1))
    return idf


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

    tfidf_score = 0.0
    all_hits: list[str] = []
    hits_by_cluster: dict[str, int] = defaultdict(int)

    for kw in keywords:
        kw_lower = kw.lower()
        tf_title = title.count(kw_lower)
        tf_abstract = abstract.count(kw_lower)
        tf = tf_title * 2 + tf_abstract  # title matches weighted 2x

        if tf > 0:
            all_hits.append(kw)
            idf_val = idf.get(kw, 0.0)
            tfidf_score += tf * idf_val

            for cluster_name, kw_list in clusters.items():
                if kw in kw_list:
                    hits_by_cluster[cluster_name] += 1

    paper["keyword_hits"] = all_hits

    base_score = min(8.0, tfidf_score / 2.0)

    cluster_bonus = 0.0
    for _cluster_name, hit_count in hits_by_cluster.items():
        if hit_count >= 2:
            cluster_bonus += min(hit_count * 0.3, 1.5)
    cluster_bonus = min(3.0, cluster_bonus)

    citation_bonus = 0.0
    citation_count = paper.get("citation_count")
    if isinstance(citation_count, (int, float)) and citation_count > 0:
        citation_bonus = min(1.0, math.log(citation_count + 1) / math.log(100))

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


# ── Top-level rank ────────────────────────────────────────────────────────────

def rank_papers(
    papers: list[dict],
    keywords: list[str],
    clusters: dict[str, list[str]],
    threshold: float,
    use_corpus_affinity: bool = True,
) -> list[dict]:
    """Dedup + score a flat list of papers and return them ranked, high→low.

    Each returned paper gets ``bm25_score``, ``corpus_affinity_score`` (or None),
    ``relevance_score`` and ``ingestion_candidate`` set in place.
    """
    today = datetime.date.today()

    deduped = deduplicate(papers)
    log.info("After dedup: %d papers", len(deduped))

    idf = compute_idf(deduped, keywords)

    for paper in deduped:
        paper["bm25_score"] = score_paper(paper, keywords, idf, clusters, today)

    corpus_affinity_used = False
    corpus_embeddings = None
    corpus_model = None

    if use_corpus_affinity:
        if not _sentence_transformers_available():
            log.info("sentence-transformers not available — using BM25 only.")
        elif get_corpus_notes_dir() is None:
            log.info("LITKIT_CORPUS_DIR not set — using BM25 only.")
        else:
            cache_path = _corpus_cache_path()
            corpus_embeddings = _load_corpus_cache(cache_path)
            if corpus_embeddings is None:
                log.info("Corpus cache not found at %s, building…", cache_path)
                if build_corpus_cache(cache_path):
                    corpus_embeddings = _load_corpus_cache(cache_path)
            if corpus_embeddings is not None:
                try:
                    from sentence_transformers import SentenceTransformer
                    corpus_model = SentenceTransformer("all-MiniLM-L6-v2")
                    corpus_affinity_used = True
                    log.info("Corpus affinity enabled (%d docs)", len(corpus_embeddings))
                except Exception as exc:
                    log.warning("Could not load sentence-transformer model: %s", exc)

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

    return sorted(deduped, key=lambda p: p["relevance_score"], reverse=True)
