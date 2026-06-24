"""
ingest.py — Scan corpus, parse PDFs/MD with Docling, chunk with HybridChunker,
embed with BGE-M3, and upsert into Qdrant.

Usage:
    python3 scripts/ingest.py [--corpus /path] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    CHUNK_MAX_TOKENS,
    DENSE_DIM,
    EMBEDDING_MODEL,
    LIT_QUERY_COLLECTION,
    LIT_QUERY_DB,
    LIT_QUERY_CORPUS,
    get_all_corpus_paths,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_section(headings: list[str] | None) -> str:
    """Map heading text to a canonical section type."""
    if not headings:
        return "Other"
    text = " ".join(headings).lower()
    for keyword, label in [
        ("abstract", "Abstract"),
        ("introduction", "Introduction"),
        ("method", "Methods"),
        ("material", "Methods"),
        ("result", "Results"),
        ("discussion", "Discussion"),
        ("conclusion", "Discussion"),
        ("references", "References"),
    ]:
        if keyword in text:
            return label
    return "Other"


def _extract_page(chunk) -> int | None:
    """Extract page number from the first doc_item provenance."""
    try:
        return chunk.meta.doc_items[0].prov[0].page_no
    except (IndexError, AttributeError):
        return None


def _extract_year(filename: str) -> int | None:
    """Try to extract a year (1900-2099) from a filename."""
    m = re.search(r"(19|20)\d{2}", filename)
    return int(m.group()) if m else None


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest(db_path: Path) -> dict:
    manifest_path = db_path / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            return json.load(f)
    return {}


def _save_manifest(db_path: Path, manifest: dict) -> None:
    db_path.mkdir(parents=True, exist_ok=True)
    with open(db_path / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)


def to_sparse_vector(lexical_weights: dict):
    """Convert BGE-M3 lexical_weights dict to Qdrant SparseVector."""
    from qdrant_client import models  # local import to allow --dry-run without qdrant

    indices = [int(k) for k in lexical_weights.keys()]
    values = list(lexical_weights.values())
    return models.SparseVector(indices=indices, values=values)


# ---------------------------------------------------------------------------
# Collection setup
# ---------------------------------------------------------------------------

def _ensure_collection(client, collection_name: str) -> None:
    """Create the collection if it doesn't exist yet."""
    from qdrant_client import models

    existing = [c.name for c in client.get_collections().collections]
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=DENSE_DIM,
                    distance=models.Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(),
            },
        )
        print(f"[ingest] Created collection '{collection_name}'")


def _delete_file_points(client, collection_name: str, filename: str) -> None:
    """Delete all existing points whose payload.source equals filename."""
    from qdrant_client import models

    client.delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source",
                        match=models.MatchValue(value=filename),
                    )
                ]
            )
        ),
    )


# ---------------------------------------------------------------------------
# Ingest one file
# ---------------------------------------------------------------------------

