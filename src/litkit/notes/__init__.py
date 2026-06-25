"""litkit.notes — the structured reading-note template + filling instructions.

This stage ships only markdown (no heavy dependency). The loader reads the
bundled template / categories / annotation prompt via ``importlib.resources`` so
they are available no matter where the package is installed.
"""

from litkit.notes.loader import (
    build_note_prompt,
    load_annotation_prompt,
    load_categories,
    load_template,
)

__all__ = [
    "load_template",
    "load_categories",
    "load_annotation_prompt",
    "build_note_prompt",
]
