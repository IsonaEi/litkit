"""litkit — a literature toolkit.

Four composable stages — discover, manage, notes, search — exposed three ways:

- as an importable Python package (the pure functions in each submodule),
- as a human-facing CLI (``litkit.cli`` / the ``litkit-*`` console scripts),
- as an MCP server for AI agents (``litkit.mcp_server`` / ``litkit-mcp``).

Heavy, stage-specific dependencies (FlagEmbedding/qdrant for search,
biopython/feedparser for discover) are imported lazily inside the functions that
need them, so importing :mod:`litkit` itself never requires the extras.
"""

__version__ = "0.2.0"

__all__ = ["__version__"]
