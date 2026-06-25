# notes

Stage 3 of [litkit](../README.md). A structured reading-note methodology: a
markdown **template** plus a runner-agnostic **task prompt** for turning a paper
into a consistent, critical, quotable note. There is no code and no new
dependency here — it is driven by whatever LLM agent you already use (or by hand).

## What it is

Every note follows one template with seven analytical sections plus a User Notes
area reserved for the human:

1. **Known Premises** — what the authors take as established, and whether it holds.
2. **Gap & Problem** — the problem the paper addresses and why it matters.
3. **Methods** — how they answer the question (filled differently per paper type).
4. **Results & Interpretation** — findings vs. the authors' inferences from them.
5. **Core Contribution** — what the field must now rethink because of this paper.
6. **Limitations & Critique** — stated *and* unstated weaknesses; a critical read.
7. **Connections** — where the paper sits relative to others (optionally filled
   via the [search](../search/) stage).
8. **User Notes** — the reader's own space. An agent must **never** write here.

### The design idea

Two principles make the notes durable and trustworthy:

- **Quote anchors.** Every analytical section opens with a *verbatim* quote from
  the source, labelled with its section. The quote is the ground truth; your
  prose is the interpretation built on top of it. This keeps notes honest — you
  can always check a claim against the exact words.
- **Language-agnostic prose.** Write your analysis in whatever language you work
  in, but keep quoted passages verbatim in the source language. The structure,
  not the language, is what makes the notes comparable.

The template, the example taxonomy, and the annotation prompt are shipped as
package data and read at runtime via `importlib.resources` — the source markdown
lives under
[`src/litkit/notes/`](../src/litkit/notes/) (`templates/note-template.md`,
`references/categories-example.md`, `references/annotation-prompt.md`).

## How to use it

**By hand:** print the template and copy the block, filling it in as you read.
See the worked `Zador et al. (2023)` example in it for the target quality.

```bash
python3 -c "from litkit.notes import load_template; print(load_template())"
python3 -c "from litkit.notes import load_categories; print(load_categories())"
```

**With an LLM agent (via MCP):** point your MCP client at the litkit server and
use the `write_reading_note(paper_path)` prompt — it returns the full template
plus filling instructions. The template and the example taxonomy are also exposed
as the `litkit://note-template` and `litkit://categories-example` resources.

**With any agent (no MCP):** build the same prompt in Python and hand it to any
agent that can read a file and write a markdown file — runner-agnostic, no
specific API or model assumed (it leaves User Notes empty):

```bash
python3 -c "from litkit.notes import build_note_prompt; print(build_note_prompt('library/papers/x.md'))"
```

## Dependencies

None beyond the core `litkit` install — this stage ships only markdown plus a
tiny loader, with no `litkit` extra to add. The only optional integration is the
[search](../search/) stage for filling in the Connections section, which you
install separately (`pip install -e ".[search]"`).

## Chaining

`notes` sits in the middle of the litkit pipeline:

```
discover → manage → notes → search
```

- The [manage](../manage/) stage gives you a downloaded, converted paper to
  annotate.
- The notes you write become part of the corpus that [search](../search/)
  indexes — and that the [discover](../discover/) stage's optional Stage-2
  re-ranker scores new papers against. So the more you annotate, the better both
  discovery and retrieval get: the pipeline closes into a loop.
- While writing a note, the **Connections** section can call the search stage to
  find related papers already in your corpus (optional — skip it if nothing is
  indexed yet).
