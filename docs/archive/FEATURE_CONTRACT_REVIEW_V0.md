# Feature Contract Review — V0 (104 features)

Status: **REVIEW ONLY** — no feature was added, removed, renamed, redefined, or
deleted as a result of this document. All classifications are audit findings for
a future `feature_version` contract decision.

Audited against: ppy/osu @
`b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e` (difficulty version `20260706`).
Full upstream inventory and concept mapping:
[`PPY_DIFFICULTY_REFERENCE_AUDIT.md`](PPY_DIFFICULTY_REFERENCE_AUDIT.md).

Evidence base:

- `training/datasets/feature_qa/feature_stats_full.json` (126,509 maps)
- `training/datasets/feature_qa/feature_correlations.json` (deterministic 20k nested subset)
- `training/datasets/feature_qa/segment_stats.json`
- `training/datasets/feature_qa/FEATURE_QA_REPORT.md`
- `src/osu_skill_profiler/features/{schema,extractor}.py`
- `src/osu_skill_profiler/parser/normalized.py`

QA baseline (all phases): 126,509 / 126,509 PASS; 0 NaN/Inf; 0 missing > 50 %;
feature count stable at 104; 93/93 tests.

## Classification legend

| Value | Meaning |
| --- | --- |
| `KEEP` | keep as a deterministic feature in the current contract. |
| `KEEP_AS_METADATA` | keep, but treat as context/metadata, not as a skill signal. |
| `RENAME` | name is misleading relative to its definition; rename in the next contract. |
| `REDEFINE` | definition should change in the next contract to better match the intended signal. |
| `REDUNDANT_CANDIDATE` | nearly or exactly duplicates another feature; candidate for merge in the next contract. |
| `REMOVE_CANDIDATE` | candidate for removal in the next contract (no change made here). |
| `NEEDS_REVIEW` | definition or edge-case behaviour needs investigation before trusting it. |

No `REMOVE_CANDIDATE` is issued in this review: every feature has at least a
contextual or diagnostic use in v0.

## High-level findings

### 18 pairs with |r| > 0.98 (20k deterministic subset)

| Feature A | Feature B | r | Note |
| --- | --- | --- | --- |
| `temporal.burst_count_250ms` | `temporal.dense_section_count` | 1.0 | exact duplicate by construction |
| `temporal.burst_longest_duration_ms_250ms` | `temporal.longest_dense_section_ms` | 1.0 | exact duplicate by construction |
| `section.duration_weighted_density_per_s` | `temporal.density_objects_per_s` | 1.0 | functional duplicate (weighted window mean collapses to object_count / covered duration) |
| `temporal.delta_time_ms_mean` | `temporal.delta_time_ms_p50` | 0.999825 | near-duplicate family |
| `temporal.delta_time_ms_mean` | `temporal.delta_time_ms_p75` | 0.999463 | near-duplicate family |
| `temporal.delta_time_ms_p50` | `temporal.delta_time_ms_p75` | 0.999262 | near-duplicate family |
| `temporal.delta_time_ms_p75` | `temporal.delta_time_ms_p90` | 0.999243 | near-duplicate family |
| `temporal.delta_time_ms_p90` | `temporal.delta_time_ms_p95` | 0.999215 | near-duplicate family |
| `temporal.delta_time_ms_mean` | `temporal.delta_time_ms_p90` | 0.998354 | near-duplicate family |
| `temporal.delta_time_ms_p75` | `temporal.delta_time_ms_p95` | 0.997966 | near-duplicate family |
| `temporal.delta_time_ms_p50` | `temporal.delta_time_ms_p90` | 0.997793 | near-duplicate family |
| `temporal.delta_time_ms_mean` | `temporal.delta_time_ms_p95` | 0.996957 | near-duplicate family |
| `temporal.delta_time_ms_p50` | `temporal.delta_time_ms_p95` | 0.996067 | near-duplicate family |
| `spatial.velocity_norm_per_s_p90` | `spatial.velocity_norm_per_s_p95` | 0.995232 | near-duplicate tail stats |
| `section.density_per_s_mean` | `temporal.density_objects_per_s` | 0.993844 | near-duplicate density |
| `section.density_per_s_mean` | `section.duration_weighted_density_per_s` | 0.993844 | near-duplicate density |
| `spatial.velocity_norm_per_s_p75` | `spatial.velocity_norm_per_s_p90` | 0.986515 | near-duplicate tail stats |
| `section.density_per_s_mean` | `section.density_per_s_p95` | 0.984308 | near-duplicate density |

