# Local Signal Contract v0.3

Status: **IMPLEMENTED; pending independent re-verification**

`SIGNAL_VERSION = 0.3.0` is the corrected current Local Signal contract.
`0.2.0` remains a frozen historical replay mode. Both are pinned to ppy/osu
commit `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`, difficulty version
`20260706`.

This is a delta contract over
[`LOCAL_SIGNAL_CONTRACT_V02.md`](LOCAL_SIGNAL_CONTRACT_V02.md). Every v0.2
field not named below keeps its documented unit, missing semantics and
reference boundary. The machine-readable source of truth is
`src/osu_skill_profiler/signals/contract.py`.

## Version boundary

| Local contract | Status | Slider duration | Travel repeat bonus | Late real tick |
| --- | --- | --- | --- | --- |
| `0.2.0` | historical/frozen | one span incorrectly used as total | `span_count^0.3` | did not move tracking end |
| `0.3.0` | current/default | total across every span | `repeat_count^0.3` | updates tracking end before reorder |

The historical behavior is deliberately retained only when callers select
`LocalSignalExtractor("0.2.0")`.

## Canonical slider contract

```text
span_count = max(1, parsed_slides)
repeat_count = span_count - 1
single_span_duration_ms = path_distance / velocity
total_slider_duration_ms = single_span_duration_ms * span_count
end_time_ms = start_time_ms + total_slider_duration_ms
```

New corrected code never uses an overloaded `repeats` variable to mean both
counts.

## New and changed fields

| Field | Unit | v0.3 semantic |
| --- | --- | --- |
| `ls.slider_repeat_count` | count | true repeat count, `span_count - 1` |
| `ls.slider_span_count` | count | number of spans from the `.osu` `slides` field; retained name, now explicitly paired with repeat count |
| `ls.slider_single_span_duration_ms` | ms | one traversal, `path_distance / velocity` |
| `ls.slider_total_duration_ms` | ms | every traversal, single-span duration multiplied by span count |
| `ls.slider_duration_ms` | ms | compatibility alias of `ls.slider_total_duration_ms` in v0.3 |
| `ls.end_time_ms` | ms | slider start plus total duration |
| `ls.travel_distance_cs_normalised` | normalised px | lazy travel multiplied by `max(1, repeat_count^0.3)` |
| `ls.lazy_travel_time_ms` | ms | tracking end includes a late real tick before tail reordering, matching the pinned source |

The schema grows from 35 fields in v0.2 to 38 in v0.3. Numeric signal count
is derived by `numeric_signals(version)` rather than hard-coded.

## Downstream timing effects

For repeat sliders, total end time can alter:

- `ls.last_object_end_delta_time_ms`;
- `ls.minimum_jump_time_ms`;
- nested repeat/tick event timing;
- `ls.lazy_travel_time_ms` and `ls.travel_time_ms`;
- lazy end/tail parity and subsequent slider-aware movement;
- per-segment placement and summaries;
- Reference preprocessing that consumes Local geometry.

These fields are tested directly; correctness is not inferred from
`ls.slider_total_duration_ms` alone.

## Missing, pathological and guard semantics

The v0.2 safety boundary remains in force:

- non-finite or non-positive timing produces `None` with provenance;
- path, flattening, span and tick budgets remain explicit guards;
- blocked geometry is never replaced by a fabricated path;
- no new clipping or imputation is introduced;
- malformed non-positive `.osu` span values retain the existing
  `slider_slides_nonpositive` provenance and are interpreted as one span.

## Migration rules

1. Do not compare v0.2 and v0.3 values without retaining `signal_version`.
2. New consumers should read `ls.slider_total_duration_ms` and
   `ls.slider_repeat_count` explicitly.
3. `ls.slider_duration_ms` remains for compatibility but should not be used
   when code needs to distinguish one-span from total duration.
4. Historical artifacts under `training/datasets/golden_v02/` and
   `training/datasets/local_signal_qa/` are immutable.
5. Corrected artifacts belong under `golden_v03/` and
   `local_signal_qa_v03/`.

## Verification evidence

- Independent slider micro-oracles and mutation checks:
  `tests/test_foundation_remediation_v01.py`.
- Corrected synthetic golden:
  `training/datasets/golden_v03/` (20 fixtures, 155 checks).
- Old-vs-corrected semantic-delta and corpus QA:
  `docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md`.

No final difficulty, star rating, PP, taxonomy, labels or learned skill value
is introduced by v0.3.
