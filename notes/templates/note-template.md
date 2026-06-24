# Reading-Note Template

> Design principles: prose analysis in your working language, a verbatim
> source-language quote anchoring every section, a critical perspective, and a
> User Notes area that is yours alone.

---

## How to use

**Before filling in:**

- Full PDF available → fill in every section normally.
- Only an abstract / no PDF → mark `Status: ❌ No PDF`, fill in **only Metadata
  and the TL;DR (from the abstract)**, leave the other sections empty, and add a
  `<!-- No source text, to be completed -->` marker.
- The paper type changes how you fill the **Methods** section (see the inline
  comment in the template).

**Language convention:**

- Write your *analysis prose* in whatever language you actually work in.
- Keep every *quoted passage* **verbatim in its source language**, and label it
  with the section it came from. The quote is the anchor; your prose is the
  interpretation. Never paraphrase inside the quotation marks.

**About User Notes:**

- The `## User Notes` section is reserved for the reader's own reflections. An
  automated agent **must leave this section empty** — it must not fill, modify,
  or suggest content for it.
- The agent fills every other section; User Notes is the human's own space for
  thoughts, questions, and extensions.

---

## The template

```markdown
# [FirstAuthorLastName] et al. (YYYY) — [Full paper title]

**DOI**: xxx
**Authors**: First author full name (affiliation); corresponding author full name★ (affiliation)
**Year**: YYYY | **Journal/Venue**: xxx | **Type**: Research / Review / Perspective / Theory / Methods
**Category**: COMP / PHIL_AGENCY / METH / BEH / NEURO / ...
**Status**: ✅ Read / 📖 Reading / ⬜ To read / ❌ No PDF

---

> **TL;DR:** [One sentence: what this paper did, what it found, and why it
> matters. Write freely — no fixed format required.]

---

## Known Premises

> "[Verbatim key quote from the source — do not change a word]" (§Section name)

[Your interpretation: what knowledge base does the author start from? What do
they take for granted as established? Are those premises sound?]

---

## Gap & Problem

> "[Verbatim key quote from the source — do not change a word]" (§Section name)

[Your interpretation: what problem is this paper trying to solve? Why does it
matter? Where do the authors think existing methods or understanding fall
short?]

---

## Methods

> "[Verbatim key quote from the source — do not change a word]" (§Section name)

<!-- Choose how to fill this in based on the paper type:
- Research paper: experimental design, subjects/samples, data sources, analysis
- Review paper: literature scope, how the argument is organized (chronological?
  by sub-question?), how the points build on one another
- Theory/Perspective: how the argument escalates, which cases / thought
  experiments are cited in support
-->

[Your interpretation: by what means does this paper answer its question?]

---

## Results & Interpretation

> "[Verbatim key quote from the source — do not change a word]" (§Section name)

[Your interpretation: what are the main findings? How do the authors interpret
them? Keep "what the data say" and "what the authors infer from the data"
clearly separate.]

---

## Core Contribution

[What does this paper claim to contribute to the field? (Not "the result is X",
but "this forces / allows the field to rethink Y".) e.g. proposes a new
framework / challenges an assumption / provides a new dataset / establishes a new
benchmark.]

---

## Limitations & Critique

> "[Quote where the authors state a limitation, if any]" (§Discussion)

[Critical assessment:
- What limitations do the authors acknowledge?
- What obvious limitations go unstated?
- Which assumptions are worth questioning?
- Are there methodological problems?
For a Perspective/Comment paper, assess the logical gaps in the argument itself.]

---

## Connections

<!-- This section can be left empty at first and filled in later — early in
     reading you may not yet know where the paper sits in the wider field. -->

- **Builds on**: [which papers it stands on]
- **Responds to / rebuts**: [papers it opposes or revises]
- **Extended by**: [later papers that cite and develop this one]
- **Compare (same topic)**: [papers on a similar question with a different approach]

---

## User Notes

<!-- This section is reserved for the reader's own reflections.
     An automated agent must leave this section empty — do not fill, modify, or
     suggest content. The reader may add: personal thoughts, research
     implications, questions, and directions to follow up. -->
```

---

## Worked example: Zador et al. (2023) (Review)