### 8 proxy relationships (feature vs manifest/QA proxy)

| Feature | Proxy | r | Note |
| --- | --- | --- | --- |
| `difficulty.AR` | `ar` | 1.0 | direct metadata echo |
| `difficulty.CS` | `cs` | 1.0 | direct metadata echo |
| `difficulty.OD` | `od` | 1.0 | direct metadata echo |
| `slider.slider_ratio` | `slider_ratio` | 1.0 | same value computed twice |
| `temporal.object_count` | `object_count` | 1.0 | same value computed twice |
| `section.window_count` | `duration_ms` | 0.994324 | window count is a duration proxy |
| `difficulty.AR` | `od` | 0.954352 | cross-metadata correlation (old maps) |
| `difficulty.OD` | `ar` | 0.954352 | cross-metadata correlation (old maps) |

### Extreme finite values (|max| >= 1e12, full corpus)

| Feature | max | Source |
| --- | --- | --- |
| `slider.length_px_std` | 9.17e306 | degenerate slider pixel lengths |
| `slider.velocity_px_per_s_mean/std/p75/p90/p95/max` | up to 8.24e303 | degenerate beat lengths → duration estimate near 0 |
| `temporal.bpm_p75/p95/max` | up to 6.00e302 | degenerate red timing points (beat length near 0) |

All values remain finite in feature output (non-finite mapped to `None`); they
are provenance-tagged in QA and must not be silently clipped.

### Missingness (full corpus)

- `difficulty.AR`: 10,654 / 126,509 missing (8.4 %) — old maps without the field.
- `difficulty.OD/CS/HP`, `difficulty.SliderMultiplier`, `difficulty.SliderTickRate`: 0 missing.
- Slider features (`slider.length_px_*`, `slider.duration_ms_*`,
  `slider.velocity_px_per_s_*`): ~0.4 % missing (maps with no sliders or
  degenerate pixel length).
- `temporal.delta_time_ms_*` / `spatial.*`: 15 missing (single-object maps).

## Per-feature audit

### Temporal (31)

| Feature | Classification | Rationale |
| --- | --- | --- |
| `temporal.object_count` | `KEEP` | Fundamental size signal; also a manifest proxy (r=1.0). |
| `temporal.map_duration_ms` | `KEEP` | Fundamental context; needed for density and stamina reasoning. |
| `temporal.density_objects_per_s` | `KEEP` | Core density; note r=1.0 with `section.duration_weighted_density_per_s`. |
| `temporal.bpm_mean` | `KEEP` | Central tendency of local BPM. |
| `temporal.bpm_std` | `KEEP` | BPM variability (timing complexity context). |
| `temporal.bpm_p50` | `KEEP` | Robust central BPM. |
| `temporal.bpm_p90` | `KEEP` | High-BPM context. |
| `temporal.bpm_min` | `KEEP` | Low-BPM context. |
| `temporal.bpm_p75` | `NEEDS_REVIEW` | Tail polluted by degenerate timing points (max 6e302). |
| `temporal.bpm_p95` | `NEEDS_REVIEW` | Tail polluted by degenerate timing points. |
| `temporal.bpm_max` | `NEEDS_REVIEW` | Tail polluted by degenerate timing points. |
| `temporal.delta_time_ms_mean` | `KEEP` | Core timing; near-duplicate of p50/p75/p90/p95. |
| `temporal.delta_time_ms_std` | `KEEP` | Timing variability; no exact duplicate. |
| `temporal.delta_time_ms_p50` | `KEEP` | Robust central delta. |
| `temporal.delta_time_ms_p75` | `KEEP` | Part of near-duplicate delta family. |
| `temporal.delta_time_ms_p90` | `KEEP` | Part of near-duplicate delta family. |
| `temporal.delta_time_ms_p95` | `KEEP` | Part of near-duplicate delta family. |
| `temporal.delta_time_ms_max` | `KEEP` | Longest gap (break/spacing context). |
| `temporal.delta_time_ms_min` | `KEEP` | Densest local gap; overlaps with mean family but carries distinct edge meaning. |
| `temporal.interval_ratio_mean` | `KEEP` | Simple rhythm-change statistic; official island model is more complete (PARTIAL_OVERLAP). |
| `temporal.rhythm_entropy_bits` | `KEEP` | Coarse rhythm irregularity; used by weak rule `wsp003`. |
| `temporal.interval_diversity` | `KEEP` | Coarse rhythm diversity; used by weak rule `wsp003`. |
| `temporal.burst_count_250ms` | `REDUNDANT_CANDIDATE` | Exact duplicate of `temporal.dense_section_count` (same `_burst_metrics` call). Keep in v0, merge in next contract. |
| `temporal.burst_max_len_250ms` | `KEEP` | Burst run length; no exact duplicate. |
| `temporal.burst_longest_duration_ms_250ms` | `REDUNDANT_CANDIDATE` | Exact duplicate of `temporal.longest_dense_section_ms`. |
| `temporal.burst_count_125ms` | `KEEP` | 125 ms threshold carries distinct burst semantics. |
| `temporal.burst_max_len_125ms` | `KEEP` | Distinct 125 ms run length. |
| `temporal.burst_longest_duration_ms_125ms` | `KEEP` | Distinct 125 ms duration; correlated with `burst_max_len_125ms` but not identical. |
| `temporal.dense_section_count` | `REDUNDANT_CANDIDATE` | Exact duplicate of `temporal.burst_count_250ms`. |
| `temporal.longest_dense_section_ms` | `REDUNDANT_CANDIDATE` | Exact duplicate of `temporal.burst_longest_duration_ms_250ms`. |
| `temporal.object_rate_max_1s` | `KEEP` | Sliding-window peak rate; closest local analogue to official strain-time density. |

