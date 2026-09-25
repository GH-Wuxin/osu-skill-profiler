# Formal Map-Demand / Slider Release v0.40

v0.40 is the deployable public path for one local `.osu` file.  It is
map-side demand evidence, not a player ability model.

## What is admitted

`profile-map` now runs the frozen `MAP_DEMAND_V100` release and the bounded
v0.36 Slider pressure scan.  The output contains:

- nine numeric map-demand axes: `jump_aim`, `flow_aim`, `aim_control`,
  `spatial_precision`, `raw_speed`, `finger_control`, `reading`, `stamina`,
  and `endurance`;
- formal Flow, Aim Control, and Micro Precision route admission when the
  corresponding ppy-derived axis is emitted with finite evidence;
- a Slider pressure vector with physical fields and a peak scalar defined as
  `max(required_cursor_velocity_norm_px_per_ms)` over support-gated sustained
  candidates.

The pressure scalar is not a weighted sum, a star rating, or a player score.
Maps without a valid candidate report `NO_SUSTAINED_CANDIDATE`; no scalar is
invented for them.

## Public command

```powershell
python -m osu_skill_profiler.cli.main profile-map path\to\map.osu --out profile.json
```

The output fields are:

- `map_demand.axes[*].value` and `.status`;
- `map_demand.axis_values` for direct consumption;
- `slider_evidence.pressure_vector`;
- `map_demand.slider_pressure.scalar` and `.scalar_unit`;
- `slider_evidence.semantic_routes` for Flow, Aim Control, and Precision;
- `map_demand.player_skill_score_admitted`, always `false` in this release.

`stamina` and `endurance` retain their bounded `0–10` unit.  The other axes
use the existing descriptive star-equivalent units from the frozen release.
No mixed-unit overall scalar is published.

## Replay boundary and holdout

The independent Classic audit is stored in
`training/ppy_slider_replay_validation_v035/independent_classic_corpus_v040.json`.
The Python verifier rebuilds nested Slider identity from the map and compares
Lazer Classic aggregate counts with the Stable `.osr` header.  Oshama and
KAEDE are exact parity rows.  Glacierfall remains an explicit mismatch
holdout, and Nhelv remains a bounded timeout row.  Those rows are marked
`UNVERIFIED` for player-side judgement claims; they do not block map-demand
output.

All host traces used for this release were muted.  The release does not scan a
library or leaderboard and does not require the user to play a map.
