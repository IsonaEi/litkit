# manage

Stage 2 of [litkit](../README.md). Build and maintain a local literature
library: **download** a paper by DOI, **convert** it to markdown, **enrich** its
metadata from Semantic Scholar, and **audit** the collection for consistency.

## What it does

- `download.sh` — Resolve a DOI (or URL) to a PDF, trying legal sources in
  order: a direct URL, then publisher PDF patterns (Nature, eLife, bioRxiv,
  PNAS, Frontiers, Springer/BMC), then EuropePMC, then arXiv. A Sci-Hub fallback
  exists but is **off by default and opt-in only** (see below).
- `convert.sh` — Convert a PDF to markdown via `pdftotext`, falling back to
  `uvx markitdown[pdf]` for higher fidelity.
- `verify.sh` — Check a single PDF + markdown pair (valid PDF, extractable
  title, non-empty/reasonably-sized markdown).
- `audit.sh` — Full audit of a `references/` directory: PDF validity, every PDF
  has a matching markdown, and `index.json` integrity (valid JSON, paths exist,
  no duplicate IDs, counts match).
- `litkit-enrich` — Fill missing `abstract`/`year`/`authors` and refresh
  `citation_count` in an `index.json` from Semantic Scholar. Idempotent.
  (`litkit.manage.enrich.enrich_library` from Python; the MCP `enrich_metadata`
  tool for agents.)

## Install

```bash
pip install -e ".[manage]"      # from the repo root (installs requests)
```

System tools used by the shell scripts:

- `curl` — downloading
- `pdftotext` (poppler-utils) — PDF text extraction
- `file` (coreutils) — PDF validation
- `python3` — JSON processing in `audit.sh`
- `uvx markitdown[pdf]` (optional) — higher-fidelity PDF→markdown fallback.
  Note: plain `uvx markitdown` does **not** handle PDFs — the `[pdf]` extra is
  required.

## Usage

```bash
# Download a paper by DOI into a directory (legal sources only):
bash scripts/download.sh "10.1038/s41592-024-02200-1" library/papers/

# Convert a PDF to markdown:
bash scripts/convert.sh library/papers/10-1038_s41592-024-02200-1.pdf

# Verify one PDF + markdown pair:
bash scripts/verify.sh paper.pdf paper.md

# Full audit of a references/ tree:
bash scripts/audit.sh library/

# Enrich an index.json in place with Semantic Scholar metadata:
litkit-enrich --input library/index.json --output library/index.json
litkit-enrich --library library/ --dry-run
```

### Suggested library layout

```
library/
├── index.json                 # machine index (one object per paper)
├── README.md                  # optional human index
├── <category>/
│   ├── papers/                # PDFs
│   └── markdown/              # converted text
```

`audit.sh` expects PDFs under `*/papers/*.pdf` and converted text under the
sibling `*/markdown/*.md`. `index.json` may be either a bare list of paper
objects or `{"papers": [...]}`.

## The Sci-Hub fallback (opt-in)

`download.sh` does **not** use Sci-Hub by default. It is attempted only when you
explicitly opt in, via either:

- the `--enable-scihub` flag: `bash scripts/download.sh --enable-scihub <DOI> <dir>`, or
- the environment variable `LITKIT_ENABLE_SCIHUB=1`.

When enabled, the script prints a disclaimer to stderr noting that accessing
papers this way may violate publisher terms of service or copyright law in your
jurisdiction, that **you are solely responsible** for ensuring your use is legal
and ethical, and that the recommended sources are the publisher, EuropePMC, and
arXiv — which are always tried first.

## Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `S2_API_KEY` | No | — | Semantic Scholar API key for `litkit-enrich` (raises rate limits) |
| `LITKIT_ENABLE_SCIHUB` | No | `0` (off) | Set to `1` to allow the opt-in Sci-Hub download fallback |
