# search

Stage 3 of [litkit](../README.md). Hybrid semantic + lexical search over your
own local literature corpus, with no persistent server and no data leaving your
machine.

## What it does

- **Docling** parses PDFs/markdown into structured documents with section
  headings.
- **HybridChunker** splits them into section-aware chunks (~512 tokens).
- **BGE-M3** produces dense + sparse embeddings per chunk.
- **Qdrant** (embedded, on-disk) stores them and searches with **RRF fusion**
  combining dense and sparse retrieval.

`ingest.py` and `search.py` are independent CLI calls — the embedding model
loads on demand and is released when the process exits.

## Install

```bash
pip install -e ".[search]"     # from the repo root
```

> The first run downloads the BGE-M3 model (~2.3 GB) to `~/.cache/huggingface/`.
> A GPU (~3–4 GB VRAM, FP16) makes ingest much faster; CPU works but is slower.

## Usage

```bash
# Point at your corpus and index it (idempotent — skips unchanged files):
export LIT_QUERY_CORPUS="/path/to/your/library"
python3 scripts/ingest.py

# Preview what would be ingested without embedding or writing:
python3 scripts/ingest.py --dry-run

# Force a full re-process:
python3 scripts/ingest.py --force

# Search (JSON output, top-8 by default):
python3 scripts/search.py "dopamine reward prediction error" --top-k 8

# Human-readable output:
python3 scripts/search.py "spatial memory" --format text

# Restrict to a paper section:
python3 scripts/search.py "stimulation protocol" --section-filter Methods
```

Valid `--section-filter` values: `Abstract`, `Introduction`, `Methods`,
`Results`, `Discussion`, `References`, `Other`.

## Multi-corpus indexing

Index several directories at once with `LIT_QUERY_CORPUS_EXTRA` (comma-separated
paths, added to the primary `LIT_QUERY_CORPUS`):

```bash
export LIT_QUERY_CORPUS="$PWD/library/notes"
export LIT_QUERY_CORPUS_EXTRA="$PWD/library/cat-a/markdown,$PWD/library/cat-b/markdown"
python3 scripts/ingest.py
```

Re-run `ingest.py` after adding new files; unchanged files (tracked by MD5 in
`manifest.json`) are skipped automatically.

## Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `LIT_QUERY_CORPUS` | **Yes** | — | Directory of PDF/MD papers to index |
| `LIT_QUERY_CORPUS_EXTRA` | No | — | Extra corpus directories (comma-separated) |
| `LIT_QUERY_DB` | No | `~/.lit-query/qdrant_storage` | Qdrant on-disk storage path |
| `LIT_QUERY_COLLECTION` | No | `literature` | Qdrant collection name |
| `LIT_QUERY_EMBEDDING_MODEL` | No | `BAAI/bge-m3` | HuggingFace embedding model |
| `LIT_QUERY_CHUNK_MAX_TOKENS` | No | `512` | Max tokens per chunk |

## Output

`search.py` returns one record per result with `rank`, `score` (RRF), `title`,
`source` (the filename in your corpus), `section_type`, `headings`, `page`,
`year`, and the chunk `text`.

> The RRF `score` is a rank-combination score, not an absolute similarity — it
> is comparable *within* one query, not across queries. Don't apply a fixed
> threshold; read the top few results instead.

## Further reading

- [references/setup.md](references/setup.md) — detailed setup, hardware notes,
  and troubleshooting.
- [references/query-patterns.md](references/query-patterns.md) — query tips,
  section filtering, and result interpretation.