### Spatial (31)

| Feature | Classification | Rationale |
| --- | --- | --- |
| `spatial.distance_norm_mean` | `KEEP` | Mean spacing; future `REDEFINE` candidate for CS-normalised uniform-scale distance. |
| `spatial.distance_norm_std` | `KEEP` | Spacing variability. |
| `spatial.distance_norm_p50` | `KEEP` | Robust spacing. |
| `spatial.distance_norm_p75` | `KEEP` | High-spacing tail. |
| `spatial.distance_norm_p90` | `KEEP` | High-spacing tail. |
| `spatial.distance_norm_p95` | `KEEP` | High-spacing tail (used by `wsp001`). |
| `spatial.distance_norm_max` | `KEEP` | Extreme jump context. |
| `spatial.distance_norm_min` | `KEEP` | Stack/overlap context. |
| `spatial.velocity_norm_per_s_mean` | `KEEP` | Movement rate central tendency. |
| `spatial.velocity_norm_per_s_std` | `KEEP` | Movement rate variability. |
| `spatial.velocity_norm_per_s_p50` | `KEEP` | Robust movement rate. |
| `spatial.velocity_norm_per_s_p75` | `KEEP` | Movement tail; near-duplicate of p90/p95 (r>0.98). |
| `spatial.velocity_norm_per_s_p90` | `KEEP` | Movement tail; near-duplicate of p95 (r=0.995). |
| `spatial.velocity_norm_per_s_p95` | `KEEP` | Movement tail; used by `wsp001`. |
| `spatial.velocity_norm_per_s_max` | `KEEP` | Extreme movement; correlated with acceleration max. |
| `spatial.velocity_norm_per_s_min` | `KEEP` | Near-zero movement context. |
| `spatial.acceleration_norm_per_s2_mean` | `NEEDS_REVIEW` | Discrete velocity derivative; noisy, skips non-positive deltas; no direct official counterpart. |
| `spatial.acceleration_norm_per_s2_max` | `NEEDS_REVIEW` | Noisy derivative; correlated with velocity max; extreme outliers. |
| `spatial.angle_deg_mean` | `KEEP` | Mean turn angle; future `REDEFINE` candidate (slider-aware, official-style angle). |
| `spatial.angle_deg_std` | `KEEP` | Angle variability. |
| `spatial.angle_deg_p50` | `KEEP` | Robust turn angle. |
| `spatial.angle_deg_p75` | `KEEP` | Wide-angle tail. |
| `spatial.angle_deg_p90` | `KEEP` | Wide-angle tail. |
| `spatial.angle_deg_p95` | `KEEP` | Wide-angle tail. |
| `spatial.angle_deg_max` | `KEEP` | 180° reversal context. |
| `spatial.angle_deg_min` | `KEEP` | Near-straight context. |
| `spatial.sharp_angle_ratio_lt_60` | `KEEP` | Sharp-angle fraction; flow/awkward-aim candidate signal. |
| `spatial.direction_change_ratio_ge_90` | `KEEP` | Direction-change fraction; related to angle mean but not identical. |
| `spatial.net_displacement_ratio` | `KEEP` | Map-level path linearity; no official counterpart (OURS_MORE_GENERAL). |
| `spatial.x_range_norm` | `KEEP_AS_METADATA` | Playfield coverage, not a skill signal by itself. |
| `spatial.y_range_norm` | `KEEP_AS_METADATA` | Playfield coverage; highest outlier count (200 records) — keep for diagnostics. |

