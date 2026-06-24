#!/usr/bin/env python3
"""scout_pubmed.py — PubMed scout for the discover tool.

Searches PubMed via Bio.Entrez for recent papers matching config keywords.
Outputs a JSON array of papers to stdout.

Usage:
    python3 scout_pubmed.py           # normal run
    python3 scout_pubmed.py --test    # return 2 dummy papers, no network
"""

import json
import sys
import datetime
import time

from config import LITKIT_CONFIG, ENTREZ_EMAIL
from scout_utils import load_config, all_keywords, keyword_hits, paper_schema

# ── Dependency imports ──────────────────────────────────────────────────────

try:
    from Bio import Entrez
    Entrez.email = ENTREZ_EMAIL
except ImportError:
    Entrez = None
    print("[scout_pubmed] WARNING: biopython not installed. Run: pip install biopython", file=sys.stderr)

# ── Test mode ────────────────────────────────────────────────────────────────


def dummy_papers() -> list[dict]:
    today = datetime.date.today().isoformat()
    return [
        paper_schema(
            title="[TEST] Grid cell remapping during virtual reality navigation",
            authors=["Test Author A", "Test Author B"],
            date=today,
            url="https://pubmed.ncbi.nlm.nih.gov/00000001",
            doi="10.0000/test.pubmed.1",
            abstract_snippet="This is a test abstract about grid cells and spatial navigation.",
            citation_count=None,
            keyword_hits_list=["grid cells", "spatial navigation", "virtual reality navigation"],
            source="pubmed",
        ),
        paper_schema(
            title="[TEST] Sharp-wave ripples and memory consolidation in CA1",
            authors=["Test Author C"],
            date=today,
            url="https://pubmed.ncbi.nlm.nih.gov/00000002",
            doi="10.0000/test.pubmed.2",
            abstract_snippet="A test abstract about sharp-wave ripples and CA1 memory consolidation.",
            citation_count=None,
            keyword_hits_list=["sharp-wave ripples", "CA1", "memory consolidation"],
            source="pubmed",
        ),
    ]


# ── PubMed query ─────────────────────────────────────────────────────────────


def query_pubmed(keywords: list[str], since_date: str, max_results: int) -> list[dict]:
    if Entrez is None:
        print("[scout_pubmed] ERROR: biopython not available.", file=sys.stderr)
        return []

    kw_clause = " OR ".join(f'"{kw}"[Title/Abstract]' for kw in keywords)
    date_clause = f'("{since_date}"[PDAT] : "3000"[PDAT])'
    query = f"({kw_clause}) AND {date_clause}"

    print(f"[scout_pubmed] Searching PubMed: {query[:100]}…", file=sys.stderr)

    try:
        handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
        id_list = Entrez.read(handle)["IdList"]
        handle.close()
    except Exception as exc:
        print(f"[scout_pubmed] ERROR esearch: {exc}", file=sys.stderr)
        return []

    if not id_list:
        print("[scout_pubmed] No results.", file=sys.stderr)
        return []

    print(f"[scout_pubmed] Fetching {len(id_list)} records…", file=sys.stderr)

    try:
        time.sleep(0.4)
        handle = Entrez.efetch(db="pubmed", id=",".join(id_list), rettype="xml")
        records = Entrez.read(handle)
        handle.close()
    except Exception as exc:
        print(f"[scout_pubmed] ERROR efetch: {exc}", file=sys.stderr)
        return []

    results: list[dict] = []
    seen_pmids: set[str] = set()

    for rec in records.get("PubmedArticle", []):
        try:
            art = rec["MedlineCitation"]["Article"]
            title = str(art.get("ArticleTitle", "")).strip()

            abstract_node = art.get("Abstract", {}).get("AbstractText", [""])
            if isinstance(abstract_node, list):
                abstract = " ".join(str(a) for a in abstract_node)
            else:
                abstract = str(abstract_node)

            doi = None
            for id_obj in rec.get("PubmedData", {}).get("ArticleIdList", []):
                if str(id_obj.attributes.get("IdType", "")) == "doi":
                    doi = str(id_obj)
                    break

            pmid = str(rec["MedlineCitation"]["PMID"])
            if pmid in seen_pmids:
                continue
            seen_pmids.add(pmid)

            # Extract date
            date_str = ""
            try:
                pub_date = art.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
                year = str(pub_date.get("Year", ""))
                month = str(pub_date.get("Month", "01")).zfill(2)
                day = str(pub_date.get("Day", "01")).zfill(2)
                if year:
                    try:
                        int(month)
                    except ValueError:
                        month = str(datetime.datetime.strptime(month, "%b").month).zfill(2)
                    date_str = f"{year}-{month}-{day}"
            except Exception:
                date_str = datetime.date.today().isoformat()

            # Authors
            authors: list[str] = []
            for author in art.get("AuthorList", []):
                last = str(author.get("LastName", ""))
                fore = str(author.get("ForeName", ""))
                if last:
                    authors.append(f"{last} {fore}".strip())

            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"
            hits = keyword_hits(title, abstract, keywords)

            results.append(
                paper_schema(
                    title=title,
                    authors=authors,
                    date=date_str,
                    url=url,
                    doi=doi,
                    abstract_snippet=abstract[:300],
                    citation_count=None,
                    keyword_hits_list=hits,
                    source="pubmed",
                )
            )
        except Exception as exc:
            print(f"[scout_pubmed] WARN skipping record: {exc}", file=sys.stderr)

    print(f"[scout_pubmed] Done — {len(results)} papers.", file=sys.stderr)
    return results


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    if "--test" in sys.argv:
        print(json.dumps(dummy_papers(), indent=2))
        return

    cfg = load_config(LITKIT_CONFIG)
    lookback = cfg.get("lookback_days", 7)
    since_date = (datetime.date.today() - datetime.timedelta(days=lookback)).isoformat()
    keywords = all_keywords(cfg)
    max_results = cfg.get("pubmed_max_results", 50)

    papers = query_pubmed(keywords, since_date, max_results)
    print(json.dumps(papers, indent=2))


if __name__ == "__main__":
    main()