```markdown
# Zador et al. (2023) — Catalyzing next-generation Artificial Intelligence through NeuroAI

**DOI**: 10.1038/s41467-023-37180-x
**Authors**: Anthony M. Zador (Cold Spring Harbor Laboratory); multiple corresponding authors★ (various institutions)
**Year**: 2023 | **Journal/Venue**: Nature Communications | **Type**: Review
**Category**: COMP
**Status**: ✅ Read

---

> **TL;DR:** A collective manifesto for the NeuroAI field — to break through the
> ceiling of scaling, AI needs to learn sensorimotor intelligence from biological
> neuroscience; it proposes the "embodied Turing test" as an operationalizable
> grand challenge.

---

## Known Premises

> "Historically, many key AI advances, such as convolutional ANNs and reinforcement learning, were inspired by neuroscience. Neuroscience continues to provide guidance—e.g., attention-based neural networks were loosely inspired by attention mechanisms in the brain—but this is often based on findings that are decades old." (§Introduction)

Neuroscience has historically driven AI (CNNs ← visual cortex; RL ← animal
reinforcement learning), but the cross-pollination has thinned in recent years,
and neuroscience's influence is increasingly confined to decades-old findings.
The authors treat this as a "missed opportunity" rather than an inevitable trend.

---

## Gap & Problem

> "Although AI systems can easily defeat any human opponent in games such as chess and Go, they are not robust and often struggle when faced with novel situations... Today's AI systems cannot compete with the sensorimotor capabilities of a four-year old child or even simple animals." (§Introduction)

Today's AI surpasses humans at logical games but cannot match a four-year-old at
sensorimotor tasks. The root cause: scaling language models alone cannot acquire
sensorimotor intelligence — which is precisely the core capability all animals
acquired through evolution.

---

## Methods

> "We therefore propose an expanded 'embodied Turing test,' one that includes advanced sensorimotor abilities... comprising challenges that include a wide range of organisms used in neuroscience research, including worms, flies, fish, rodents and primates." (§NeuroAI grand challenge)

A review paper; the argument is organized as:
(1) Define the problem (why AI lacks sensorimotor intelligence).
(2) Propose the embodied Turing test as a benchmark, tiered to evolutionary complexity.
(3) Lay out a gradual path (simulate simpler animals → higher primates).
(4) Recommend infrastructure (cross-disciplinary training, data standards, compute).

---

## Results & Interpretation

> "If AI aims to achieve animal-level common-sense sensorimotor intelligence, researchers would be well-advised to learn from animals and the solutions they evolved to behave in an unpredictable world." (§Conclusions)

The claim (not an experimental result): animals are the best engineering
blueprint; 500 million years of evolution already solved AI's hardest problems.
The authors interpret this as requiring *institutional* investment, not merely
individual researchers' interest.

---

## Core Contribution

Proposes the "embodied Turing test" (ETT) as an operationalizable grand challenge
for NeuroAI; calls for rebuilding the deep cross-pollination between neuroscience
and AI, with sensorimotor intelligence as the central goal, and offers a concrete
tiered benchmark roadmap.

---

## Limitations & Critique

> [The paper states no explicit limitation; it is closer in character to a manifesto / call to action.]

- It is an opinion piece without empirical data; ETT's concrete standardization
  (how to quantify "behavioral indistinguishability") remains vague.
- The "learn from animals" path is too high-level and lacks actionable short-term milestones.
- Its assessment of LLMs is dated (a pre-2023 perspective) and does not account
  for recent progress in embodied agents.
- A multi-author manifesto may paper over internal disagreement; the choice of
  arguments is somewhat selective.

---

## Connections

- **Builds on**: Hassabis et al. (2017) neuroscience-inspired AI; Moravec (1988) paradox
- **Compare (same topic)**: Richards et al. (2019) "A deep learning framework for neuroscience"
- **Extended by**: subsequent NeuroAI benchmark papers (2023–2024)

---

## User Notes

<!-- The reader's own space — the agent does not fill this section. -->
```

---

## Worked example: no-PDF case

```markdown
# Smith et al. (2021) — [Full paper title]

**DOI**: xxx
**Authors**: [If the abstract names them, fill in the first author; leave the corresponding author★ blank if unknown]
**Year**: 2021 | **Journal/Venue**: xxx | **Type**: Research
**Category**: NEURO
**Status**: ❌ No PDF

---

> **TL;DR:** [From the abstract — what this paper did.]

---

## Known Premises

<!-- No source text, to be completed -->

## Gap & Problem

<!-- No source text, to be completed -->

## Methods

<!-- No source text, to be completed -->

## Results & Interpretation

<!-- No source text, to be completed -->

## Core Contribution

<!-- No source text, to be completed -->

## Limitations & Critique

<!-- No source text, to be completed -->

## Connections

<!-- No source text, to be completed -->

## User Notes

<!-- The reader's own space — the agent does not fill this section. -->
```