### Slider (28)

| Feature | Classification | Rationale |
| --- | --- | --- |
| `slider.slider_ratio` | `KEEP` | Composition measurement; also manifest proxy (r=1.0). |
| `slider.duration_ms_mean` | `KEEP` | Estimated duration (pixel length / (SM*100*SV) * beatLength); official travel time is more complete. |
| `slider.duration_ms_std` | `KEEP` | Duration variability. |
| `slider.duration_ms_p50` | `KEEP` | Robust duration. |
| `slider.duration_ms_p75` | `KEEP` | Long-slider tail. |
| `slider.duration_ms_p90` | `KEEP` | Long-slider tail. |
| `slider.duration_ms_p95` | `KEEP` | Long-slider tail. |
| `slider.duration_ms_max` | `KEEP` | Extreme slider duration. |
| `slider.duration_ms_min` | `KEEP` | Short/kickslider context. |
| `slider.velocity_px_per_s_mean` | `NEEDS_REVIEW` | By construction equals `SM*100*SV*1000/beatLength`; degenerate beat lengths produce 1e303 tails; largely redundant with SV/BPM context. |
| `slider.velocity_px_per_s_std` | `NEEDS_REVIEW` | Same degeneracy; std overflows to Infinity in QA stats. |
| `slider.velocity_px_per_s_p50` | `NEEDS_REVIEW` | Same degeneracy (median is stable, but family shares definition). |
| `slider.velocity_px_per_s_p75` | `NEEDS_REVIEW` | Extreme tail from degenerate timing. |
| `slider.velocity_px_per_s_p90` | `NEEDS_REVIEW` | Extreme tail from degenerate timing. |
| `slider.velocity_px_per_s_p95` | `NEEDS_REVIEW` | Extreme tail from degenerate timing. |
| `slider.velocity_px_per_s_max` | `NEEDS_REVIEW` | Max 8.24e303 from degenerate timing. |
| `slider.velocity_px_per_s_min` | `NEEDS_REVIEW` | Stable but family definition should be reviewed as a whole. |
| `slider.length_px_mean` | `KEEP` | Raw geometry; direct input to official travel distance. |
| `slider.length_px_std` | `KEEP` | Geometry variability; max 9.17e306 from pathological pixel lengths (finite, tagged). |
| `slider.length_px_p50` | `KEEP` | Robust length. |
| `slider.length_px_p75` | `KEEP` | Long-slider tail. |
| `slider.length_px_p90` | `KEEP` | Long-slider tail. |
| `slider.length_px_p95` | `KEEP` | Long-slider tail. |
| `slider.length_px_max` | `KEEP` | Extreme geometry. |
| `slider.length_px_min` | `KEEP` | Minimal-slider context. |
| `slider.repeats_total` | `KEEP` | Total repeat burden; official uses repeat bonus in travel distance. |
| `slider.repeats_max` | `KEEP` | Worst-case repeat slider. |
| `slider.to_circle_transition_count` | `KEEP` | Slider→circle transition frequency; relevant to flow/rhythm and official `LastObjectEndDeltaTime` semantics. |

### Section (8)

