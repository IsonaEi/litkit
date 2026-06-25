# search: Query Patterns Guide

## When to Use

This tool answers questions about your own ingested corpus, such as:

- "which papers discuss X"
- "find papers about X"
- "I read about X somewhere"
- "papers supporting the claim that X"
- "what does my corpus say about X"
- "do any of my papers cover X"

**NOT for:** internet search (use the [discover](../../discover/) stage),
downloading new papers (use [manage](../../manage/)), or papers not yet
ingested.

---

## Basic Usage

```bash
# Default: JSON output, top-8 results
litkit-search "your query here"

# Human-readable (easier to scan quickly)
litkit-search "your query" --format text --top-k 5

# More results
litkit-search "your query" --top-k 20
```

---

## Section Filtering

Use `--section-filter` to restrict results to a specific paper section.
Valid values: `Abstract`, `Introduction`, `Methods`, `Results`, `Discussion`, `References`, `Other`.

```bash
# Find experimental protocols
litkit-search "optogenetic stimulation protocol" --section-filter Methods

# Find quantitative outcomes
litkit-search "accuracy F1 score" --section-filter Results

# Find conceptual framing
litkit-search "theoretical framework" --section-filter Introduction

# Find summary/interpretation
litkit-search "limitations future work" --section-filter Discussion
```

---

## Interpreting Results

### RRF Score

The `score` field reflects **Reciprocal Rank Fusion (RRF)** — a rank-combination
score, not an absolute similarity measure.

- **Scores are relative within a single query**, not comparable across queries.
- Do **not** use a fixed threshold (e.g., "only use results with score > 0.5").
- Rank 1 is simply more relevant than rank 2, but a rank-5 result may still be
  highly relevant depending on your corpus size.

**Rule of thumb:** read top-3 in full; skim rank 4–8 for additional context.

### JSON Output Schema

```json
[
  {
    "rank": 1,
    "score": 0.8234,
    "title": "Paper Title",
    "source": "2023_author_paper.pdf",
    "section_type": "Results",
    "headings": ["Results", "3.2 Behavioral Analysis"],
    "page": 7,
    "year": 2023,
    "text": "The contextualized chunk text..."
  }
]
```

- `source` — use this to identify the paper (filename in your corpus)
- `section_type` — normalized section label (`Methods`, `Results`, etc.)
- `headings` — raw heading list from Docling (more precise than `section_type`)
- `text` — the actual chunk content (first 200 chars shown in `--format text`)

---

## Token-Efficient Agent Workflow

1. **Call search:** `litkit-search "query" --top-k 8 --format json`
2. **Scan titles + section_type** of all 8 results to identify relevance.
3. **Deep-read `text`** for top-3 only.
4. **Cite by `source`** (filename) when referencing findings.
5. **Refine with section filter** if results are too broad.

Avoid loading full paper text into context. The `text` field already provides
the most relevant chunk; use it directly for synthesis.

---

## Re-ingest Reminder

Results are only as current as your last ingest run.  
If you've added new papers, re-ingest before searching:

```bash
litkit-ingest   # skips unchanged files automatically
```
