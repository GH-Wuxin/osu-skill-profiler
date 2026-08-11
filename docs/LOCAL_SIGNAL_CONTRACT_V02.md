# Local Signal Layer v0.2 Contract

Status: **IMPLEMENTED** (per-object observable signals, `ls.*` namespace).

Upstream reference (pinned, do not follow master):

- repository: `ppy/osu`
- commit: `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`
- difficulty version: `20260706` (`OsuDifficultyCalculator.Version`)

`SIGNAL_VERSION = 0.2.0`. The public profile schema version
(`osu_skill_profiler.SCHEMA_VERSION`) remains `0.1.0`; v0.2 adds an independent
per-object sub-contract and does not change any v0.1 feature.

## Layer model

Three layers are kept strictly separate:

| Layer | Content | Status |
| --- | --- | --- |
| A | observable local signals (`ls.*`) | implemented in v0.2 |
| B | official reference signals (`official_reference.*`) | not emitted; reference only |
| C | learned / interpretable skill representation | forbidden this phase |

Every `ls.*` signal in this document is **Layer A**: a deterministic
measurement of hit-object / gameplay geometry or reaction context. No official
difficulty final, no harmonic aggregation, no star-rating value, and no skill
score is produced.

## Extraction chain

```text
.osu text
  -> parse_osu_file            (strict parser, legacy format support)
  -> LocalSignalExtractor.extract
       -> per-object rows (file order + time_sorted_index)
       -> fixed-time 5s segment summaries (mean / p90 / max per numeric signal)
  -> CLI: extract-local-signals
```

Ordering rule: rows are emitted in **.osu file order** (`ls.original_index`).
`ls.time_sorted_index` is the rank when objects are sorted by
`(start_time, original_index)`. Downstream consumers must never assume file
order equals chronological order.

## Numeric safety

- No `NaN` / `Inf` is emitted. Non-finite intermediate results become `None`
  with a provenance flag.
- Pathological finite values (e.g. `1e306` pixel lengths) are **kept as-is**
  and provenance-tagged. No silent clipping, no winsorization, no imputation.
- The only clamp is a semantic clamp: the official 25 ms minimum delta.

## Missing semantics

Every signal has explicit missing semantics (see table). Missing values are
`None` and, where meaningful, accompanied by a `ls.provenance` flag such as:

- `no_previous` (first object)
- `ar_missing` / `od_missing` / `cs_missing` (missing difficulty metadata; never
  silently treated as AR/OD/CS 0)
- `cs_missing_for_distance_scale`
- `current_is_spinner` / `previous_is_spinner` (spinner context)
- `minimum_jump_time_previous_slider_unknown`
- `minimum_jump_distance_tail_unknown`
- `pixel_length_missing` / `pixel_length_nonfinite`
- `slider_multiplier_defaulted` / `slider_multiplier_nonpositive`
- `beat_length_nonpositive` / `precision_adjusted_beat_length_nonpositive`
- `slider_velocity_nonpositive` / `path_distance_invalid` / `path_distance_zero`
- `jump_distance_nonfinite` / `lazy_jump_distance_nonfinite`
- `plain_angle_nonfinite` / `slider_angle_nonfinite` /
  `normalised_vector_angle_nonfinite`
- `od_missing_for_double_tap` / `double_tap_lazy_jump_unknown`
- `cs_missing_for_lazy_scale`
- `lazy_cursor_nonfinite_geometry` / `lazy_end_nonfinite_geometry`
- `last_real_tick_reordered`
- geometry guards: `path_blocked:control_points_exceeded`,
  `path_blocked:flattening_budget_exceeded`,
  `slider_spans_exceeded:<n>`, `slider_tick_count_exceeded`

## Pathological slider geometry guards

A single high-degree Bezier slider (tens of thousands of control points)
requires O(n^2) work per adaptive subdivision level and can run effectively
forever. v0.2 therefore bounds the work and refuses to fabricate geometry:

| Guard | Limit | Provenance flag |
| --- | --- | --- |
| Bezier/perfect control points per path | `MAX_PATH_CONTROL_POINTS = 4096` | `path_blocked:control_points_exceeded` |
| Flattening operations per path | `MAX_PATH_FLATTEN_WORK = 5_000_000` | `path_blocked:flattening_budget_exceeded` |
| Slider spans | `MAX_SLIDER_SPANS = 10_000` | `slider_spans_exceeded:<n>` |
| Slider ticks per slider | `MAX_SLIDER_TICKS = 100_000` | `slider_tick_count_exceeded` |

A blocked slider keeps the unknown-geometry missing semantics for its
slider-dependent signals (all `None`) and carries the provenance flag. It is
never replaced by a fake path, a clipped value, or a silent fallback to
pixel-length estimates. This is a **documented semantic deviation** from
pinned ppy/osu, which flattens unconditionally (see
[`PPY_PARITY_REPORT_V02.md`](PPY_PARITY_REPORT_V02.md)).

