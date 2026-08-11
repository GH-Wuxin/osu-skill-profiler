# Official Reference Signal Layer v0.1 - Contract

Status: **FINAL** (2026-08-11)

Reference contract version: `0.1.0`

This document defines every exposed `ref.ppy.*` field produced by
`ReferenceSignalExtractor`. All semantics are pinned to:

| Item | Value |
| --- | --- |
| Repository | `ppy/osu` |
| Commit | `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e` |
| Difficulty version | `20260706` (`OsuDifficultyCalculator.Version`) |
| Layer | B - Official Reference Signals |
| Classification | `OFFICIAL_REFERENCE` |

Every field is a **reference-only measurement of ppy/osu difficulty-tuning
policy**. It is never an observable primitive, never ground truth, never a
label, and never a final skill vector.

## 1. Supported scope

```text
SUPPORTED:
  osu!standard
  unmodded
  local/reference analysis only

UNSUPPORTED:
  mod-transformed reference semantics (HR/DT/HD/EZ/rate-adjusted/lazer mod
  parity)
  final star rating
  PP
  final difficulty aggregation
  player skill inference
```

## 2. Namespace and row identity

Rows are aligned to the `.osu` file order of `[HitObjects]`. Each row carries:

| Field | Type | Meaning |
| --- | --- | --- |
| `ref.original_index` | int | 0-based index in file order |
| `ref.time_sorted_index` | int | 0-based rank by `(start_time_ms, original_index)` |
| `ref.start_time_ms` | float | object start time in ms |
| `ref.object_type` | enum | `circle` / `slider` / `spinner` |
| `ref.provenance` | list | flags for unavailable / pathological / legacy semantics |

`ref.provenance` includes `no_difficulty_row` for the first raw object
(upstream never creates a difficulty row for raw object 0) and one
`ref_unavailable:<signal>` flag per signal that could not be evaluated on that
row. Geometry-blocked slider rows are propagated from the audited Layer A
guards (`path_blocked:*`, `slider_spans_exceeded:*`,
`slider_tick_count_exceeded`).

## 3. Exposed signals

### 3.1 `ref.ppy.snap_include_sliders`

- Type: float or `None`
- Unit: normalised px/ms (policy-scaled, dimensionless scale)
- Semantic: `SnapAimEvaluator.EvaluateDifficultyOf(current,
  withSliderTravelDistance=true)` - snap aim difficulty including lazy slider
  travel through previous sliders and the current slider travel bonus.
- Upstream: `osu.Game.Rulesets.Osu/Difficulty/Evaluators/Aim/SnapAimEvaluator.cs`
  (blob `a345b2aa5fb78e9afb8810ee522ee93f0a733909`), `EvaluateDifficultyOf`
- Slider involvement: previous slider lazy travel extends `currVelocity`;
  current slider adds `TravelDistance/TravelTime`; angle handling uses lazy
  cursor positions.
- Timing involvement: `AdjustedDeltaTime` (25 ms floor), high-BPM bonus,
  rhythm-change velocity penalty, 300-400 BPM acute-angle gating.
- Missing semantics: `None` for the first raw object, missing CS, or blocked
  slider geometry; `0.0` only where the upstream gate itself returns 0
  (`Index <= 1` on difficulty rows, spinner context).
- Pathological semantics: no silent clipping; upstream semantic clamps
  preserved; non-finite pathological finite inputs return `None` with
  `ref_unavailable:` provenance.
- Numeric safety: no NaN/Inf propagation.
- Model-input recommendation: not recommended as a raw model feature
  (`model_input_safe: false`); safe for exploratory analysis only.
- Ground truth: never.

### 3.2 `ref.ppy.snap_exclude_sliders`

- Type: float or `None`
- Unit: normalised px/ms (policy-scaled, dimensionless scale)
- Semantic: `SnapAimEvaluator.EvaluateDifficultyOf(current,
  withSliderTravelDistance=false)` - snap aim using start-to-start jump
  distances only.
- Upstream: same file/commit as 3.1, `EvaluateDifficultyOf`
- Slider involvement: slider travel ignored; slider-to-object transitions use
  raw jump geometry.
- Timing involvement: identical timing policy to 3.1.
- Missing / pathological / model-input semantics: same policy as 3.1.

### 3.3 `ref.ppy.agility`

- Type: float or `None`
- Unit: normalised px/ms (policy-scaled, dimensionless scale)
- Semantic: `AgilityEvaluator.EvaluateDifficultyOf(current)` - fast-aiming
  difficulty from (previous lazy travel + current lazy jump), capped at 120
  normalised px, over `AdjustedDeltaTime`, with small-circle and high-BPM
  bonuses.
- Upstream: `AgilityEvaluator.cs`
  (blob `bd5204faaf8d987fdd73027bc0ebf5628bd0f0db`), `EvaluateDifficultyOf`
- Slider involvement: previous slider lazy travel is added to the current lazy
  jump.
- Timing involvement: `AdjustedDeltaTime`, high-BPM bonus (0.2 base).
- Missing: first raw object or missing lazy jump; `0.0` for spinner current.

### 3.4 `ref.ppy.flow_include_sliders`

- Type: float or `None`
- Unit: normalised px/ms (policy-scaled, dimensionless scale)
- Semantic: `FlowAimEvaluator.EvaluateDifficultyOf(current,
  withSliderTravelDistance=true)` - flow aim including slider travel, raised
  to 1.45, gated by `Smootherstep(distance, 0, 50)`.
- Upstream: `FlowAimEvaluator.cs`
  (blob `cea98ff010f072e0bc16803b46fbb2ceba1f596a`), `EvaluateDifficultyOf`
- Slider involvement: previous slider lazy travel extends `currVelocity`;
  current slider adds travel velocity.
