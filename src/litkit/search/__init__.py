"""litkit.search — local hybrid (dense + sparse) semantic search.

Public entry points:
- :func:`litkit.search.ingest.ingest` — index a corpus into Qdrant.
- :func:`litkit.search.query.search` — hybrid RRF search over the index.

Heavy dependencies (docling, FlagEmbedding, qdrant-client) are imported lazily
inside these functions so importing this package never requires the ``search``
extra.
"""

from litkit.search.ingest import ingest
from litkit.search.query import search

__all__ = ["ingest", "search"]
