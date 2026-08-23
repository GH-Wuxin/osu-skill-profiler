# Map Demand Atomic V0.5 (historical)

> Superseded by `MAP_DEMAND_ATOMIC_V04` / V0.6. V0.5 remains readable for
> audit, but its 10-star hard cap must not be used for new outputs.

`MAP_DEMAND_ATOMIC_V03` separates two quantities that V0.4 incorrectly
collapsed: a feature's corpus percentile and a human-facing demand scale.
It remains an experimental map-demand model, not a player-skill model and not
an implementation of osu!'s official difficulty calculator.

## Eight human skill axes

1. `jump_aim`: discrete jump movement pressure.
2. `flow_aim`: sustained continuous aim, with continuity and chain length used
   as morphology gates on actual chain velocity pressure.
3. `aim_control`: spatial angle and movement-velocity changes.
4. `spatial_precision`: CS-normalised spatial placement pressure.
5. `raw_speed`: short-interval tapping speed.
6. `stamina`: sustained dense-section duration and density.
7. `finger_control`: temporal interval entropy, diversity, and ratio changes.
8. `reading`: high-AR pressure plus visual change, with density allowed only as
   an amplifier of that visual complexity.

`timing_precision` is removed from the human skill taxonomy. The objective
Great hit window remains under `context.accuracy_window`; it never enters
archetype classification, human labels, or derived summaries.

## Score semantics

Each axis contains both:

- `percentile_rank`: the diagnostic rank of its proxy signals in the versioned
  feature-calibration population;
- `demand_score_0_10`: that rank mapped through the empirical distribution of
  126,148 local osu!standard NoMod star ratings and capped at 10.

`score` is `demand_score_0_10 / 10` for contract compatibility. A 97th
percentile proxy therefore maps to roughly seven-star-equivalent demand, not
9.7/10. This is a scale anchor, not a claim that an axis equals official stars.

The tie-safe midrank policy preserves a real zero floor. It fixes the V0.4 bug
where a zero high-AR Reading term ranked at 96.28% because 4,814 of 5,000
calibration maps were tied at zero.

## Version and data boundaries

- output schema: `map_demand_v0.5.0`
- review axis schema: `atomic_v0.5.0`
- archetype schema: `map_archetype_v0.3.0`
- canonical calibration: `map_demand_calibration_v03_star_scale_20k`
- canonical QA: `map_demand_qa_v03_star_scale_20k`
- human review package: `map_archetype_atomic_v03`

V0.5 uses the existing deterministic 20k QA extraction rather than the more
heavily quota-biased 5k phase. The empirical star-scale source is versioned by
the SHA-256 of the local `osu!.db`. Older six-axis and atomic-v0.4 responses
remain auditable but are incomparable and are never converted silently.

## Commands

```powershell
python tools\skill-profiler-map-demand-v01.py build-calibration --osu-db "G:\osu! 20210821\osu!.db"
python tools\skill-profiler-map-demand-v01.py qa
python tools\skill-profiler-map-demand-v01.py archetype-qa
python tools\skill-profiler-map-demand-v01.py archetype-review-ui --show-algorithm
```

The assisted review page is served at `http://127.0.0.1:8766/`. Omit
`--show-algorithm` for blind review.
