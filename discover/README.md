# discover

Stage 1 of [litkit](../README.md). Search five academic sources in parallel —
**PubMed, bioRxiv, arXiv, Semantic Scholar, and journal RSS** — deduplicate the
results, score them with a hand-written BM25-style ranker, and emit a ranked
markdown digest (plus JSON candidate lists for the [manage](../manage/) stage).

## What it does

- Runs one scout per source concurrently, each producing a normalised paper
  record (title, authors, date, DOI, abstract snippet, citations, source).
- Deduplicates by DOI and fuzzy title match.
- Scores each paper 0–10 with `merge_and_rank.py`:
  - **TF-IDF** over your keyword clusters (title hits weighted ×2),
  - a **cluster bonus** rewarding papers that hit several keywords in one
    cluster,
  - a log-scaled **citation bonus**, and a **recency bonus**.
  - Optionally re-ranks by semantic similarity to a corpus of papers you already
    consider relevant (Stage 2, see `LITKIT_CORPUS_DIR` below).
- Flags papers above `relevance_threshold` as ingestion candidates.

## Install

```bash
pip install -e ".[discover]"           # from the repo root
# Optional semantic re-ranker:
pip install -e ".[discover-rerank]"
```

## Usage

```bash
# Print a ranked digest of recent papers to stdout (default mode):
ENTREZ_EMAIL=you@example.com litkit-discover --once

# Override the query and write the digest to a file:
ENTREZ_EMAIL=you@example.com litkit-discover \
    --once --query "place cells navigation" --output digest.md

# Restrict to specific sources:
litkit-discover --once --sources pubmed,biorxiv

# Scheduled run — writes JSON + digest + log to $LITKIT_OUTPUT:
ENTREZ_EMAIL=you@example.com litkit-discover --cron

# No-network smoke test (dummy data from every source, no API keys):
litkit-discover --test
```

`litkit-discover` is equivalent to `python -m litkit.cli discover`. From Python,
call `litkit.discover.discover_papers(keywords=[...], sources=[...])` directly to
get the ranked list of paper dicts; an AI agent gets the same via the MCP
`discover_papers` tool.

## Configuration

Copy the bundled example config and edit the keyword clusters, sources, lookback
window, and RSS feed list (the example ships inside the package — print it with
`python3 -c "from litkit.config import get_discover_config_path as p; print(open(p()).read())"`):

```bash
python3 -c "from litkit.config import get_discover_config_path as p; print(open(p()).read())" \
    > my-search-config.json
$EDITOR my-search-config.json
export LITKIT_CONFIG="$PWD/my-search-config.json"
```

Key fields: `keyword_clusters`, `lookback_days`, `relevance_threshold`,
`max_digest_papers`, `rss_feeds`, `sources`, `scout_timeout_s`.

## Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `ENTREZ_EMAIL` | Yes (for PubMed) | — | NCBI Entrez API contact requirement |
| `S2_API_KEY` | No | — | Semantic Scholar API key (raises rate limits) |
| `LITKIT_CONFIG` | No | bundled `search-config-example.json` | Path to your search config JSON |
| `LITKIT_OUTPUT` | No | `/tmp/litkit-discover` | Output directory for `--cron` mode |
| `LITKIT_CORPUS_DIR` | No | — | Directory of `.md` notes for Stage-2 corpus-affinity re-ranking. Unset = BM25-only. |
| `LITKIT_NOTIFY_CMD` | No | — | Shell command to fire when a cron digest is ready (summary text appended as a final argument). Unset = no notification. |

## Output

| Mode | Output |
|------|--------|
| `--once` | Markdown digest → stdout (or `--output` path) |
| `--cron` | `$LITKIT_OUTPUT/scout-YYYY-MM-DD.json` (full ranked list) + `candidates-YYYY-MM-DD.json` (above threshold) + `digest-YYYY-MM-DD.md` + `scout.log` |

The full paper-object schema and the scoring formula are documented in
[references/output-schema.md](references/output-schema.md).

## Hand off to the next stage

The `candidates-YYYY-MM-DD.json` file is designed to feed the
[manage](../manage/) stage. Extract DOIs and batch-download:

```bash
python3 -c "import json,sys; [print(p['doi']) for p in json.load(open(sys.argv[1])) if p.get('doi')]" \
    candidates-2026-03-23.json | while read doi; do
        bash ../scripts/download.sh "$doi" library/papers/
done
```

## Scheduling

To run periodically, wire `litkit-discover --cron` into any scheduler (`cron`,
systemd timers, etc.). Example weekly crontab entry (Mondays 9 AM):

```cron
0 9 * * 1 ENTREZ_EMAIL=you@example.com LITKIT_CONFIG=/path/to/search-config.json litkit-discover --cron
```
