"""Central configuration for litkit.

Merges the two former per-stage ``config.py`` files (discover + search) into one
module. Everything is read from environment variables with sensible defaults;
nothing is hardcoded and no secret is ever stored here.

Environment variables, by stage:

discover
    ENTREZ_EMAIL            NCBI Entrez (PubMed) contact email.
    S2_API_KEY              Semantic Scholar API key (raises rate limits; shared
                            with the manage stage).
    LITKIT_CONFIG           Path to the discover search-config JSON
                            (default: the bundled example shipped in the package).
    LITKIT_OUTPUT           Output directory for scheduled ("cron") runs
                            (default: /tmp/litkit-discover).
    LITKIT_CORPUS_DIR       Directory of .md notes for Stage-2 corpus-affinity
                            re-ranking (unset = BM25-only).
    LITKIT_NOTIFY_CMD       Shell command fired when a cron digest is ready.

manage
    S2_API_KEY              (see above) — used by metadata enrichment.
    LITKIT_ENABLE_SCIHUB    Set to "1" to opt in to the Sci-Hub download
                            fallback. OFF (0) by default.

search
    LIT_QUERY_CORPUS        Directory of PDF/MD papers to index (required).
    LIT_QUERY_CORPUS_EXTRA  Extra corpus directories, comma-separated.
    LIT_QUERY_DB            Qdrant on-disk storage location.
    LIT_QUERY_COLLECTION    Qdrant collection name (default: literature).
    LIT_QUERY_EMBEDDING_MODEL  HuggingFace embedding model (default: BAAI/bge-m3).
    LIT_QUERY_CHUNK_MAX_TOKENS Max tokens per chunk (default: 512).
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # Python 3.9+: importlib.resources.files
    from importlib.resources import files as _pkg_files
except ImportError:  # pragma: no cover - we require >=3.10 anyway
    _pkg_files = None  # type: ignore[assignment]


# ── Bundled package data ──────────────────────────────────────────────────────

def _bundled_search_config() -> Path:
    """Path to the search-config example shipped inside the package.

    Read at call time (not import time) so that an unusual install layout never
    breaks ``import litkit.config``.
    """
    if _pkg_files is not None:
        try:
            return Path(str(_pkg_files("litkit.discover") / "search-config-example.json"))
        except (ModuleNotFoundError, FileNotFoundError):
            pass
    # Fallback: path relative to this file.
    return Path(__file__).parent / "discover" / "search-config-example.json"


# ── discover ──────────────────────────────────────────────────────────────────

def get_discover_config_path() -> Path:
    """Resolve the active discover search-config path (LITKIT_CONFIG or bundled)."""
    raw = os.environ.get("LITKIT_CONFIG", "").strip()
    return Path(raw) if raw else _bundled_search_config()


def get_discover_output_dir() -> Path:
    """Resolve the discover cron output directory (LITKIT_OUTPUT)."""
    return Path(os.environ.get("LITKIT_OUTPUT", "/tmp/litkit-discover"))


def get_entrez_email() -> str:
    """NCBI Entrez contact email (ENTREZ_EMAIL)."""
    return os.environ.get("ENTREZ_EMAIL", "")


def get_s2_api_key() -> str:
    """Semantic Scholar API key (S2_API_KEY); empty string when unset."""
    return os.environ.get("S2_API_KEY", "")


def get_corpus_notes_dir() -> Path | None:
    """Corpus directory for Stage-2 affinity re-ranking (LITKIT_CORPUS_DIR).

    Returns ``None`` when unset — corpus affinity is optional.
    """
    raw = os.environ.get("LITKIT_CORPUS_DIR", "").strip()
    return Path(raw) if raw else None


def get_notify_cmd() -> str:
    """Optional notification command (LITKIT_NOTIFY_CMD); empty when unset."""
    return os.environ.get("LITKIT_NOTIFY_CMD", "").strip()


# ── manage ──────────────────────────────────────────────────────────────────

def scihub_enabled() -> bool:
    """Whether the Sci-Hub download fallback is opted in (LITKIT_ENABLE_SCIHUB=1)."""
    return os.environ.get("LITKIT_ENABLE_SCIHUB", "0").strip() == "1"


# ── search ──────────────────────────────────────────────────────────────────

def get_corpus_path() -> Path | None:
    """Primary search corpus directory (LIT_QUERY_CORPUS); ``None`` when unset."""
    raw = os.environ.get("LIT_QUERY_CORPUS", "").strip()
    return Path(raw) if raw else None


def get_corpus_extra_paths() -> list[Path]:
    """Extra search corpus directories (LIT_QUERY_CORPUS_EXTRA, comma-separated)."""
    raw = os.environ.get("LIT_QUERY_CORPUS_EXTRA", "").strip()
    if not raw:
        return []
    return [Path(p.strip()) for p in raw.split(",") if p.strip()]


def get_all_corpus_paths() -> list[Path]:
    """All search corpus paths (primary + extras) that currently exist on disk."""
    paths: list[Path] = []
    primary = get_corpus_path()
    if primary:
        paths.append(primary)
    paths.extend(get_corpus_extra_paths())
    return [p for p in paths if p.exists()]


def get_db_path() -> Path:
    """Qdrant on-disk storage path (LIT_QUERY_DB)."""
    return Path(os.environ.get(
        "LIT_QUERY_DB",
        str(Path.home() / ".lit-query" / "qdrant_storage"),
    ))


def get_collection_name() -> str:
    """Qdrant collection name (LIT_QUERY_COLLECTION)."""
    return os.environ.get("LIT_QUERY_COLLECTION", "literature")


def get_embedding_model() -> str:
    """HuggingFace embedding model name (LIT_QUERY_EMBEDDING_MODEL)."""
    return os.environ.get("LIT_QUERY_EMBEDDING_MODEL", "BAAI/bge-m3")


def get_chunk_max_tokens() -> int:
    """Max tokens per chunk for the search chunker (LIT_QUERY_CHUNK_MAX_TOKENS)."""
    return int(os.environ.get("LIT_QUERY_CHUNK_MAX_TOKENS", "512"))


# BGE-M3 dense vector dimension (model-fixed, not an env var).
DENSE_DIM = 1024