- Timing involvement: `AdjustedDeltaTime`, rhythm-change factor, angular
  velocity factor.
- Pathological note: on pathological finite slider inputs this field can reach
  extremely large finite values (up to ~1.6e17 on the real corpus). Values are
  provenance-tagged via `extreme_finite` reporting, never clipped, and should
  be treated as policy blow-up signals for human inspection.

### 3.5 `ref.ppy.flow_exclude_sliders`

- Same evaluator as 3.4 with `withSliderTravelDistance=false`.
- Slider involvement: no travel extension or current-slider travel bonus.
- Missing / pathological / model-input semantics: same policy as 3.4.

### 3.6 `ref.ppy.speed`

- Type: float or `None`
- Unit: 1/ms (policy-scaled, dimensionless scale)
- Semantic: `SpeedEvaluator.EvaluateDifficultyOf(current)` - tap-speed
  difficulty from `AdjustedDeltaTime`, OD-window-capped strain time, 200+ BPM
  bonus, high-BPM bonus and double-tap feasibility penalty.
- Upstream: `SpeedEvaluator.cs`
  (blob `7caa03a0b9c662c032c813e49c4372bb48ab132d`), `EvaluateDifficultyOf`
- Slider involvement: spinner current returns 0; sliders otherwise use the
  same tap-time policy.
- Timing involvement: `AdjustedDeltaTime`, hit window (OD), high-BPM bonus
  (0.3 base), double-tap feasibility.
- Missing: first raw object or missing OD; `0.0` for spinner current.

### 3.7 `ref.ppy.rhythm`

- Type: float or `None`
- Unit: dimensionless multiplier (>= 1)
- Semantic: `RhythmEvaluator.EvaluateDifficultyOf(current)` - rhythm-complexity
  multiplier from island structure over the previous 5 s / 32-object window,
  delta ratios, slider-aware ratios, double-tap nerf and occurrence nerfs.
- Upstream: `RhythmEvaluator.cs`
  (blob `498b130991e3dfadbe8ff11c349d7079c27a7ffb`), `EvaluateDifficultyOf`
- Slider involvement: slider-aware minimum-jump and last-object-end ratios;
  bpm-change-into/from-slider nerfs.
- Timing involvement: raw `DeltaTime` comparisons, hit-window epsilon, 5 s
  history window, island deltas.
- Missing: first raw object or missing OD on evaluated rows; `0.0` for spinner
  current.

### 3.8 `ref.ppy.speed_with_rhythm`

- Type: float or `None`
- Unit: policy product (dimensionless scale)
- Semantic: `SpeedEvaluator` value x `RhythmEvaluator` value for the same
  object. This is a private reference-only decomposition mirroring the two
  evaluators that the upstream `Speed` skill combines under harmonic strain
  decay. It is **not** the official strain value: it excludes the 1.16 skill
  multiplier and strain decay.
- Upstream: `Speed.cs`
  (blob `f8ab313cb76a0ff6f73ef84e5db5175adb7ef8ce`) /
  `SpeedEvaluator.cs` / `RhythmEvaluator.cs`; `ObjectDifficultyOf` decomposed.
- Missing: `None` whenever either component is unavailable; `0.0` for spinner
  current.

### 3.9 `ref.ppy.reading`

- Type: float or `None`
- Unit: dimensionless policy value
- Semantic: `ReadingEvaluator.EvaluateDifficultyOf(current, hidden=false)` -
  unmodded reading difficulty from visible-object density (past + future),
  constant-angle repetition nerf, preempt difficulty and high-BPM bonus,
  combined with a 1.5-norm.
- Upstream: `ReadingEvaluator.cs`
  (blob `99826ed4170b1ec73fd7b5311f721298eaac8db5`), `EvaluateDifficultyOf`
  (hidden=false only).
- Slider involvement: no slider-specific branch; sliders participate via start
  times, lazy jumps and preempt.
- Timing involvement: preempt (AR), 3 s reading window, 2 s angle window, time
  nerf, high-BPM bonus (0.8 base).
- Missing: first raw object, missing AR, or missing lazy-jump inputs; `0.0`
  only where the upstream gate returns 0.

## 4. Aggregation policy

Fixed-time 5 s segment summaries are descriptive statistics only
(`count`, `mean`, `median`, `p90`, `p95`, `max`) and never form a final
segment difficulty scalar. `mean` uses an overflow-safe scaled mean; all other
statistics are standard empirical quantiles over finite member values.

Segment index fields (`start_idx` / `end_idx`) refer to positions in the
**time-sorted** row order used by `segment_reference_signals`, not to
`ref.original_index`. Joins back to file order must use
`ref.time_sorted_index`.

## 5. What this layer is NOT

- Not `AimDifficulty`, `SpeedDifficulty`, `ReadingDifficulty`, star rating or
  PP.
- Not a learned skill vector; no taxonomy inference is performed by this
  layer.
- Not ground truth for any human skill name.
- Not a replacement for Layer A observable local signals.

## 6. Explicit field-level flags

Every field in `REFERENCE_SCHEMA` carries:

- `classification: OFFICIAL_REFERENCE`
- `reference_only: true`
- `never_ground_truth: true`
- `model_input_safe: false` (exploratory use only)
- `exploratory_safe: true`

## 7. Revision pinning

- `UPSTREAM_REPOSITORY = ppy/osu`
- `UPSTREAM_COMMIT = b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`
- `UPSTREAM_DIFFICULTY_VERSION = 20260706`
- `REFERENCE_VERSION = 0.1.0`

Any future update must re-audit the pinned upstream files, record new blob
SHAs in `docs/PPY_DIFFICULTY_REFERENCE_AUDIT.md`, bump the reference version,
and re-run the full golden + corpus gates before changing exposed semantics.
