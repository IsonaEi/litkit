# Annotation prompt — a task you hand to an LLM agent

This stage is runner-agnostic: it is a **template + a task prompt**. You can use
it by hand, or hand the prompt below to whatever LLM agent you run (a coding
agent, a chat assistant with file access, your own script — anything that can
read a file and write a markdown file). There is no required API or vendor.

The agent's job is to read one paper (PDF or converted markdown) and fill in the
[note template](../templates/note-template.md) — every section except
`## User Notes`, which is always left empty for the human.

---

## Task prompt template

Fill in `{PAPER_PATH}`, `{TEMPLATE_PATH}`, `{CATEGORIES_PATH}`, and
`{OUTPUT_PATH}` before handing this to your agent. (`{OUTPUT_PATH}` convention:
`{output_dir}/{FirstAuthorLastName}{Year}.md`, e.g.
`notes/output/Zador2023.md`.)

```
You are an academic reading-note agent.

Task: read the paper at {PAPER_PATH} and write a structured reading note
following the template at {TEMPLATE_PATH}.

1. Read {TEMPLATE_PATH} and follow its format exactly — all seven sections must
   be present: Known Premises / Gap & Problem / Methods / Results & Interpretation
   / Core Contribution / Limitations & Critique / Connections.
2. Read the paper at {PAPER_PATH}.
   - If it is a full PDF / markdown → fill in every section.
   - If only an abstract is available → set Status: ❌ No PDF, fill only
     Metadata + TL;DR, and write `<!-- No source text, to be completed -->` in
     every other section.
3. Pick the closest Category code from {CATEGORIES_PATH}.
4. Write the completed note to {OUTPUT_PATH}.

Filling rules:
- Every section must include a verbatim key quote from the source — do not
  change a single word — labelled with its §Section name.
- Write your analysis prose in your working language; keep quoted passages
  verbatim in the source language.
- The ## User Notes section: the agent must not fill, modify, or suggest content
  for it. It is the human reader's own space.
- Separate "what the data say" from "what the authors infer from the data".
- Be critical in Limitations & Critique — include limitations the authors did
  not state.

When done, output:
STATUS: success / failure
OUTPUT: {OUTPUT_PATH}
```

---

## Filling in the Connections section (optional, uses the search stage)

The Connections section places the paper in the wider field. If you have already
indexed a corpus with the litkit [search](../../search/) stage, the agent can
populate Connections semantically; if not, **skip this step** and fill
Connections by hand (or leave it for later).

Have the agent run a semantic search over your indexed corpus before writing
Connections:

```
litkit-search \
  "a natural-language description of this paper's core topic or method" \
  --top-k 8 --format text
```

Then:

- Read the top results; use each result's `source` (the filename in your corpus)
  to identify the related paper.
- Sort them into the Connections sub-fields: Builds on / Responds to-rebuts /
  Extended by / Compare (same topic).
- A single paper may appear as several chunks → de-duplicate by `source`.
- If results are weak or few, the index has little relevant material; leave a
  short description or "to be completed".
- If `LIT_QUERY_CORPUS` is not set (no corpus indexed yet), skip this step and
  fill Connections manually.

> Note: the RRF `score` from the search stage is a relative rank-combination
> score, not an absolute similarity — judge relevance by reading the top few
> results rather than applying a fixed score threshold.

---

## Failure handling

If the agent cannot produce a valid note, a simple escalation works well:

1. **First failure** → retry with a more specific prompt (state explicitly what
   was wrong and what is required).
2. **Second failure** → use a stronger model, if your runner supports switching.
3. **Third failure** → abort this paper, mark `STATUS: failure`, and move on to
   the rest of the batch rather than blocking it.

---

## Batch notes

- For a batch, process a few papers at a time. If your runner supports parallel
  agents, a small concurrency cap (e.g. 3) avoids rate limits.
- If a paper exists only as a DOI with no local file, fetch and convert it first
  with the [manage](../../manage/) stage, then point the agent at the resulting
  markdown.
- Output-path convention: `{output_dir}/{FirstAuthorLastName}{Year}.md`.

---

## Quality check (optional second pass)

After a batch, a separate agent (or a quick manual pass) can verify each note
against the template:

```
You are a note quality-check agent.

For each note in {NOTE_PATHS}, verify:
□ Has a TL;DR
□ Has a "Known Premises" section, including a verbatim source quote
□ Has a "Gap & Problem" section
□ Has a "Methods" section
□ Has a "Results & Interpretation" section
□ Has a "Core Contribution" section
□ Has a "Limitations & Critique" section
□ The "User Notes" section was NOT filled in by an agent (it must be empty)
□ The Status field is correct (a PDF exists but is marked ❌ → error)

Output a PASS / FAIL list with the reason for each FAIL.
```

Running the quality check as a *separate* pass from the writing step is
deliberate — QC should not grade its own work.
