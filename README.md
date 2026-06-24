# litkit

A small, scriptable toolkit for working with scientific literature, built as
three composable command-line stages:

```
  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
  │  discover   │  →   │   manage    │  →   │   search    │
  │ find papers │      │ build a PDF │      │ semantically│
  │ across 5    │      │ library:    │      │ search your │
  │ sources,    │      │ download,   │      │ own corpus  │
  │ rank them   │      │ convert,    │      │ (BGE-M3 +   │
  │ (BM25)      │      │ audit       │      │ Qdrant)     │
  └─────────────┘      └─────────────┘      └─────────────┘
```

1. **[discover](discover/)** — Search PubMed, bioRxiv, arXiv, Semantic Scholar
   and journal RSS feeds in parallel, deduplicate, and rank results with a
   hand-written BM25-style scorer (plus an optional semantic re-ranker). Emits a
   ranked markdown digest and JSON candidate lists.
2. **[manage](manage/)** — Turn a DOI into an organised local library: download
   the open-access PDF, convert it to markdown, enrich metadata from Semantic
   Scholar, and audit the collection for consistency.
3. **[search](search/)** — Index your local PDF/markdown library with Docling
   chunking and BGE-M3 hybrid (dense + sparse) embeddings into Qdrant, then run
   hybrid semantic + lexical search with RRF fusion.

The three stages are independent — use any one on its own — but they chain
naturally: the JSON `candidates` file from **discover** feeds DOIs into
**manage**, and the library that **manage** builds is exactly what **search**
indexes.

## Quickstart

```bash
git clone https://github.com/IsonaEi/litkit.git
cd litkit

# Install only the stages you need (extras are per-tool):
pip install -e ".[discover]"   # paper discovery + ranking
pip install -e ".[manage]"     # metadata enrichment
pip install -e ".[search]"     # local semantic search
pip install -e ".[all]"        # everything

# Configure environment (see .env.example for all variables):
cp .env.example .env && $EDITOR .env

# 1. Discover — print a ranked digest of recent papers:
ENTREZ_EMAIL=you@example.com python3 discover/scripts/run_scout.py --once

# 2. Manage — download a paper by DOI and convert it to markdown:
bash manage/scripts/download.sh "10.7554/eLife.12345" library/papers/
bash manage/scripts/convert.sh  library/papers/10-7554_eLife-12345.pdf

# 3. Search — index a library, then query it:
export LIT_QUERY_CORPUS="$PWD/library"
python3 search/scripts/ingest.py
python3 search/scripts/search.py "place cells remapping" --format text
```

> **No-network smoke test for discover:**
> `python3 discover/scripts/run_scout.py --test` runs the whole pipeline against
> built-in dummy data — no API keys, no network.

## Dependency extras

`litkit` is published with per-stage [optional dependencies](pyproject.toml) so
you only install what you use:

| Extra | Stage | Pulls in |
|-------|-------|----------|
| `discover` | discover | `biopython`, `requests`, `feedparser` |
| `discover-rerank` | discover (optional) | `sentence-transformers`, `numpy` |
| `manage` | manage | `requests` |
| `search` | search | `docling`, `FlagEmbedding`, `qdrant-client` |
| `all` | — | all of the above |

The **manage** stage's download/convert/audit scripts also use these system
tools: `curl`, `pdftotext` (poppler-utils), `file`, and optionally
`uvx markitdown[pdf]`.

## Configuration & secrets

All configuration is read from environment variables — nothing is hardcoded.
API keys (`S2_API_KEY`, etc.) are read from the environment only. See
[.env.example](.env.example) for the full list, and each stage's README for a
per-tool environment-variable table.

## License

[Apache-2.0](LICENSE) © 2026 Meng-Xuan Liu
