# Map Demand Atomic V0.4

> Historical contract. Superseded by `MAP_DEMAND_ATOMIC_V03` / V0.5; do not
> use these percentile scores as absolute 0–10 difficulty.

`MAP_DEMAND_ATOMIC_V02` replaces the exploratory broad six-axis output with
nine human-facing atomic demand axes. It remains heuristic and requires human
validation; it is not a player-skill model and does not claim ppy parity.

## Atomic axes

1. `jump_aim`: discrete jump movement pressure.
2. `flow_aim`: sustained forward-continuity chains, their length, and a
   lower-weight capped velocity term.
3. `aim_control`: spatial angle and movement-velocity changes.
4. `spatial_precision`: CS-normalised spatial placement pressure.
5. `raw_speed`: short-interval tapping speed.
6. `stamina`: sustained dense-section duration and density.
7. `finger_control`: temporal interval entropy, diversity, and ratio changes.
8. `timing_precision`: pressure from the effective great-hit window.
9. `reading`: preempt, visual density, and direction-change pressure.

Temporal irregularity belongs to `finger_control`; spatial angle, spacing, and
velocity irregularity belongs to `aim_control`. There is no human-facing
`rhythm` axis.

## Derived summaries

`aim_summary`, `tapping_summary`, and `overall_demand` are arithmetic means of
their emitted atomic source axes. They live under `summaries`, never under
`axes`, and are display-only: calibration, archetype classification, review,
and future training consume only the nine atomic axes.

## Version and data boundaries

- output schema: `map_demand_v0.4.0`
- review axis schema: `atomic_v0.4.0`
- archetype schema: `map_archetype_v0.2.0`
- canonical calibration: `map_demand_calibration_v02_atomic_rev2`
- canonical QA: `map_demand_qa_v02_atomic_rev2`
- human review package: `map_archetype_atomic_v02`

The old `map_archetype_v01` package and its broad six-axis responses are
frozen. They are accepted as `broad_v0.3.0` for auditability, reported as
`LEGACY_V03_INCOMPARABLE`, and never converted into atomic labels. The atomic
review UI refuses to write to legacy packages.

## Canonical QA result

The rev2 calibration contains 5,000 maps. Atomic-axis emission ranges from
4,975 to 4,991 maps. Direct recomputation of 20 source maps has maximum absolute
component delta 0. The initial Flow Aim prototype correlated 0.978 with Jump
Aim; rev2 moved Flow Aim to continuity share, chain length, and a lower-weight
capped chain-velocity term, reducing Jump/Flow Spearman correlation to 0.616.

## Commands

From the repository root:

```powershell
python tools\skill-profiler-map-demand-v01.py build-calibration
python tools\skill-profiler-map-demand-v01.py qa
python tools\skill-profiler-map-demand-v01.py archetype-qa
python tools\skill-profiler-map-demand-v01.py archetype-review-ui --show-algorithm
```

The last command serves the assisted nine-slider review at
`http://127.0.0.1:8766/`. Omit `--show-algorithm` for blind review.
