"""litkit.discover.sources — one module per academic source.

Each source module exposes:

    query(keywords, since_date, max_results) -> list[dict]   # network call
    dummy_papers() -> list[dict]                             # offline test data

and shares the normalized paper schema in :mod:`litkit.discover.sources.common`.
Heavy dependencies (biopython, requests, feedparser) are imported lazily inside
``query`` so importing this package never requires the ``discover`` extra.
"""
