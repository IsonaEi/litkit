# litkit

A small, scriptable toolkit for working with scientific literature, built as
four composable command-line stages:

```
  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
  │ discover  │ →  │  manage   │ →  │   notes   │ →  │  search   │
  │ find      │    │ build a   │    │ annotate  │    │ search    │
  │ papers    │    │ PDF       │    │ with a    │    │ your own  │
  │ across 5  │    │ library:  │    │ structured│    │ corpus    │
  │ sources,  │    │ download, │    │ 7-section │    │ (BGE-M3 + │
  │ rank (BM25)    │ convert,  │    │ template  │    │ Qdrant)   │
  │           │    │ audit     │    │           │    │           │
  └───────────┘    └───────────┘    └───────────┘    └─────┬─────┘
        ▲                                                  │
        └──────────────────────────────────────────────────┘
          the notes you write become the corpus that search
          indexes — and that discover's re-ranker scores against
```

1. **[discover](discover/)** — Search PubMed, bioRxiv, arXiv, Semantic Scholar
   and journal RSS feeds in parallel, deduplicate, and rank results with a
   hand-written BM25-style scorer (plus an optional semantic re-ranker). Emits a
   ranked markdown digest and JSON candidate lists.
2. **[manage](manage/)** — Turn a DOI into an organised local library: download
   the open-access PDF, convert it to markdown, enrich metadata from Semantic
   Scholar, and audit the collection for consistency.
3. **[notes](notes/)** — Annotate each paper with a structured 7-section reading
   note (Known Premises / Gap & Problem / Methods / Results & Interpretation /
   Core Contribution / Limitations & Critique / Connections), every section
   anchored by a verbatim source quote. A template + a runner-agnostic LLM-agent
   prompt; no code, no extra dependency.
4. **[search](search/)** — Index your local PDF/markdown library with Docling
   chunking and BGE-M3 hybrid (dense + sparse) embeddings into Qdrant, then run
   hybrid semantic + lexical search with RRF fusion.

The four stages are independent — use any one on its own — but they chain
naturally, and they close into a loop:

- the JSON `candidates` file from **discover** feeds DOIs into **manage**;
- the library that **manage** builds is what you annotate in **notes**;
- the notes you write become part of the corpus that **search** indexes **and**
  that **discover**'s optional Stage-2 re-ranker scores new papers against — so
  the more you read and annotate, the sharper both discovery and retrieval get.

litkit is one importable package (`litkit`) with a three-layer design — a core
library of pure functions, a human CLI, and an MCP server for AI agents — all
calling the same stage functions.

## Use as an MCP server

litkit ships an [MCP](https://modelcontextprotocol.io/) server (`litkit-mcp`,
stdio transport) so an AI agent (Claude Desktop, Claude Code, or any MCP client)
can drive the whole pipeline. The server is provider-agnostic — it makes no LLM
calls of its own; it only exposes tools, a prompt, and resources.

```bash
git clone https://github.com/IsonaEi/litkit.git
cd litkit
pip install -e ".[all]"     # includes the `mcp` package (FastMCP)
```

Add it to your client config (Claude Desktop / Claude Code):

```json
{
  "mcpServers": {
    "litkit": {
      "command": "litkit-mcp",
      "env": {
        "LIT_QUERY_CORPUS": "/path/to/library",
        "S2_API_KEY": "...",
        "ENTREZ_EMAIL": "you@example.com"
      }
    }
  }
}
```

It exposes:

| Kind | Name | When the agent uses it |
|------|------|------------------------|
| tool | `discover_papers(keywords, sources?, max_results?)` | Find new papers online, ranked |
| tool | `download_paper(doi, dest_dir?, enable_scihub?)` | Fetch a PDF by DOI (legal sources first; Sci-Hub opt-in) |
| tool | `convert_to_markdown(pdf_path)` | Turn a local PDF into markdown text |
| tool | `enrich_metadata(library_dir)` | Fill missing metadata in a library `index.json` |
| tool | `ingest_library(corpus_dir?, force?)` | Index a corpus so it becomes searchable |
| tool | `search_library(query, top_k?, section?)` | Search the user's *own* indexed corpus |
| prompt | `write_reading_note(paper_path)` | The 7-section reading-note template + filling instructions |
| resource | `litkit://note-template` | The reading-note template markdown |
| resource | `litkit://categories-example` | The example category taxonomy markdown |

> Heavy, stage-specific dependencies are imported lazily, so the MCP server
> starts cleanly even without the `discover`/`search` extras — a missing
> dependency only surfaces (as a clear `pip install 'litkit[...]'` message) when
> the corresponding tool is actually invoked.

## CLI quickstart

```bash
# Install only the stages you need (extras are per-tool):
pip install -e ".[discover]"   # paper discovery + ranking
pip install -e ".[manage]"     # metadata enrichment
pip install -e ".[search]"     # local semantic search
pip install -e ".[all]"        # everything (incl. the MCP server)

# Configure environment (see .env.example for all variables):
cp .env.example .env && $EDITOR .env

# 1. Discover — print a ranked digest of recent papers:
ENTREZ_EMAIL=you@example.com litkit-discover --once

# 2. Manage — download a paper by DOI and convert it to markdown:
bash scripts/download.sh "10.7554/eLife.12345" library/papers/
bash scripts/convert.sh  library/papers/10-7554_eLife-12345.pdf

# 3. Notes — annotate a paper with the structured template (by hand, or via the
#    MCP `write_reading_note` prompt / `litkit://note-template` resource):
#    the template lives in the package — print it with:
python3 -c "from litkit.notes import load_template; print(load_template())"

# 4. Search — index your library + notes, then query:
export LIT_QUERY_CORPUS="$PWD/library"
litkit-ingest
litkit-search "place cells remapping" --format text
```

The console scripts (`litkit-discover`, `litkit-search`, `litkit-ingest`,
`litkit-enrich`) are equivalent to `python -m litkit.cli <stage> ...`.

> **No-network smoke test for discover:**
> `litkit-discover --test` runs the whole pipeline against built-in dummy data —
> no API keys, no network.

## Dependency extras

`litkit` is published with per-stage [optional dependencies](pyproject.toml) so
you only install what you use:

| Extra | Stage | Pulls in |
|-------|-------|----------|
| `discover` | discover | `biopython`, `requests`, `feedparser` |
| `discover-rerank` | discover (optional) | `sentence-transformers`, `numpy` |
| `manage` | manage | `requests` |
| — | notes | nothing — markdown template + LLM-agent prompt, no Python deps |
| `search` | search | `docling`, `FlagEmbedding`, `qdrant-client` |
| `mcp` | MCP server | `mcp` (FastMCP) |
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
