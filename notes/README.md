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

## How to use it

**By hand:** open [templates/note-template.md](templates/note-template.md), copy
the template block, and fill it in as you read. See the worked
`Zador et al. (2023)` example in that file for the target quality.

**With an LLM agent:** hand the task prompt in
[references/annotation-prompt.md](references/annotation-prompt.md) to any agent
that can read a file and write a markdown file. The prompt is runner-agnostic —
no specific API, model, or platform is assumed. Fill in the paper path, template
path, category list, and output path, and the agent produces a completed note
(leaving User Notes empty).

**Categories:** [references/categories-example.md](references/categories-example.md)
is an example taxonomy (computational / behavioral neuroscience). Replace it with
categories for your own domain.

## Dependencies

None. This stage ships only markdown — there is no Python package to install and
no `litkit` extra to add. The only optional integration is the
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
