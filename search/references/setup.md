# search Setup Guide

## 1. Dependencies

```bash
pip install docling FlagEmbedding qdrant-client
```

> First run will download the BGE-M3 model (~2.3 GB) to `~/.cache/huggingface/`.

---

## 2. Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LIT_QUERY_CORPUS` | **Yes** | — | Path to directory containing PDF/MD papers |
| `LIT_QUERY_DB` | No | `~/.lit-query/qdrant_storage` | Qdrant embedded DB storage path |
| `LIT_QUERY_COLLECTION` | No | `literature` | Qdrant collection name |
| `LIT_QUERY_EMBEDDING_MODEL` | No | `BAAI/bge-m3` | HuggingFace model name |
| `LIT_QUERY_CHUNK_MAX_TOKENS` | No | `512` | Max tokens per chunk |

---

## 3. First-Time Setup

**Step 1** — Export the corpus path:
```bash
export LIT_QUERY_CORPUS="/path/to/your/references"
```

**Step 2** — Preview what will be ingested (no embedding, no writes):
```bash
python3 scripts/ingest.py --dry-run
```

**Step 3** — Run full ingest:
```bash
python3 scripts/ingest.py
```

Expected time: ~30–60 min for 200 PDFs (Docling OCR) + ~10–20 min embedding (GPU).
CPU-only is supported but significantly slower.

---

## 4. Hardware Requirements

| Mode | VRAM | Notes |
|------|------|-------|
| GPU (recommended) | ~3–4 GB FP16 | RTX 3060 12 GB or equivalent |
| CPU | — | Works, but embedding is ~10× slower |

---

## 5. Re-ingest

Ingest is **idempotent** — files are tracked by MD5 hash in `manifest.json`
stored in `LIT_QUERY_DB`. Unchanged files are skipped automatically.

```bash
# Ingest only new/changed files
python3 scripts/ingest.py

# Force re-process all files
python3 scripts/ingest.py --force

# Add --corpus to override the env var
python3 scripts/ingest.py --corpus /path/to/new/batch
```

When a file is re-ingested, all existing Qdrant points for that file are
deleted before the new chunks are inserted (no duplicate chunks).

---

## 6. Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `LIT_QUERY_CORPUS is not set` | Env var missing | `export LIT_QUERY_CORPUS=...` |
| `Qdrant DB not found` | Ingest not run yet | Run `python3 scripts/ingest.py` |
| `Collection '...' is empty` | Ingest failed or wrong collection name | Check logs; set `LIT_QUERY_COLLECTION` |
| `ImportError: No module named 'docling'` | Dependencies missing | `pip install docling FlagEmbedding qdrant-client` |
| PDF parse warning | Corrupted or password-protected PDF | The file is skipped; manifest not updated (will retry next run) |
