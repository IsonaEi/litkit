# Example category taxonomy — customize for your own research domain

This is an **illustrative** category set (drawn from a computational /
behavioral neuroscience reading list). Treat it as a worked example: replace the
codes and descriptions with categories that fit your own field before using it.
The note template's `**Category**` field expects one (or more) of these codes.

---

## Categories

- **COMP** — Computational neuroscience, AI/ML for behavior, neural data modeling, pose estimation, behavioral quantification
- **COMPD** — Computational decision-making: reinforcement learning, reward, value-based choice, goal-directed vs. habitual
- **PHIL_AGENCY** — Philosophy of agency, autonomy, free will, action theory, enactivism, embodied cognition
- **PHIL_MIND** — Philosophy of mind, consciousness, intentionality, mental causation
- **SPON** — Spontaneous behavior, variability, intrinsic dynamics, internally-generated action
- **FLEX** — Behavioral flexibility: goal-directed vs. habitual control, habit formation, reversal learning
- **PLAN** — Action planning, spatial decision-making, hippocampal sequences, mental simulation
- **SPAT** — Spatial navigation, place cells, grid cells, cognitive maps
- **ACTN** — Action generation: motor cortex, basal ganglia circuits, movement initiation
- **METH** — Methods: tools, pipelines, datasets, benchmarks, pose estimation, decoding methods
- **CLIN** — Clinical / translational: OCD, addiction, Parkinson's, habit-related disorders

---

## Usage

A single category:

```
**Category**: COMPD
```

Multiple categories are allowed (space-separated):

```
**Category**: COMP METH
```

---

## Optional: priority tiers

Some readers like to tag how central each category is to their current focus.
This is purely optional — an example of one way to organize a reading list:

- ⭐⭐⭐ Core: COMPD, PHIL_AGENCY, SPON
- ⭐⭐ High: FLEX, COMP, PLAN
- ⭐ Supporting: METH, SPAT, ACTN, PHIL_MIND, CLIN
