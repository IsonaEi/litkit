"""litkit.manage — build and maintain a local literature library.

- :mod:`litkit.manage.shell` wraps the proven download/convert/audit/verify
  shell tools (preserving the DOI→PDF fallback chain and Sci-Hub opt-in gating).
- :mod:`litkit.manage.enrich` enriches a library ``index.json`` from Semantic
  Scholar.
"""

from litkit.manage.enrich import enrich_index, enrich_library
from litkit.manage.shell import audit_library, convert_to_markdown, download_paper, verify_pair

__all__ = [
    "download_paper",
    "convert_to_markdown",
    "audit_library",
    "verify_pair",
    "enrich_index",
    "enrich_library",
]