## Signal table

Legend for column "flags":

- `context` — context-only signal; safe as model input, but not a standalone
  skill signal.
- `weak-label` — candidate for weak supervision.
- `meta` — structural/provenance metadata, not model input.

### Structure / ordering

| Signal | Unit | Definition / semantics | Missing | Flags |
| --- | --- | --- | --- | --- |
| `ls.original_index` | index | 0-based position in `[HitObjects]` file order | always present | meta |
| `ls.time_sorted_index` | index | rank when sorted by `(start_time, original_index)` | always present | meta |
| `ls.object_type` | enum | `circle \| slider \| spinner` | always present | context |
| `ls.start_time_ms` | ms | object start time | always present | context |
| `ls.end_time_ms` | ms | start + duration for sliders; spinner end; start for circles | slider without duration falls back to start (provenance) | context |
| `ls.spinner_context` | bool | current or immediate previous object is a spinner; upstream skips distances/angles in this context | always present | context |
| `ls.provenance` | list | provenance flags for missing / pathological / legacy semantics | always present | meta |

### Timing (official-inspired)

| Signal | Unit | Definition / semantics | Upstream | Missing |
| --- | --- | --- | --- | --- |
| `ls.delta_time_ms` | ms | raw start-to-start delta vs previous object in **file order** | `DifficultyHitObject.DeltaTime` | `None` for first object |
| `ls.adjusted_delta_time_ms` | ms | `max(delta_time_ms, 25)`; the official semantic clamp for simultaneous objects | `OsuDifficultyHitObject.AdjustedDeltaTime` | `None` for first object |
| `ls.last_object_end_delta_time_ms` | ms | `max(start - previous_end, 25)`; slider tail-aware; first difficulty row equals adjusted delta | `OsuDifficultyHitObject.LastObjectEndDeltaTime` | `None` for first object |
| `ls.minimum_jump_time_ms` | ms | `max(adjusted_delta - previous_slider_lazy_travel_time, 25)`; time budget after slider travel | `OsuDifficultyHitObject.MinimumJumpTime` | `None` for first object; `minimum_jump_time_previous_slider_unknown` when previous lazy travel time is unknown |

### CS / reaction context

| Signal | Unit | Definition / semantics | Upstream | Missing |
| --- | --- | --- | --- | --- |
| `ls.radius_px` | px | `64 * ((1 - 0.7*(CS-5)/5)/2 * 1.00041)` | `OsuHitObject.Radius` / `CalculateScaleFromCircleSize` | `None` when CS missing (`cs_missing`) |
| `ls.cs_scale` | ratio | `50 / radius_px` CS normalisation scale | `OsuDifficultyHitObject` normalised radius | `None` when CS missing |
| `ls.preempt_ms` | ms | AR-derived approach time: floor of the two-piece linear `1800 / 1200 / 450` range | `OsuHitObject.TimePreempt` | `None` when AR missing (`ar_missing`), never silent AR=0 |
| `ls.fade_in_ms` | ms | `400 * min(1, preempt / 450)` | `OsuHitObject.TimeFadeIn` | `None` when AR missing |
| `ls.hit_window_great_ms` | ms | full GREAT window `2*(floor(DifficultyRange(OD,80,50,20)) - 0.5)` | `DifficultyHitObject.HitWindowGreat` | `None` when OD missing (`od_missing`) |

### Spatial distance

| Signal | Unit | Definition / semantics | Upstream | Missing |
| --- | --- | --- | --- | --- |
| `ls.jump_distance_raw_px` | px | Euclidean start-to-start distance, unscaled | `OsuDifficultyHitObject.JumpDistance` (unscaled) | `None` first object; `0.0` in spinner context |
| `ls.jump_distance_cs_normalised` | normalised px | raw jump * `cs_scale` | `OsuDifficultyHitObject.JumpDistance` | `None` first object / missing CS; `0.0` spinner context |
| `ls.lazy_jump_distance_cs_normalised` | normalised px | previous lazy end (or previous start) to current start, CS-normalised | `OsuDifficultyHitObject.LazyJumpDistance` | `None` first object / missing CS; `0.0` spinner context |
| `ls.minimum_jump_distance_cs_normalised` | normalised px | `min(lazy_jump - (max_slider_radius - assumed_slider_radius), tail_jump - max_slider_radius)` floored at 0; anti-flow vs flow distance | `OsuDifficultyHitObject.MinimumJumpDistance` | `None` first object / missing CS / unknown tail; `0.0` spinner context |

### Slider lazy travel

