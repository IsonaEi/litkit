"""litkit MCP server — expose the four literature stages to AI agents.

A FastMCP server (stdio transport) that wraps the pure ``litkit`` functions as
MCP tools, a prompt, and resources. It is intentionally provider-agnostic: it
imports no LLM/Anthropic API and makes no model calls. It only exposes
capabilities — the calling agent decides when to use them.

Heavy, stage-specific dependencies (FlagEmbedding/qdrant for search,
biopython/feedparser for discover) are imported lazily inside the tool
functions, so this module imports cleanly even when those extras are absent. A
missing dependency surfaces as a clear "pip install 'litkit[...]'" error only
when the relevant tool is actually invoked.

Run it with ``litkit-mcp`` (or ``python -m litkit.mcp_server``).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("litkit")


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def discover_papers(
    keywords: list[str],
    sources: list[str] | None = None,
    max_results: int = 20,
) -> list[dict]:
    """Find recent papers across academic sources, ranked by relevance.

    Call this when the user wants to DISCOVER NEW literature from the internet —
    e.g. "find recent papers on X", "what's new on Y", "search the literature for
    Z". It queries PubMed, bioRxiv, arXiv, Semantic Scholar and journal RSS
    feeds, deduplicates, and ranks the results (BM25 + cluster + citation +
    recency). Do NOT use this to search the user's own library — use
    ``search_library`` for that.

    Args:
        keywords: Topic keywords to search for (e.g. ["place cells", "remapping"]).
        sources: Subset of sources to query — any of "pubmed", "biorxiv",
            "arxiv", "semantic" (or "semantic_scholar"), "rss". None = all five.
        max_results: Maximum number of ranked papers to return.

    Returns:
        A list of ranked paper dicts (title, authors, date, source, url, doi,
        abstract_snippet, citation_count, keyword_hits, relevance_score,
        ingestion_candidate). Papers with ``ingestion_candidate: true`` are the
        ones worth downloading via ``download_paper``.
    """
    from litkit.discover.orchestrator import discover_papers as _discover

    return _discover(keywords=keywords, sources=sources, max_results=max_results)


@mcp.tool()
def download_paper(
    doi: str,
    dest_dir: str | None = None,
    enable_scihub: bool = False,
) -> dict:
    """Download a paper's PDF by DOI into a local directory.

    Call this when the user wants to FETCH the actual PDF of a known paper (you
    have its DOI). It tries legal sources in order — direct URL, publisher
    patterns (Nature, eLife, bioRxiv, PNAS, Frontiers, Springer/BMC), EuropePMC,
    then arXiv. The Sci-Hub fallback is OFF by default and is only attempted when
    the user has explicitly opted in via ``enable_scihub=True`` (or the
    LITKIT_ENABLE_SCIHUB=1 environment variable); never enable it on your own
    initiative.

    Args:
        doi: The paper DOI (e.g. "10.7554/eLife.12345") or a direct URL.
        dest_dir: Directory to save the PDF into (default: current directory).
        enable_scihub: Opt in to the Sci-Hub fallback. Leave False unless the
            user has explicitly asked for it; the caller bears legal/ethical
            responsibility.

    Returns:
        {status: "success"|"failure", doi, path, source, stdout, stderr}.
        On success, ``path`` is the saved PDF and ``source`` names the provider.
    """
    from litkit.manage.shell import download_paper as _download

    return _download(doi=doi, dest_dir=dest_dir, enable_scihub=enable_scihub)


@mcp.tool()
def convert_to_markdown(pdf_path: str) -> dict:
    """Convert a local PDF into a markdown text file.

    Call this after ``download_paper`` (or for any local PDF) when you need the
    paper's text — e.g. before writing a reading note or before ingesting it for
    search. Uses ``pdftotext`` first, then falls back to ``markitdown`` for
    higher fidelity.

    Args:
        pdf_path: Path to the PDF file to convert.

    Returns:
        {status: "success"|"failure", pdf_path, path, tool, stdout, stderr}.
        On success, ``path`` is the produced markdown file and ``tool`` is the
        converter that succeeded.
    """
    from litkit.manage.shell import convert_to_markdown as _convert

    return _convert(pdf_path=pdf_path)


@mcp.tool()
def enrich_metadata(library_dir: str) -> dict:
    """Fill in missing metadata for a local library from Semantic Scholar.

    Call this when the user wants to ENRICH their library catalogue — i.e. fill
    missing abstract/year/authors and refresh citation counts in a library's
    ``index.json``. It looks up each paper by DOI and updates the file in place.
    Idempotent: entries that already have a citation count are skipped.

    Args:
        library_dir: Path to the library directory (the index lives at
            ``<library_dir>/index.json``).

    Returns:
        {status: "ok"|"error", total, enriched, skipped, index_path,
        output_path}. On error the ``message`` field explains why.
    """
    from litkit.manage.enrich import enrich_library

    try:
        summary = enrich_library(library_dir=library_dir)
    except (FileNotFoundError, ValueError) as exc:
        return {"status": "error", "message": str(exc)}
    summary["status"] = "ok"
    return summary


@mcp.tool()
def ingest_library(corpus_dir: str | None = None, force: bool = False) -> dict:
    """Index a local corpus of PDFs/markdown so it becomes searchable.

    Call this BEFORE ``search_library`` whenever new papers have been added (or
    the user asks to "index"/"reindex" their library). It parses each file with
    Docling, chunks it, embeds it with BGE-M3, and stores the vectors in an
    on-disk Qdrant collection. It is idempotent — unchanged files are skipped
    via an MD5 manifest unless ``force=True``.

    Args:
        corpus_dir: Directory of PDF/MD papers to index. None uses the
            LIT_QUERY_CORPUS (+ LIT_QUERY_CORPUS_EXTRA) environment variables.
        force: Re-ingest every file, ignoring the manifest.

    Returns:
        A summary dict — {status, corpus_paths, found, to_process, processed,
        chunks, files}. ``status`` is one of "ok", "no_files", "up_to_date",
        "dry_run", "error".
    """
    from litkit.search.ingest import SearchDependencyError, ingest

    try:
        return ingest(corpus_dir=corpus_dir, force=force)
    except SearchDependencyError as exc:
        return {"status": "error", "message": str(exc)}


@mcp.tool()
def search_library(query: str, top_k: int = 8, section: str | None = None) -> list[dict]:
    """Search the user's OWN ingested library semantically.

    Call this when the user asks about papers they already have — e.g. "which of
    my papers discuss X", "find papers in my library about Y", "what does my
    corpus say about Z". This searches the local Qdrant index built by
    ``ingest_library``; it does NOT touch the internet. For discovering brand-new
    papers online, use ``discover_papers`` instead.

    Args:
        query: Natural-language query text.
        top_k: Number of results to return.
        section: Optional section filter — one of Abstract, Introduction,
            Methods, Results, Discussion, References, Other.

    Returns:
        A list of hit dicts (rank, score, title, source, section_type, headings,
        page, year, text). ``source`` is the filename in the corpus; cite by it.
        On error (missing extras or empty/absent index) returns a single dict
        ``[{status: "error", message: ...}]``.
    """
    from litkit.search.ingest import SearchDependencyError
    from litkit.search.query import SearchIndexError, search

    try:
        return search(query=query, top_k=top_k, section=section)
    except (SearchDependencyError, SearchIndexError) as exc:
        return [{"status": "error", "message": str(exc)}]


# ── Prompt ────────────────────────────────────────────────────────────────────

@mcp.prompt()
def write_reading_note(paper_path: str) -> str:
    """Return a ready-to-use prompt for writing a structured reading note.

    Use this prompt when the user wants to ANNOTATE a paper into a consistent,
    critical, quotable note. It returns the full 7-section reading-note template
    (Known Premises / Gap & Problem / Methods / Results & Interpretation / Core
    Contribution / Limitations & Critique / Connections) plus filling
    instructions and an example category taxonomy. The agent fills every section
    except ``## User Notes``, which stays empty for the human.

    Args:
        paper_path: Path to the paper (PDF or converted markdown) to annotate.
    """
    from litkit.notes.loader import build_note_prompt

    return build_note_prompt(paper_path)


# ── Resources ─────────────────────────────────────────────────────────────────

@mcp.resource("litkit://note-template")
def note_template_resource() -> str:
    """The reading-note markdown template (with worked examples)."""
    from litkit.notes.loader import load_template

    return load_template()


@mcp.resource("litkit://categories-example")
def categories_example_resource() -> str:
    """The example category taxonomy markdown (customize for your own domain)."""
    from litkit.notes.loader import load_categories

    return load_categories()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Run the litkit MCP server over stdio (the default transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
