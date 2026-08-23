# Feature Catalog

> Current catalog: **Feature v0.2.0** (106 fields).
> Feature v0.1.0 (104 fields) is frozen and replayable by explicitly
> constructing `FeatureExtractor(feature_version="0.1.0")`. The differences
> are documented in
> [FEATURE_MIGRATION_V01_TO_V02.md](FEATURE_MIGRATION_V01_TO_V02.md).

All features are **deterministic measurements**, not skill judgements. They
describe what is objectively measurable in a beatmap. Naming a feature
`temporal.burst_count_125ms` is a measurement; naming something
`tech_score` would be a hypothesis, so the project does not do that.

Machine-readable schema: `src/osu_skill_profiler/features/schema.py`.
Extractor: `src/osu_skill_profiler/features/extractor.py`.

## Naming conventions

- Dot-separated groups: `temporal.*`, `spatial.*`, `slider.*`, `section.*`,
  `difficulty.*`.
- Distribution features append `_mean`, `_std`, `_p50`, `_p75`, `_p90`,
  `_p95`, `_max`, `_min`.
- Every feature has a documented unit.
- `None` is used when a measurement is not defined (e.g. no sliders, no
  angles, constant input).

## Temporal

| feature | unit | meaning |
| --- | --- | --- |
| `temporal.object_count` | count | number of hit objects |
| `temporal.map_duration_ms` | ms | first object start to last object end |
| `temporal.density_objects_per_s` | objects/s | object count / duration |
| `temporal.bpm_*` | beats/min | local BPM at each object |
| `temporal.delta_time_ms_*` | ms | gap between consecutive object start times |
| `temporal.interval_ratio_mean` | ratio | mean ratio of consecutive delta times |
| `temporal.rhythm_entropy_bits` | bits | Shannon entropy of quantized delta-time buckets |
| `temporal.interval_diversity` | ratio | unique quantized intervals / interval count |
| `temporal.burst_count_250ms` / `_125ms` | count | runs of >= 2 gaps at or below threshold |
| `temporal.burst_max_len_250ms` / `_125ms` | count | longest burst run length |
| `temporal.burst_longest_duration_ms_250ms` / `_125ms` | ms | longest burst duration |
| `temporal.dense_section_count` | count | dense sections (gaps <= 250ms) |
| `temporal.longest_dense_section_ms` | ms | longest continuous dense section |
| `temporal.object_rate_max_1s` | objects/s | max objects in any 1s window |

## Spatial

| feature | unit | meaning |
| --- | --- | --- |
| `spatial.distance_norm_*` | normalized units | Euclidean distance to previous object on 512x384 field |
| `spatial.velocity_norm_per_s_*` | normalized units/s | distance / delta time |
| `spatial.acceleration_norm_per_s2_mean` | norm units/s^2 | mean velocity change rate |
| `spatial.acceleration_norm_per_s2_max` | norm units/s^2 | max velocity change rate |
| `spatial.angle_deg_*` | degrees | turn angle at object |
| `spatial.sharp_angle_ratio_lt_60` | ratio | fraction of angles < 60 degrees |
| `spatial.direction_change_ratio_ge_90` | ratio | fraction of angles >= 90 degrees |
| `spatial.net_displacement_ratio` | ratio | start-to-end distance / path length |
| `spatial.x_range_norm` / `spatial.y_range_norm` | normalized units | bounding-box extent |

## Slider

| feature | unit | meaning |
| --- | --- | --- |
| `slider.slider_ratio` | ratio | sliders / all objects |
| `slider.duration_ms_*` | ms | total slider duration across all spans |
| `slider.velocity_px_per_s_*` | px/s | pixel length / single-span duration |
| `slider.length_px_*` | px | slider pixel length |
| `slider.repeat_count_total` | count | sum of true repeat counts (span count − 1) |
| `slider.repeat_count_max` | count | maximum true repeat count |
| `slider.span_count_total` | count | sum of slider span counts from the `.osu` slides field |
| `slider.span_count_max` | count | maximum slider span count |
| `slider.to_circle_transition_count` | count | circles immediately following sliders |

> Historical v0.1 fields `slider.repeats_total` / `slider.repeats_max` were
> raw span counts under misleading repeat names. They remain replayable only
> under `feature_version="0.1.0"` and are marked
> `DEPRECATED_FOR_NEW_MODELS` in the leakage registry.

## Section

Derived from fixed 5s windows over the whole map (in the extractor's
`_section_features`) or from segment aggregation (in the profiler output).

| feature | unit | meaning |
| --- | --- | --- |
| `section.window_count` | count | non-empty fixed windows used |
| `section.density_per_s_mean/p95/max` | objects/s | window density distribution |
| `section.duration_weighted_density_per_s` | objects/s | density weighted by window duration |
| `section.velocity_norm_per_s_p90` | norm units/s | p90 of window p90 velocities |
| `section.angle_deg_p90` | degrees | p90 of window p90 angles |
| `section.peak_density_window_start_ms` | ms | start of densest window |

## Difficulty context

| feature | unit | meaning |
| --- | --- | --- |
| `difficulty.AR` / `OD` / `CS` / `HP` | osu values | approach rate, overall difficulty, circle size, HP drain |
| `difficulty.SliderMultiplier` | multiplier | slider velocity multiplier |
| `difficulty.SliderTickRate` | ticks/beat | slider tick rate |

## Profiler output note

In the public profile JSON, the `features` field is **segment-aggregated**
(mean/std/max/p90 of per-segment features), while weak-label rules consume the
full-map extractor output. Both representations are deterministic and
versioned.
