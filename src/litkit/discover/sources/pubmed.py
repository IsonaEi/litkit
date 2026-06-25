"""PubMed source — searches PubMed via Bio.Entrez for recent papers.

The biopython dependency is imported lazily inside :func:`query`; a missing
dependency raises a clear "pip install litkit[discover]" message only when this
source is actually run.
"""

from __future__ import annotations

import datetime
import logging
import time

from litkit.config import get_entrez_email
from litkit.discover.sources.common import keyword_hits, paper_schema

log = logging.getLogger(__name__)

NAME = "pubmed"


def dummy_papers() -> list[dict]:
    """Two offline dummy papers for the no-network smoke test."""
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


def query(keywords: list[str], since_date: str, max_results: int) -> list[dict]:
    """Search PubMed for recent papers matching ``keywords``."""
    try:
        from Bio import Entrez
    except ImportError as exc:  # pragma: no cover - depends on extras
        raise ImportError(
            "biopython is required for the PubMed source. "
            "Install it with: pip install 'litkit[discover]'"
        ) from exc

    Entrez.email = get_entrez_email()

    kw_clause = " OR ".join(f'"{kw}"[Title/Abstract]' for kw in keywords)
    date_clause = f'("{since_date}"[PDAT] : "3000"[PDAT])'
    pubmed_query = f"({kw_clause}) AND {date_clause}"

    log.info("Searching PubMed: %s…", pubmed_query[:100])

    try:
        handle = Entrez.esearch(db="pubmed", term=pubmed_query, retmax=max_results)
        id_list = Entrez.read(handle)["IdList"]
        handle.close()
    except Exception as exc:
        log.error("esearch failed: %s", exc)
        return []

    if not id_list:
        log.info("No results.")
        return []

    log.info("Fetching %d records…", len(id_list))

    try:
        time.sleep(0.4)
        handle = Entrez.efetch(db="pubmed", id=",".join(id_list), rettype="xml")
        records = Entrez.read(handle)
        handle.close()
    except Exception as exc:
        log.error("efetch failed: %s", exc)
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
            log.warning("skipping record: %s", exc)

    log.info("Done — %d papers.", len(results))
    return results
