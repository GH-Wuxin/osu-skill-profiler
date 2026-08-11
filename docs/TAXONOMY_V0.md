# Provisional Taxonomy v0

**Status: PROVISIONAL.** This taxonomy is a candidate set of skill axes, not a
final truth and not a ground-truth definition. Every axis is a hypothesis to
be tested with weak supervision, human annotation, and model evaluation.

Machine-readable source: `src/osu_skill_profiler/taxonomy/v0.json`.

## Versioning

`model_version` and `taxonomy_version` are **independent** fields in every
output. Changing the taxonomy never implies a model change, and a new model
does not require a taxonomy bump. This separation is explicit in the schema
and in `docs/MODEL_INTERFACE.md`.

## Design rules

1. A skill is an **atom**: a single, defensible human difficulty concept.
2. **`tech` is not an atomic skill.** It appears only as a convenience label
   (`PROVISIONAL_CONVENIENCE_ONLY`) that may later be derived from multiple
   atomic skills. It must never be used as a base label or a training target.
3. Each skill records:
   - `id`
   - `provisional_definition`
   - what it is **not**
   - `candidate_signals` (observable measurements that might correlate)
   - `known_ambiguity` (why it cannot be trusted without data)

## Candidate axes

### Aim

| id | provisional definition | not | candidate signals | known ambiguity |
| --- | --- | --- | --- | --- |
| `jump_aim` | place cursor accurately and quickly onto distant, isolated targets | raw distance alone; slow large-spacing maps | large normalized distances, short delta times on large distances, high movement velocity | large spacing can also be reading-driven; overlaps precision/reading |
| `flow_aim` | move cursor smoothly through connected, curved patterns | slider play; discrete jumps | small turn angles, continuous low-velocity movement, low direction-change ratio | correlates with slider complexity in naive features |
| `precision` | hit small targets and short tightly spaced movements accurately | the OD accuracy stat (OD is context) | short distances, high local density, high CS, sharp angles | shares raw spacing signals with speed |
| `awkward_aim` | handle unusual/uncomfortable cursor paths | a feature derivable from geometry alone | irregular angles, unexpected direction changes, non-uniform spacing | least objective aim axis; needs annotation |

### Tapping

| id | provisional definition | not | candidate signals | known ambiguity |
| --- | --- | --- | --- | --- |
| `burst` | tap short clusters at high rate | sustained streams; finger alternation | runs of gaps <= 250ms, burst lengths/density | burst/stream boundary is a label decision |
| `stream` | tap long continuous equally spaced runs | finger independence; stamina alone | long dense sections, low interval diversity, sustained rate | confounded with stamina |
| `speed` | tap at high BPM accurately | map BPM itself (context) | high local BPM, short deltas, high object rate | confounded with stamina in short maps |
| `stamina` | sustain high tapping rate over time | a single-map local property | long dense sections, duration-weighted density, late vs early density | short dense maps are not stamina |
| `finger_control` | execute uneven/alternating/non-standard patterns | raw speed; one rhythm statistic | high interval diversity, irregular rhythms, mixed intervals | may be reading rather than tapping |

### Reading / Rhythm

| id | provisional definition | not | candidate signals | known ambiguity |
| --- | --- | --- | --- | --- |
| `reading` | perceive/react to patterns under time pressure | a geometry-computable feature | high AR, short reaction windows, irregular placement | perceptual; needs player data |
| `rhythm_complexity` | rhythmic irregularity and interval diversity | a claim about any player's difficulty | rhythm entropy, interval diversity, interval ratios, off-grid deltas | pattern complexity vs player difficulty |

### Slider

| id | provisional definition | not | candidate signals | known ambiguity |
| --- | --- | --- | --- | --- |
| `slider_complexity` | complexity from slider geometry/repeats/length/velocity | aim; player-side slider accuracy | slider ratio, repeats, length, velocity, slider-to-circle transitions | overlaps rhythm complexity |

### Convenience labels

| id | status | definition |
| --- | --- | --- |
| `tech` | `PROVISIONAL_CONVENIENCE_ONLY` | a future derived label from `awkward_aim`, `finger_control`, `rhythm_complexity`, `flow_aim`; not an atomic skill and never a base label |

## What must happen before any axis becomes final

- Collect weak-label distribution and check for degenerate/confounded axes.
- Collect human absolute/ordinal and pairwise judgments (`docs/ANNOTATION_SCHEMA.md`).
- Evaluate model agreement with those judgments per axis.
- Only then promote axes out of `PROVISIONAL`.
