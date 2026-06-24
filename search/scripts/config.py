"""Central config — all paths from environment variables."""
import os
from pathlib import Path

# Required: corpus directory (no default — must be set by the user)
_corpus_raw = os.environ.get("LIT_QUERY_CORPUS", "")
LIT_QUERY_CORPUS: Path | None = Path(_corpus_raw) if _corpus_raw else None

# Multi-corpus support: comma-separated paths (optional)
_corpus_extra_raw = os.environ.get("LIT_QUERY_CORPUS_EXTRA", "")
LIT_QUERY_CORPUS_EXTRA: list[Path] = [
    Path(p.strip()) for p in _corpus_extra_raw.split(",") if p.strip()
] if _corpus_extra_raw else []


def get_all_corpus_paths() -> list[Path]:
    """Return all corpus paths (primary + extras) that exist on disk."""
    paths = []
    if LIT_QUERY_CORPUS:
        paths.append(LIT_QUERY_CORPUS)
    paths.extend(LIT_QUERY_CORPUS_EXTRA)
    return [p for p in paths if p.exists()]

# Qdrant storage path
LIT_QUERY_DB = Path(os.environ.get(
    "LIT_QUERY_DB",
    str(Path.home() / ".lit-query" / "qdrant_storage"),
))

# Collection name
LIT_QUERY_COLLECTION = os.environ.get("LIT_QUERY_COLLECTION", "literature")

# Embedding model (HuggingFace model name)
EMBEDDING_MODEL = os.environ.get("LIT_QUERY_EMBEDDING_MODEL", "BAAI/bge-m3")

# HybridChunker token upper limit (aligned with embedding model tokenizer)
CHUNK_MAX_TOKENS = int(os.environ.get("LIT_QUERY_CHUNK_MAX_TOKENS", "512"))

# BGE-M3 dense vector dimension
DENSE_DIM = 1024
