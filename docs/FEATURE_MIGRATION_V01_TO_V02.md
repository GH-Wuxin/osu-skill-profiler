# Feature Migration — v0.1 (104 features) → v0.2 (Local Signal Layer)

Status: **v0.1 frozen; v0.2 added as an independent per-object layer.**

## Policy

- The v0.1 contract (104 deterministic features, `feature_version` 0.1.0)
  remains **frozen and loadable**. No v0.1 feature is modified, removed,
  renamed, or redefined by v0.2.
- v0.2 signals live in a separate `ls.*` namespace with
  `SIGNAL_VERSION = 0.2.0` and can never collide with v0.1 names.
- Existing v0.1 outputs remain byte-deterministic. The 104-feature QA baseline
  is unchanged (126,509 maps, 0 NaN/Inf, 93/93 tests) and the v0.2 QA pipeline
  asserts `feature_count_distribution == {104: n}` on every phase.
- The public profile schema version (`SCHEMA_VERSION`) stays `0.1.0`; the
  v0.2 local-signal sub-contract is versioned independently.

## Added signals (v0.2, `ls.*`)

35 schema entries; 28 are numeric model-input signals; 7 are structural /
context / provenance entries.

### Timing

- `ls.delta_time_ms` — raw start-to-start delta (file order)
- `ls.adjusted_delta_time_ms` — 25 ms semantic clamp
- `ls.last_object_end_delta_time_ms` — slider-tail-aware end delta
- `ls.minimum_jump_time_ms` — adjusted delta minus previous lazy travel, 25 ms
  floor

### Spatial (CS-normalised)

- `ls.jump_distance_raw_px`
- `ls.jump_distance_cs_normalised`
- `ls.lazy_jump_distance_cs_normalised`
- `ls.minimum_jump_distance_cs_normalised`
- `ls.cs_scale`, `ls.radius_px`

### Slider lazy travel / raw geometry

- `ls.lazy_end_position_x_px`, `ls.lazy_end_position_y_px`
- `ls.lazy_travel_distance_cs_normalised`, `ls.lazy_travel_time_ms`
- `ls.travel_distance_cs_normalised`, `ls.travel_time_ms`
- `ls.slider_duration_ms`, `ls.slider_velocity_px_per_ms`,
  `ls.slider_path_distance_px`
- `ls.slider_span_count`, `ls.slider_tick_count`,
  `ls.slider_nested_object_count`

### Angles / reaction

- `ls.slider_aware_angle_rad`, `ls.normalised_vector_angle_rad`
- `ls.preempt_ms`, `ls.fade_in_ms`, `ls.hit_window_great_ms`
- `ls.double_tap_feasibility`

### Structure / context

- `ls.original_index`, `ls.time_sorted_index`, `ls.object_type`
- `ls.start_time_ms`, `ls.end_time_ms`, `ls.spinner_context`, `ls.provenance`

## Unchanged signals (v0.1)

All 104 v0.1 features are unchanged:

- temporal (31)
- spatial (31)
- slider (28)
- section (8)
- difficulty context (6)

`docs/FEATURES.md` remains the authoritative catalog for v0.1.

## Deprecated duplicates (v0.1 → v0.2 canonicalisation)

The v0.1 contract review identified three exact-duplicate pairs. v0.1 keeps
emitting both names with identical meaning; v0.2 marks the deprecated side as
an alias. No historical value changes meaning.

| Deprecated (v0.1 keeps emitting) | Canonical | Reason |
| --- | --- | --- |
| `temporal.burst_count_250ms` | `temporal.dense_section_count` | both count runs of >= 2 gaps <= 250 ms; dense_section_count is canonical |
| `temporal.burst_longest_duration_ms_250ms` | `temporal.longest_dense_section_ms` | both measure the longest dense 250 ms run |
| `section.duration_weighted_density_per_s` | `temporal.density_objects_per_s` | map-level values coincide by construction |

Machine-readable form: `migration_table()` in
`src/osu_skill_profiler/signals/contract.py`
(`from_feature_version=0.1.0`, `to_feature_version=0.2.0`, 3 aliases).

## Semantic changes between v0.1 and v0.2

| Topic | v0.1 behaviour | v0.2 behaviour |
| --- | --- | --- |
| Distance normalisation | `x/512`, `y/384` (non-uniform, CS-ignoring) | uniform `px` + CS scale `50/radius` in `ls.*` |
| Minimum delta | raw deltas used (0 ms for simultaneous objects) | `ls.adjusted_delta_time_ms` applies the official 25 ms semantic clamp |
| Slider duration/velocity | estimated from `pixel_length / (SM*100*SV) * beatLength` | `ls.slider_duration_ms` / `ls.slider_velocity_px_per_ms` from path + precision-adjusted beat length |
| Slider movement | no path simulation | follow-circle lazy cursor simulation (`lazy_*`, `travel_*`) |
| Angle | raw object positions only | `ls.slider_aware_angle_rad` = `min(plain, slider)` with second-last nested object |
| AR | raw metadata only | `ls.preempt_ms` / `ls.fade_in_ms` derived; missing AR stays `None` + provenance |
| OD | raw metadata only | `ls.hit_window_great_ms` derived |
| Double-tap | not present | `ls.double_tap_feasibility` (observable reference signal) |
| Unknown slider geometry | estimated values always produced | `None` + provenance (`path_blocked:*`, `slider_spans_exceeded:*`, `slider_tick_count_exceeded`) |
| Ordering | features consume normalized time-sorted view | both `original_index` and `time_sorted_index` preserved |

None of these changes alter any v0.1 value; they only add new information.

## Migration policy

1. Consumers that only need v0.1 keep working unchanged; ignore `ls.*`.
2. Consumers that need gameplay-aware per-object signals should migrate to
   the `ls.*` namespace. Per-object rows are the source of truth; segment
   summaries are derived (mean/p90/max per 5 s window).
3. Do not mix v0.1 raw-distance semantics with v0.2 CS-normalised semantics in
   the same downstream feature without documenting the unit change.
4. Missing values in `ls.*` are `None`; check `ls.provenance` before imputing.
   Imputation is a downstream decision and must be explicit.
5. v0.1 duplicates remain deprecated aliases; do not build new logic on the
   deprecated names.

## Regression evidence

- v0.1 QA: 126,509 / 126,509 PASS, 0 NaN/Inf, 104 features stable.
- v0.2 QA: 5k / 20k / full 126,509 all PASS; 0 NaN/Inf; 0 ordering/coverage/
  serialization failures.
- Tests: 93/93 (v0.1) → 126/126 (v0.1 + 33 new v0.2 tests).
- Golden: 148/148 checks (Gate B).
