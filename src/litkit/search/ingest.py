"""Index a corpus: parse with Docling, chunk, embed with BGE-M3, upsert to Qdrant.

The pure entry point is :func:`ingest`, which returns a structured summary dict.
Heavy dependencies (docling, FlagEmbedding, qdrant-client) are imported lazily;
``--dry-run`` works without them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from pathlib import Path

from litkit.config import (
    DENSE_DIM,
    get_all_corpus_paths,
    get_chunk_max_tokens,
    get_collection_name,
    get_db_path,
    get_embedding_model,
)

log = logging.getLogger(__name__)

SKIP_NAMES = {"README.md", "index.md", "INDEX.md"}


class SearchDependencyError(RuntimeError):
    """Raised when the search extras are not installed but are required."""


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    """Extract a page number from the first doc_item provenance."""
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
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
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


def _to_sparse_vector(lexical_weights: dict):
    """Convert BGE-M3 lexical_weights dict to a Qdrant SparseVector."""
    from qdrant_client import models

    indices = [int(k) for k in lexical_weights.keys()]
    values = list(lexical_weights.values())
    return models.SparseVector(indices=indices, values=values)


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
        log.info("Created collection '%s'", collection_name)


def _delete_file_points(client, collection_name: str, filename: str) -> None:
    """Delete all existing points whose payload.source equals ``filename``."""
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


def _ingest_file(
    file_path: Path,
    client,
    model,
    chunker_cls,
    collection_name: str,
    embedding_model: str,
    max_tokens: int,
) -> int:
    """Parse, chunk, embed and upsert one file. Returns the number of chunks."""
    from docling.document_converter import DocumentConverter

    log.info("Processing %s …", file_path.name)

    try:
        converter = DocumentConverter()
        result = converter.convert(str(file_path))
        dl_doc = result.document
    except Exception as exc:
        log.warning("failed to parse %s: %s", file_path.name, exc)
        return 0

    chunker = chunker_cls(tokenizer=embedding_model, max_tokens=max_tokens)
    chunks = list(chunker.chunk(dl_doc=dl_doc))
    if not chunks:
        log.warning("no chunks produced for %s", file_path.name)
        return 0

    texts = [chunker.contextualize(chunk) for chunk in chunks]
    output = model.encode(
        texts,
        return_dense=True,
        return_sparse=True,
        batch_size=12,
        max_length=8192,
    )
    dense_vecs = output["dense_vecs"]
    sparse_dicts = output["lexical_weights"]

    _delete_file_points(client, collection_name, file_path.name)

    from qdrant_client import models

    year = _extract_year(file_path.name)
    title = getattr(dl_doc, "name", None) or file_path.stem

    points = [
        models.PointStruct(
            id=str(uuid.uuid4()),
            vector={
                "dense": dense_vecs[i].tolist(),
                "sparse": _to_sparse_vector(sparse_dicts[i]),
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
    log.info("%s → %d chunks upserted", file_path.name, len(points))
    return len(points)


# ── Public entry point ────────────────────────────────────────────────────────

def ingest(
    corpus_dir: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Scan a corpus and index it into the Qdrant store.

    Parameters
    ----------
    corpus_dir:
        Corpus directory to index. ``None`` uses LIT_QUERY_CORPUS (+ EXTRA).
    dry_run:
        List the files that would be processed without embedding or writing.
    force:
        Re-ingest every file, ignoring the MD5 manifest.

    Returns
    -------
    dict
        ``{status, corpus_paths, found, to_process, processed, chunks, dry_run,
        files}`` summary. ``status`` is "ok", "dry_run", "no_files",
        "up_to_date", or "error" (with a ``message``).
    """
    if corpus_dir:
        override = Path(corpus_dir)
        if not override.exists():
            return {"status": "error", "message": f"corpus path does not exist: {override}"}
        corpus_paths = [override]
    else:
        corpus_paths = get_all_corpus_paths()
        if not corpus_paths:
            return {
                "status": "error",
                "message": "no valid corpus paths found. Set LIT_QUERY_CORPUS / "
                           "LIT_QUERY_CORPUS_EXTRA, or pass corpus_dir.",
            }

    files: list[Path] = []
    for corpus in corpus_paths:
        corpus_files = [
            p for p in sorted(list(corpus.rglob("*.pdf")) + list(corpus.rglob("*.md")))
            if p.name not in SKIP_NAMES
        ]
        log.info("Found %d file(s) in %s", len(corpus_files), corpus)
        files.extend(corpus_files)

    if not files:
        return {
            "status": "no_files",
            "corpus_paths": [str(p) for p in corpus_paths],
            "found": 0,
            "to_process": 0,
            "processed": 0,
            "chunks": 0,
            "dry_run": dry_run,
            "files": [],
        }

    db_path = get_db_path()
    manifest = _load_manifest(db_path)

    to_process: list[Path] = []
    for f in files:
        key = str(f)
        if not force and manifest.get(key) == _md5(f):
            log.info("Skipping (unchanged): %s", f.name)
        else:
            to_process.append(f)

    base = {
        "corpus_paths": [str(p) for p in corpus_paths],
        "found": len(files),
        "to_process": len(to_process),
        "dry_run": dry_run,
        "files": [f.name for f in to_process],
    }

    if not to_process:
        return {**base, "status": "up_to_date", "processed": 0, "chunks": 0}

    if dry_run:
        return {**base, "status": "dry_run", "processed": 0, "chunks": 0}

    try:
        from docling.chunking import HybridChunker
        from FlagEmbedding import BGEM3FlagModel
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise SearchDependencyError(
            f"missing search dependency — {exc}. "
            "Install it with: pip install 'litkit[search]'"
        ) from exc

    embedding_model = get_embedding_model()
    collection_name = get_collection_name()
    max_tokens = get_chunk_max_tokens()

    db_path.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(db_path))
    _ensure_collection(client, collection_name)

    log.info("Loading embedding model %s …", embedding_model)
    model = BGEM3FlagModel(embedding_model, use_fp16=True)

    total_chunks = 0
    for f in to_process:
        n = _ingest_file(
            file_path=f,
            client=client,
            model=model,
            chunker_cls=HybridChunker,
            collection_name=collection_name,
            embedding_model=embedding_model,
            max_tokens=max_tokens,
        )
        total_chunks += n
        # Update manifest even for 0-chunk files to avoid retrying broken PDFs.
        manifest[str(f)] = _md5(f)
        _save_manifest(db_path, manifest)

    return {
        **base,
        "status": "ok",
        "processed": len(to_process),
        "chunks": total_chunks,
    }
