# Output Schema — discover

The `discover` tool produces two JSON files per run (in `--cron` mode) and one
markdown digest.

---

## Paper Object (shared schema)

Each paper in the output arrays follows this schema:

```json
{
  "title": "string — paper title",
  "authors": ["string — author names"],
  "date": "YYYY-MM-DD — publication date",
  "source": "pubmed | biorxiv | arxiv | semantic_scholar | journal_rss",
  "url": "string — canonical paper URL",
  "doi": "string | null — DOI if available",
  "abstract_snippet": "string — first 300 chars of abstract",
  "citation_count": "integer | null — citation count (Semantic Scholar only)",
  "relevance_score": "float 0–10 — computed by merge_and_rank",
  "keyword_hits": ["string — matched keywords"],
  "ingestion_candidate": "boolean — true if score >= relevance_threshold",
  "feed": "string — RSS feed name (journal_rss source only)"
}
```

---

## scout-YYYY-MM-DD.json

Full ranked list of all deduplicated papers from this run.

- **Type:** `array<Paper>`
- **Sorted:** descending by `relevance_score`
- **Contains:** all papers (including those below threshold)

---

## candidates-YYYY-MM-DD.json

Subset of papers flagged as ingestion candidates.

- **Type:** `array<Paper>`
- **Filter:** `ingestion_candidate == true` (i.e., `relevance_score >= relevance_threshold`)
- **Use case:** feed into the `manage` tool for batch download

### Consuming candidates with the manage tool

```bash
# Extract DOIs from candidates for batch download
cat candidates-2026-03-23.json | python3 -c "
import json, sys
papers = json.load(sys.stdin)
for p in papers:
    doi = p.get('doi')
    if doi:
        print(doi)
"
```

---

## digest-YYYY-MM-DD.md (markdown)

Human-readable digest of the top N papers (default: 10).

Format:
```
📚 Literature Scout — YYYY-MM-DD
Found N papers across sources (M after dedup) · Scoring: BM25+cluster

Top Papers:
1. [Title](url) — Author et al., source
   > Abstract snippet... Relevance: X/10 · Keywords: kw1, kw2

🔬 N papers flagged for ingestion
```

---

## Relevance Scoring Formula

Each paper is scored 0–10 by `merge_and_rank.py`:

```
bm25_score = min(8.0, sum(tf * idf for each matched keyword) / 2)
           + cluster_bonus     # ≥2 keywords from one cluster, capped at +3.0
           + citation_bonus    # log(citations+1)/log(100), capped at +1.0
           + recency_bonus     # +1.0 if ≤3 days old, +0.5 if ≤7 days old

# Optional Stage 2 (only when LITKIT_CORPUS_DIR is set and
# sentence-transformers is installed):
final_score = bm25_score * 0.6 + corpus_affinity_score * 10 * 0.4
```

where:

- **TF** counts keyword frequency in the title (weighted ×2) plus the abstract.
- **IDF** = `log((N+1)/(df+1))`, so rare-but-specific keywords score higher.
- **corpus_affinity_score** is the mean of the top-3 cosine similarities between
  the paper and your reference corpus.

A paper is flagged as an `ingestion_candidate` when its `relevance_score` is at
least `relevance_threshold` (set in your search config; the example config uses
`7`).
