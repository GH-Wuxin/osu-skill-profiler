# Unified Star and Player Skill implementation v0.1

This layer is independent of the frozen `FORMAL_MAP_DEMAND_V040` output. It
does not rewrite `demand_star_equivalent`, change SliderPressure, or select a
new runtime algorithm.

## Components

| File | Role |
|---|---|
| `tools/map_demand_v01/unified_star_scale_v01.py` | Fit/load an axis-specific empirical rank mapping into one ppy reference ruler per non-FL mod context and attach it as additional fields. |
| `tools/map_demand_v01/player_skill_rating_v01.py` | Validate normalized multi-map player evidence and estimate per-axis interval-censored capacity. |
| `tools/map_demand_v01/unified_corpus_index_v01.py` | Build an explicit, MD5/version keyed map index. Index mode is cheap; measure mode fills v0.40 raw axes only for cache misses. |
| `tools/map_demand_v01/player_score_evidence_v01.py` | Ingest every score/pp row, preserve raw performance fields, and pass only explicit replay/axis outcomes to Skill Rating. |
| `tools/map_demand_v01/measurement_release_v01.py` | Narrow entry point for both layers. |
| `tools/build_unified_star_calibration_v01.py` | Build a calibration artifact from a prepared JSONL corpus. It never walks Songs. |

## Map corpus row

The builder accepts one JSON object per line:

```json
{
  "map_id": "beatmap-or-checksum",
  "mod_context": "NM",
  "ppy_star": 6.42,
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

`ppy_star` is retained for corpus coverage and audit for the declared mod
context. It is not used as a per-axis regression target. The common value is created by mapping each axis'
empirical rank to the supplied ppy reference distribution for the row's exact mod context. Contexts are calibrated separately.

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

## Universal local map coverage

The corpus index separates coverage from expensive measurement. Prefer the
existing scan or manifest so the corpus boundary is explicit:

```powershell
$env:PYTHONPATH = "src;tools"
python tools/map_demand_v01/unified_corpus_index_v01.py `
  --mode index `
  --scan training/datasets/corpus_scan.jsonl `
  --osu-db "G:/osu! 20210821/osu!.db" `
  --output training/datasets/unified_measurement_index_v01.jsonl `
  --resume
```

This writes one row for every eligible standard map, including its content
MD5, file digest, local ppy star for the selected mod context when available, and an explicit
`UNMEASURED` status. Demand computation is incremental and versioned:

```powershell
python tools/map_demand_v01/unified_corpus_index_v01.py `
  --mode measure `
  --scan training/datasets/corpus_scan.jsonl `
  --osu-db "G:/osu! 20210821/osu!.db" `
  --reference-calibration training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k/calibration.json `
  --output training/datasets/unified_measurement_index_v01.jsonl `
  --workers 2 `
  --resume
```

Rows are reused only when their content MD5, v0.40 algorithm identity, and
calibration identity match. The command never rewrites v0.40 fields. A full
Songs walk is therefore a deliberate corpus-index operation, not an implicit
side effect of a player query.

The same indexer accepts any stored non-FL standard context without changing
the map identity:

```powershell
python tools/map_demand_v01/unified_corpus_index_v01.py `
  --mode index --scan training/datasets/corpus_scan.jsonl `
  --osu-db "G:/osu! 20210821/osu!.db" `
  --all-stored-mods --output training/datasets/unified_measurement_index_all_mods.jsonl
```

For a controlled batch, use `--mods HDDT` (or repeat `--mods`) and run
`--mode measure`. FL is intentionally excluded from map-demand calibration;
its score/pp rows remain ingestible and auditable.

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

## All score and pp coverage

Score sources can be normalized without pretending that pp is an axis rating:

```powershell
python tools/map_demand_v01/player_score_evidence_v01.py `
  --input scores.jsonl `
  --map-index training/datasets/unified_measurement_index_v01.jsonl `
  --output normalized-score-evidence.jsonl `
  --source osu_api_export
```

Each output row retains `pp_measurement`, accuracy, rank, mods, timestamp, and
the map join status. Rows with no replay-derived axis outcomes remain
`PERFORMANCE_ONLY` and are still counted as ingested pp. Only rows carrying
explicit axis outcomes plus unified map demand become Skill Rating evidence.
Use `skill_evidence_records()` or `estimate_player_from_scores()` to feed the
multi-map estimator. If a player's ready evidence spans several non-FL
contexts, the score entry point partitions it into one profile per context;
it never averages stars from incompatible ppy rulers.

The same path accepts score rows for every mod spelling it can identify. The
local osu!.db reader supplies each stored osu!standard context except FL; raw
rows for a context whose v0.40 transform is not available remain retained with
their source mods and pp, and are not silently re-labeled as NM.

## Current boundary

The implementation now has the reusable coverage path. The local 126k-map
corpus can be indexed once and measured lazily or in controlled batches. A
formal common-star admission still depends on the measured corpus reaching the
contract's breadth gates, and a player's Skill Rating still depends on that
player's multi-map, multi-time axis evidence. Neither condition is faked from
one fixture or from total pp.