| Feature | Classification | Rationale |
| --- | --- | --- |
| `section.window_count` | `KEEP_AS_METADATA` | Duration proxy (r=0.994 with `duration_ms`); diagnostic only. |
| `section.density_per_s_mean` | `REDUNDANT_CANDIDATE` | r>0.99 with `temporal.density_objects_per_s` and `duration_weighted_density_per_s`. |
| `section.density_per_s_p95` | `KEEP` | Window-tail density; r=0.984 with window mean — tail still distinct. |
| `section.density_per_s_max` | `KEEP` | Peak window density; used by `wsp002`. |
| `section.duration_weighted_density_per_s` | `REDUNDANT_CANDIDATE` | Functional duplicate of `temporal.density_objects_per_s` (weighted window mean = object_count / covered duration; r=1.0 across the corpus). |
| `section.velocity_norm_per_s_p90` | `KEEP` | Window-level velocity tail; correlated with spatial velocity tails but adds window perspective. |
| `section.angle_deg_p90` | `KEEP` | Window-level angle tail; correlated with spatial angle p90/p95 but adds window perspective. |
| `section.peak_density_window_start_ms` | `KEEP_AS_METADATA` | Location of peak density, not magnitude; useful for late-map stamina analysis. |

### Difficulty context (6)

| Feature | Classification | Rationale |
| --- | --- | --- |
| `difficulty.AR` | `KEEP_AS_METADATA` | Context only; 8.4 % missing on old maps; AR~OD r=0.95. |
| `difficulty.OD` | `KEEP_AS_METADATA` | Context only; official uses it in aim/reading/speed scaling. |
| `difficulty.CS` | `KEEP_AS_METADATA` | Context only; needed if distances become CS-normalised. |
| `difficulty.HP` | `KEEP_AS_METADATA` | Context only; no difficulty-pipeline role in official osu!standard. |
| `difficulty.SliderMultiplier` | `KEEP_AS_METADATA` | Context; already baked into slider duration/velocity estimates. |
| `difficulty.SliderTickRate` | `KEEP_AS_METADATA` | Context for slider ticks; not yet used by any feature. |

## Definition issues found (no changes made)

1. **Distance unit is not uniform and not CS-normalised.** Coordinates are
   normalised by `x/512`, `y/384`, so horizontal and vertical units differ, and
   circle size is ignored. Official difficulty scales all distances by
   `50/radius`. This is the largest semantic gap for cross-CS comparability.
2. **No 25 ms delta cap.** Official caps `AdjustedDeltaTime` at 25 ms; local
   features consume raw deltas, so simultaneous objects yield `delta=0` and
   extreme interval ratios.
3. **Slider duration/velocity are estimates, not path simulations.** The local
   estimator is deterministic and useful, but it is not the official lazy
   travel path. `slider.velocity_px_per_s_*` degenerates to
   `SM*100*SV*1000/beatLength` and inherits pathological timing values.
4. **Angle is object-position only.** Official `Angle` is slider-aware and
   takes `min(angle, sliderAngle)`; local angles miss slider-tail geometry.
5. **`_burst_metrics` and dense-section features are the same computation.**
   `burst_count_250ms`/`dense_section_count` and
   `burst_longest_duration_ms_250ms`/`longest_dense_section_ms` are exact
   duplicates by construction; `duration_weighted_density_per_s` is a functional
   duplicate of `density_objects_per_s` (r=1.0; it collapses to object_count /
   covered duration, differing only when empty 5 s windows are omitted).
6. **Extreme finite values are real and tagged.** Degenerate timing/geometry
   produces values up to ~1e306. QA keeps them with provenance; any future
   transform must be explicit (e.g. documented winsorization or a
   `pathological_*` flag), never silent clipping.

## Recommended next contract (v0.2 proposal only, not implemented)

1. Keep all 104 features in v0.1; do not delete anything without a
   `feature_version` bump and regression suite.
2. In v0.2, consider merging exact duplicates and adding:
   - CS-normalised, uniform-scale distance family (`lazy` and `minimum` jump
     variants are strong candidates);
   - a documented 25 ms minimum-delta handling for velocity/ratio features;
   - slider lazy travel path signals (duration, distance, lazy end position);
   - per-object preempt/reaction-window and double-tap feasibility as
     reference signals;
   - window-level strain-like peaks only if the profiler decides to adopt
     difficulty-policy-adjacent signals (clearly labelled as reference).
3. Official difficulty outputs must stay out of the feature contract: they are
   tuned policy products (mod-aware, decay-weighted, human-balanced), not
   observable map measurements.
