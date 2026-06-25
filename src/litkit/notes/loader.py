"""Load the bundled reading-note markdown assets and build a filling prompt.

The template, categories example, and annotation prompt are shipped as package
data under ``litkit/notes/templates`` and ``litkit/notes/references``. They are
read via ``importlib.resources`` so they resolve correctly from an installed
wheel as well as an editable checkout.
"""

from __future__ import annotations

from importlib.resources import files


def load_template() -> str:
    """Return the full reading-note template markdown (with worked examples)."""
    return (files("litkit.notes.templates") / "note-template.md").read_text(encoding="utf-8")


def load_categories() -> str:
    """Return the example category taxonomy markdown."""
    return (files("litkit.notes.references") / "categories-example.md").read_text(encoding="utf-8")


def load_annotation_prompt() -> str:
    """Return the runner-agnostic annotation task prompt markdown."""
    return (files("litkit.notes.references") / "annotation-prompt.md").read_text(encoding="utf-8")


def build_note_prompt(paper_path: str) -> str:
    """Build a self-contained prompt instructing an agent to write a reading note.

    Combines concrete filling instructions for ``paper_path`` with the full
    7-section template and the example category taxonomy, so the returned string
    is everything an agent needs to produce one structured note. The agent must
    leave the ``## User Notes`` section empty.
    """
    template = load_template()
    categories = load_categories()

    return f"""You are an academic reading-note agent.

Task: read the paper at `{paper_path}` and write a structured reading note that
follows the template below exactly. All seven analytical sections must be
present: Known Premises / Gap & Problem / Methods / Results & Interpretation /
Core Contribution / Limitations & Critique / Connections.

Filling rules:
- If the paper is a full PDF / markdown, fill in every section. If only an
  abstract is available, set `Status: ❌ No PDF`, fill only Metadata + TL;DR,
  and write `<!-- No source text, to be completed -->` in every other section.
- Every analytical section must open with a verbatim key quote from the source —
  do not change a single word — labelled with its §Section name.
- Write your analysis prose in your working language; keep quoted passages
  verbatim in the source language.
- Separate "what the data say" from "what the authors infer from the data".
- Be critical in Limitations & Critique — include limitations the authors did
  not state.
- The `## User Notes` section is the human reader's own space: do NOT fill,
  modify, or suggest content for it. Leave it empty.
- Pick the closest Category code from the taxonomy below.

When done, output:
STATUS: success / failure

--- TEMPLATE ---
{template}

--- CATEGORY TAXONOMY (pick the closest code; customize for your own domain) ---
{categories}
"""