| Signal | Unit | Definition / semantics | Upstream | Missing |
| --- | --- | --- | --- | --- |
| `ls.lazy_end_position_x_px` / `ls.lazy_end_position_y_px` | px | follow-circle lazy cursor endpoint (assumed radius 90 px, repeat threshold 50 px) | `OsuDifficultyHitObject.LazyEndPosition` | `None` non-sliders / unknown geometry |
| `ls.lazy_travel_distance_cs_normalised` | normalised px | lazy cursor path length, CS-normalised by slider radius | `OsuDifficultyHitObject.LazyTravelDistance` | `None` unknown geometry; `0.0` non-sliders |
| `ls.lazy_travel_time_ms` | ms | start to lazy tracking end (tail leniency `-36 ms`) | `OsuDifficultyHitObject.LazyTravelTime` | `None` unknown duration; `0.0` non-sliders |
| `ls.travel_distance_cs_normalised` | normalised px | lazy travel distance * `max(1, span_count^0.3)` | `OsuDifficultyHitObject.TravelDistance` | `None` unknown geometry; `0.0` non-sliders |
| `ls.travel_time_ms` | ms | `max(lazy_travel_time, 25)` | `OsuDifficultyHitObject.TravelTime` | `None` unknown duration; `0.0` non-sliders |

### Slider raw geometry

| Signal | Unit | Definition / semantics | Upstream | Missing |
| --- | --- | --- | --- | --- |
| `ls.slider_duration_ms` | ms | path-based duration: path distance / velocity | `Slider.EndTime - Slider.StartTime` | `None` non-sliders / unknown duration |
| `ls.slider_velocity_px_per_ms` | px/ms | ball velocity from SliderMultiplier, SV and precision-adjusted red beat length (SV clamp per pinned build) | `Slider.Velocity` / `GetPrecisionAdjustedBeatLength` | `None` non-sliders / unknown timing |
| `ls.slider_path_distance_px` | px | path distance used for duration (expected pixel length when present, else calculated) | `SliderPath.Distance` | `None` non-sliders |
| `ls.slider_span_count` | count | `max(1, slider_slides)` | `Slider.RepeatCount` / `SpanCount()` | `None` non-sliders |
| `ls.slider_tick_count` | count | generated `SliderTick` nested objects | `SliderEventGenerator.Generate` | `None` non-sliders / unknown duration |
| `ls.slider_nested_object_count` | count | head + ticks + repeats + tail | `Slider.NestedHitObjects` | `None` non-sliders / unknown duration |

### Angles

| Signal | Unit | Definition / semantics | Upstream | Missing |
| --- | --- | --- | --- | --- |
| `ls.slider_aware_angle_rad` | rad | `min(plain_angle, slider_angle)` in `[0, pi]`; slider angle uses the second-last nested object when the previous slider has travel | `OsuDifficultyHitObject.Angle` / `calculateSliderAngle` | `None` for first two objects, spinner contexts, or missing geometry |
| `ls.normalised_vector_angle_rad` | rad | `atan2(|dy|, |dx|)` of the incoming movement vector, `[0, pi/2]` | `OsuDifficultyHitObject.NormalisedVectorAngle` | `None` for first two objects, spinner contexts, or missing geometry |

### Double-tap feasibility

| Signal | Unit | Definition / semantics | Upstream | Missing |
| --- | --- | --- | --- | --- |
| `ls.double_tap_feasibility` | ratio | `0..1` feasibility of double-tapping this object with the next (delta ratio, hit window, lazy jump distance) | `OsuDifficultyHitObject.CalculateDoubleTapFeasibility` | `None` first object / missing OD; `0.0` last object (no next) |

## Model-input safety

All 28 numeric signals in `NUMERIC_SIGNALS` are finite when present and are
declared `model_input_safe=True` in the machine-readable schema. The following
are **not** model inputs:

- `ls.original_index`, `ls.time_sorted_index` — structural indices
- `ls.object_type` — categorical context (one-hot encoding is a downstream
  concern)
- `ls.provenance` — metadata only

`context_only=True` signals (start/end time, lazy end position, spinner
context) are safe as model input but must not be interpreted as standalone
skill signals.

## Weak-label candidates

Only two signals are flagged `weak_label_candidate=True` in v0.2:

- `ls.lazy_travel_distance_cs_normalised`
- `ls.double_tap_feasibility`

Both are observable/reference evidence. They must never be renamed or consumed
as `speed_skill` / `finger_control_score`.

## Segment integration

Per-object rows are retained first; aggregation is secondary:

- fixed-time 5 s windows aligned to the first object;
- per numeric signal: `mean`, `p90`, `max`;
- empty windows omitted; segment `start_idx` / `end_idx` cover all objects;
- no map-level difficulty scalar is produced by this layer.

## Non-goals

- No `StarRating`, no final `AimDifficulty` / `SpeedDifficulty` /
  `ReadingDifficulty` / `FlashlightDifficulty`, no final evaluator scores, no
  harmonic aggregation, no strain peaks, no performance conversion.
- No training, no gold labels, no taxonomy freeze, no WuxinBot integration.

## Authoritative source

The machine-readable contract lives in
`src/osu_skill_profiler/signals/contract.py` (`SIGNAL_SCHEMA`,
`NUMERIC_SIGNALS`, `migration_table()`). This document is a human-readable
companion; when they disagree, `contract.py` wins.
