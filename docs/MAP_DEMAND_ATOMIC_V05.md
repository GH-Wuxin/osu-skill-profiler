# Map Demand Atomic V0.7 mechanism overlay

`MAP_DEMAND_ATOMIC_V05` is the first structural revision driven by the BID
human-review loop. It does **not** replace or mutate the frozen V0.6 signal
calibration. V0.6 remains replayable; V0.7 consumes the same objective Local
Signal 0.3 / Feature 0.2 inputs and applies a separately identified,
deterministic mechanism overlay in star-equivalent space.

Versioned identities:

- algorithm: `MAP_DEMAND_ATOMIC_V05`
- output schema: `map_demand_v0.7.0`
- map-demand version: `0.7.0`
- axis taxonomy: `atomic_v0.6.0` (unchanged eight axes)
- base calibration: `map_demand_calibration_v04_unbounded_star_scale_20k`
- overlay calibration identity: deterministic hash of the base calibration ID
  and the frozen V0.7 mechanism specification
- distribution QA: `map_demand_qa_v07_mechanism_overlay_20k`

## Mechanisms

### Relative AR and Reading

Raw AR is not treated as an absolute difficulty label. V0.7 converts the
effective AR (after speed/difficulty Mods) to preempt time and compares it with
the preempt requirement implied by the surrounding physical demand. Thus the
same AR can be adequate on an ordinary map and become a visibility bottleneck
on an extreme map.

Reading combines:

1. the V0.6 visual-change/high-AR score;
2. a high-demand environment floor, activated only on physically difficult
   maps or unambiguously low-AR maps;
3. a bounded nonlinear relative-AR deficit;
4. an absolute long-preempt burden for very low AR;
5. an HD compound term which activates only when a visibility deficit already
   exists.

HD is therefore not a flat universal premium. Low AR and HD reinforce one
another, while HD on a readable high-AR map remains much smaller.

### Cross-axis visibility transfer

Visibility burden transfers conservatively into Flow Aim and Aim Control. The
Flow mechanism additionally requires both a difficult environment and existing
continuous-flow morphology, preventing a map with zero flow evidence from
becoming a Flow map merely because another axis is difficult.

Aim Control also receives a smoothly activated floor for very high Jump Aim
combined with Precision Aim. This fixes the obvious extreme-jump contradiction
without pretending that the current map-level change signals fully solve Aim
Control.

### Finger Control

V0.6 only represented interval entropy/diversity. V0.7 retains that pattern
evidence and adds:

- a difficulty-gated, circle-share-weighted tapping floor;
- sustained clicking from long 125/250 ms burst runs and peak object rate;
- a bounded visibility-to-finger bottleneck for low-AR execution;
- an upper-tail extension for already-strong pattern-control evidence.

Sustained and visibility bonuses are combined as competing bottlenecks rather
than blindly summed. This separates a thousands-of-notes regular map from an
ordinary short burst and avoids promoting slider-heavy speed maps wholesale.

## Validation snapshot

On the active human BID review groups available at implementation time (with
`AT_LEAST` treated as a one-sided lower bound), the affected-axis errors were:

| Axis | Groups | Mean predicted-human | MAE |
|---|---:|---:|---:|
| Reading | 12 | -0.19 | 0.75 |
| Flow Aim | 10 | +0.03 | 0.52 |
| Finger Control | 10 | -0.19 | 0.31 |
| Aim Control | 15 | -0.65 | 0.88 |

These are descriptive anchor checks, not training metrics. Duplicate and
superseded corrections are excluded by the evaluator; `AT_LEAST` values are
not treated as exact targets.

The frozen 20k NM drift audit joins all 20,000 calibration samples to Feature
0.2 with zero missing joins. Median star deltas are +0.24 Flow, +0.04 Aim
Control, +0.69 Finger Control, and +1.17 Reading; unaffected axes remain exactly
unchanged. See the generated JSON/Markdown report for full quantiles.

## Known limits

- Aim Control remains structurally incomplete for dense control patterns that
  are neither giant jumps nor adequately captured by the two V0.6 change
  aggregates. This needs section/local-pattern evidence, not another global
  offset.
- Jump Aim and Raw Speed still understate several extreme human anchors. They
  were deliberately not globally retuned in this slice.
- Stamina was left unchanged; the human examples show that duration uniformity
  and endurance semantics need a separate revision.
- Flashlight remains deferred as its own future dimension.
- The current sample is too small and assisted to justify regression fitting.

## Replay and tools

V0.7 is now a frozen replay target. V0.8 is the BID/CLI default; V0.7 and the
V0.6 baseline remain available explicitly:

```powershell
python tools\map_demand_v01\cli.py analyze --map <map.osu> --algorithm v07
python tools\map_demand_v01\cli.py analyze --map <map.osu> --algorithm v06
```

Re-run the audits with:

```powershell
$env:PYTHONPATH='tools'
python -m map_demand_v01.evaluate_v07_anchors
python -m map_demand_v01.qa_v07_corpus
```
