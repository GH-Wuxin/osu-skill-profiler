# Map Demand Atomic V0.6 / Archetype V0.4

`MAP_DEMAND_ATOMIC_V04` removes the V0.5 10-star output ceiling. Each emitted
axis now exposes `demand_star_equivalent`, obtained by mapping the axis's
diagnostic component rank through the empirical distribution of local
osu!standard NoMod star ratings. The value is non-negative and may exceed
10.0. `score` remains `demand_star_equivalent / 10` for internal policy
compatibility and is therefore also allowed to exceed 1.0.

The scale is empirical rather than intrinsically bounded. Above the 99.9th
component percentile it uses a robust log-survival tail fitted between the
99.9th and 99.99th star quantiles. This preserves separation above 10 stars
without allowing a handful of malformed or intentionally impossible local
maps (the inspected database reaches 315.8 stars) to turn an ordinary extreme
result into hundreds of stars. At rank 1.0, finite corpus resolution supplies
a half-observation survival floor; this is a data-resolution limit, not a
10-star product cap.

Versioned identities:

- algorithm: `MAP_DEMAND_ATOMIC_V04`
- output schema: `map_demand_v0.6.0`
- review axis schema: `atomic_v0.6.0`
- archetype schema: `map_archetype_v0.4.0`
- canonical calibration: `map_demand_calibration_v04_unbounded_star_scale_20k`
- canonical QA: `map_demand_qa_v04_unbounded_star_scale_20k`

V0.5 calibration artifacts remain loadable and retain their declared
`cap_stars: 10.0` behaviour. They are never silently reinterpreted as V0.6.

This change affects scale only. It does not claim that the current Reading,
Flow Aim, Finger Control, Stamina, or Spatial Precision formulas have passed
human validation. Extreme-map feedback remains evidence for later formula
work, not a reason to tune a single case into agreement.
