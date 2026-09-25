# Unified Star and Player Skill implementation v0.1

This layer is independent of the frozen `FORMAL_MAP_DEMAND_V040` output. It
does not rewrite `demand_star_equivalent`, change SliderPressure, or select a
new runtime algorithm.

## Components

| File | Role |
|---|---|
| `tools/map_demand_v01/unified_star_scale_v01.py` | Fit/load an axis-specific empirical rank mapping into one ppy NM reference ruler and attach it as additional fields. |
| `tools/map_demand_v01/player_skill_rating_v01.py` | Validate normalized multi-map player evidence and estimate per-axis interval-censored capacity. |
| `tools/map_demand_v01/measurement_release_v01.py` | Narrow entry point for both layers. |
| `tools/build_unified_star_calibration_v01.py` | Build a calibration artifact from a prepared JSONL corpus. It never walks Songs. |

## Map corpus row

The builder accepts one JSON object per line:

```json
{
  "map_id": "beatmap-or-checksum",
  "ppy_nm_star": 6.42,
  "stratum": "ranked_stream",
  "axes": {
    "jump_aim": 8.1,
    "flow_aim": 4.3,
    "aim_control": 5.2,
    "spatial_precision": 3.9,
    "raw_speed": 6.0,
    "finger_control": 4.7,
    "reading": 5.0,
    "stamina": 7.2,
    "endurance": 6.8
  }
}
```

`ppy_nm_star` is retained for corpus coverage and audit. It is not used as a
per-axis regression target. The common value is created by mapping each axis'
empirical rank to the supplied ppy NM reference distribution.

## Build a candidate artifact

```powershell
$env:PYTHONPATH = "src;tools"
python tools/build_unified_star_calibration_v01.py `
  --records path/to/map-corpus.jsonl `
  --reference training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k/calibration.json `
  --output training/datasets/unified_star_calibration_v01 `
  --source-scope prepared-corpus-v01 `
  --corpus-id prepared-corpus-v01
```

The artifact remains `CANDIDATE` until its declared map count, per-axis
coverage, and stratum gates are met. A single fixture cannot make it formal.

## Attach the independent map layer

```python
from map_demand_v01.measurement_release_v01 import apply_map_measurements

measured = apply_map_measurements(frozen_v040_output, calibration)
```

The result keeps every v0.40 field and adds, per axis:

- `raw_value` and `raw_unit`;
- `unified_star_equivalent`;
- `unified_star_status`;
- `unified_star_percentile`;
- calibration and support diagnostics.

Values outside observed calibration support are `UNKNOWN` with a reason; they
are never clamped to a low rating.

## Player evidence row

The player estimator consumes already normalized axis outcomes. A score parser
must not pretend that raw accuracy or pp is a Skill Rating. It must first emit
an axis outcome with provenance:

```python
from map_demand_v01.player_skill_rating_v01 import (
    DEMONSTRATED,
    NOT_DEMONSTRATED,
    make_evidence_record,
)

row = make_evidence_record(
    player_id="player-id",
    map_id="map-id",
    timestamp="2026-09-25T00:00:00Z",
    source="normalized_score_or_replay_adapter",
    normalization_id="score-normalization-v01",
    map_demand={
        "jump_aim": {
            "unified_star_equivalent": 6.2,
            "unified_star_status": "ADMITTED"
        }
    },
    axis_outcomes={
        "jump_aim": {
            "status": DEMONSTRATED,
            "evidence_count": 1,
            "source_detail": "adapter-defined-and-audited",
        }
    },
)
```

The estimator uses demonstrated observations as lower bounds and explicitly
normalized non-demonstrations as upper bounds. A finite bracket can be admitted
as an axis rating; lower-bound-only evidence remains a candidate; failures with
no demonstrated capacity remain `UNKNOWN`. The output includes rating,
uncertainty bounds, evidence count, coverage, source window, and per-observation
provenance. No cross-axis overall scalar is emitted by this version.

## Current boundary

The implementation is ready for corpus/evidence ingestion, but no formal
calibration artifact is claimed yet. The next data task is to prepare a broad,
stratified map corpus and normalized player evidence. That task is separate
from the code path and does not require scanning the full Songs library.