def ingest_file(
    file_path: Path,
    client,
    model,
    chunker_cls,
    collection_name: str,
    dry_run: bool = False,
) -> int:
    """Parse, chunk, embed and upsert one file. Returns number of chunks."""
    from docling.document_converter import DocumentConverter

    print(f"[ingest] Processing {file_path.name} ...", flush=True)

    # --- Parse ---
    try:
        converter = DocumentConverter()
        result = converter.convert(str(file_path))
        dl_doc = result.document
    except Exception as exc:
        print(f"[ingest] WARNING: failed to parse {file_path.name}: {exc}")
        return 0

    # --- Chunk ---
    chunker = chunker_cls(
        tokenizer=EMBEDDING_MODEL,
        max_tokens=CHUNK_MAX_TOKENS,
    )
    chunks = list(chunker.chunk(dl_doc=dl_doc))

    if not chunks:
        print(f"[ingest] WARNING: no chunks produced for {file_path.name}")
        return 0

    if dry_run:
        print(f"[ingest] dry-run: {file_path.name} → {len(chunks)} chunks (skipping embed)")
        return len(chunks)

    # --- Embed ---
    texts = [chunker.contextualize(chunk) for chunk in chunks]
    output = model.encode(
        texts,
        return_dense=True,
        return_sparse=True,
        batch_size=12,
        max_length=8192,
    )
    dense_vecs = output["dense_vecs"]          # ndarray [N, 1024]
    sparse_dicts = output["lexical_weights"]   # list[dict[str, float]]

    # --- Delete old points for this file ---
    _delete_file_points(client, collection_name, file_path.name)

    # --- Upsert ---
    from qdrant_client import models

    year = _extract_year(file_path.name)
    title = getattr(dl_doc, "name", None) or file_path.stem

    points = [
        models.PointStruct(
            id=str(uuid.uuid4()),
            vector={
                "dense": dense_vecs[i].tolist(),
                "sparse": to_sparse_vector(sparse_dicts[i]),
            },
            payload={
                "source": file_path.name,
                "title": title,
                "section_type": _classify_section(chunk.meta.headings),
                "headings": chunk.meta.headings,
                "chunk_index": i,
                "page": _extract_page(chunk),
                "year": year,
                "text": texts[i],
            },
        )
        for i, chunk in enumerate(chunks)
    ]

    client.upsert(collection_name=collection_name, points=points)
    print(f"[ingest] {file_path.name} → {len(points)} chunks upserted")
    return len(points)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest academic papers into the search index.")
    parser.add_argument("--corpus", help="Override LIT_QUERY_CORPUS env var")
    parser.add_argument("--dry-run", action="store_true", help="List files without embedding")
    parser.add_argument("--force", action="store_true", help="Re-ingest all files, ignoring manifest")
    args = parser.parse_args()

    # Resolve corpus paths (--corpus flag overrides env; otherwise use all configured paths)
    SKIP_NAMES = {"README.md", "index.md", "INDEX.md"}

    if args.corpus:
        corpus_override = Path(args.corpus)
        if not corpus_override.exists():
            print(f"[ingest] ERROR: corpus path does not exist: {corpus_override}")
            sys.exit(1)
        corpus_paths = [corpus_override]
    else:
        corpus_paths = get_all_corpus_paths()
        if not corpus_paths:
            print("[ingest] ERROR: no valid corpus paths found. "
                  "Use --corpus, LIT_QUERY_CORPUS, or LIT_QUERY_CORPUS_EXTRA")
            sys.exit(1)

    # Discover files across all corpus paths
    files: list[Path] = []
    for corpus in corpus_paths:
        corpus_files = [
            p for p in sorted(list(corpus.rglob("*.pdf")) + list(corpus.rglob("*.md")))
            if p.name not in SKIP_NAMES
        ]
        print(f"[ingest] Found {len(corpus_files)} file(s) in {corpus}")
        files.extend(corpus_files)

    if not files:
        print("[ingest] No PDF or MD files found in any corpus path")
        sys.exit(0)

    print(f"[ingest] Total: {len(files)} file(s) across {len(corpus_paths)} corpus path(s)")

    # Load manifest
    manifest = _load_manifest(LIT_QUERY_DB)

    # Determine which files need processing
    to_process: list[Path] = []
    for f in files:
        key = str(f)
        current_hash = _md5(f)
        if not args.force and manifest.get(key) == current_hash:
            print(f"[ingest] Skipping (unchanged): {f.name}")
        else:
            to_process.append(f)

    if not to_process:
        print("[ingest] All files are up-to-date. Nothing to do.")
        sys.exit(0)

    print(f"[ingest] Will process {len(to_process)} file(s)")

    if args.dry_run:
        for f in to_process:
            print(f"  [dry-run] {f.name}")
        sys.exit(0)

    # Lazy imports (allow --dry-run without heavy deps)
    try:
        from FlagEmbedding import BGEM3FlagModel
        from docling.chunking import HybridChunker
        from qdrant_client import QdrantClient
    except ImportError as exc:
        print(f"[ingest] ERROR: missing dependency — {exc}")
        print("         Run: pip install docling FlagEmbedding qdrant-client")
        sys.exit(1)

    # Init Qdrant
    LIT_QUERY_DB.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(LIT_QUERY_DB))
    _ensure_collection(client, LIT_QUERY_COLLECTION)

    # Load embedding model once
    print(f"[ingest] Loading embedding model {EMBEDDING_MODEL} ...")
    model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=True)

    # Process each file
    for f in to_process:
        n = ingest_file(
            file_path=f,
            client=client,
            model=model,
            chunker_cls=HybridChunker,
            collection_name=LIT_QUERY_COLLECTION,
        )
        if n > 0 or True:  # update manifest even for 0-chunk files to avoid retrying
            manifest[str(f)] = _md5(f)
            _save_manifest(LIT_QUERY_DB, manifest)

    print("[ingest] Done.")


if __name__ == "__main__":
    main()
