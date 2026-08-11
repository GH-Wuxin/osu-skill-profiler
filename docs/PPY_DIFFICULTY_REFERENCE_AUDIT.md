# ppy/osu Difficulty Reference Audit

Status: **REFERENCE AUDIT (read-only)** — no feature was added, removed, renamed,
redefined, or deleted as part of this audit. No taxonomy was frozen. No model was
trained. No WuxinBot integration was made.

Date: 2026-08-10

## Scope

The goal is **not** to clone star rating. The goal is to understand how ppy/osu
extracts gameplay-meaningful *local signals* from osu!standard hit objects before
aggregating them into star rating, then to audit the current profiler
preprocessing, the 104 deterministic features, and the provisional taxonomy
against that reference.

## Method and evidence

All upstream statements in this document were read from actual source files at a
pinned commit, not from memory or from third-party summaries.

- Upstream repository: `https://github.com/ppy/osu`
- Pinned commit: `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`
  (master, 2026-08-10 06:51Z, "Fix legacy bar hit error meter origin...")
- Osu difficulty version at this commit: `OsuDifficultyCalculator.Version == 20260706`
- Shared difficulty framework at this commit lives physically under
  `osu.Game/Rulesets/Difficulty/` (namespace `osu.Game.Rulesets.Difficulty`),
  not in a separate top-level project.
- All Osu ruleset difficulty files were fetched by blob SHA from the pinned
  commit via the GitHub API and read in full. A DeepWiki snapshot was used only
  as background; wherever it disagreed or was incomplete, actual source won.

Local profiler state audited against:

- `docs/FEATURES.md`, `docs/TAXONOMY_V0.md`, `docs/ARCHITECTURE.md`
- `src/osu_skill_profiler/parser/`, `features/`, `segments/`, `weak_supervision/`, `taxonomy/`
- `training/datasets/feature_qa/feature_stats_full.json`,
  `feature_correlations.json`, `segment_stats.json`, `FEATURE_QA_REPORT.md`

---

## Phase 1 — Upstream inventory

### 1.1 Shared difficulty framework (`osu.Game/Rulesets/Difficulty/`)

| Source file | Class / function | Input | Output | Mathematical / semantic purpose |
| --- | --- | --- | --- | --- |
| `DifficultyCalculator.cs` | `DifficultyCalculator.Calculate(mods)` | playable beatmap + mods | `DifficultyAttributes` | Orchestrates the whole pipeline: playable-beatmap preprocessing, `CreateDifficultyHitObjects`, `CreateSkills`, per-object `skill.Process(...)`, final attribute creation. Applies an internal 10 s cancellation fallback. |
| `DifficultyCalculator.cs` | `SortObjects` | difficulty objects | sorted difficulty objects | Orders difficulty objects by `BaseObject.StartTime` before processing. |
| `Preprocessing/DifficultyHitObject.cs` | `DifficultyHitObject` | raw `HitObject`, previous raw object, clock rate, object list, index | rate-adjusted `DeltaTime` / `StartTime` / `EndTime`, `HitWindowGreat`, `Previous(n)` / `Next(n)` | Base per-object wrapper. All timing is clock-rate adjusted; hit windows fall back to nested objects (e.g. slider head). |
| `Skills/Skill.cs` | `Skill` | difficulty object | per-object difficulty list | Bare-minimum skill contract: `Process` stores per-object difficulties; `DifficultyValue()` defines map-level aggregation. |
| `Skills/StrainSkill.cs` | `StrainSkill` | difficulty objects | strain peaks | Classic 400 ms strain sections; section peak seeded with decaying previous strain; map difficulty = decay-weighted (`0.9^n`) sum of top peaks. |
| `Skills/VariableLengthStrainSkill.cs` | `VariableLengthStrainSkill` | difficulty objects | variable-length strain peaks | Newer aggregation: one strain peak per high-value object; peak section length varies; queued strains fill gaps; only enough history to preserve ~99.999 % of difficulty is kept. Used by Aim. |
| `Skills/StrainDecaySkill.cs` | `StrainDecaySkill` | difficulty objects | strain values | Generic exponential strain decay (`base^(ms/1000)`) + multiplier accumulation. |
| `Skills/HarmonicSkill.cs` | `HarmonicSkill` | per-object difficulties | difficulty value + `ObjectWeightSum` | Sorted per-object difficulties aggregated with harmonic weights `(1 + H/(1+i)) / (i^d + 1 + H/(1+i))`; `DifficultyToPerformance(d) = 4*d^3`. Used by Speed and Reading. |
| `Utils/DiffUtils.cs` | `Pow / Norm / Logistic / Smoothstep / Smootherstep / ReverseLerp / SmoothstepBellCurve / MillisecondsToBPM` | scalars | scalars | Shared math primitives used by every evaluator. |

### 1.2 Osu preprocessing (`osu.Game.Rulesets.Osu/Difficulty/Preprocessing/`)

`OsuDifficultyHitObject` (derives from `DifficultyHitObject`):

| Signal | Formula / source | Purpose |
| --- | --- | --- |
| `AdjustedDeltaTime` | `max(DeltaTime, 25ms)` | Prevent simultaneous/near-simultaneous objects from breaking difficulty. |
| `LastObjectEndDeltaTime` | `max(StartTime - previous.EndTime, 25ms)` | Real time between previous object end and current start (slider tail aware). |
| `Preempt` | `BaseObject.TimePreempt / ClockRate` | Reaction window used by Reading. |
| `JumpDistance` | `|last.StackedPosition - current.StackedPosition| * (50 / radius)` | CS-normalised start-to-start jump. |
| `LazyJumpDistance` | same, but from previous *lazy end cursor position* | Jump after minimal-effort slider following. |
| `MinimumJumpDistance` | `min(LazyJumpDistance - (max_slider_radius - assumed_slider_radius), tailJumpDistance - max_slider_radius)`, floored at 0 | Anti-flow vs flow natural path selection. |
| `MinimumJumpTime` | `max(AdjustedDeltaTime - previous lazy travel time, 25ms)` | Time budget for the jump after slider travel. |
| `TravelDistance` / `TravelTime` | slider lazy travel distance with repeat bonus `max(1, repeats^0.3)`; time capped at 25 ms | Slider body movement contribution. |
| `LazyEndPosition` / `LazyTravelDistance` / `LazyTravelTime` | simulated lazy cursor following slider nested objects (follow-circle radius 90 px, repeat threshold 50 px) | Minimal-movement slider path. |
| `Angle` | `atan2(det, dot)` of (prev2, prev, curr); then `min(angle, sliderAngle)` | Turn difficulty; slider-aware via second-last nested object. |
| `NormalisedVectorAngle` | `atan2(|dy|, |dx|)` | Direction-of-motion angle used for repetition nerfs. |
| `SmallCircleBonus` | `max(1, 1 + (30 - radius)/70)` | Selective CS bonus. |
| `OverallDifficulty` | `(79.5 - HitWindowGreat/2) / 6` | OD from raw hit window (used in aim/reading scaling). |
| `OpacityAt(time, hidden)` | fade-in/fade-out model | Visibility used by Reading/Flashlight. |
| `CalculateDoubleTapFeasibility(next)` | based on delta-time ratio, hit window, lazy jump distance | Whether two objects can be double-tapped; used by Speed and Rhythm nerfs. |

### 1.3 Osu skills (`.../Difficulty/Skills/`)

| Skill | Base class | Decay / aggregation | Evaluators | Notes |
| --- | --- | --- | --- | --- |
| `Aim` (two instances: include-sliders and exclude-sliders) | `VariableLengthStrainSkill` | strain decay `0.2^(ms/1000)`; reduced top-strain peaks (first 4 s scaled down to baseline 0.727) | `SnapAimEvaluator` (×70.9), `AgilityEvaluator` (×2.35), `FlowAimEvaluator` (×242.0) | Snap and agility combined with p-norm 1.2, then mixed with flow via logistic snap/flow probability; OD scaling `0.985 + OD^2/4000`; slider-strain list for slider count attributes. |
| `Speed` | `HarmonicSkill` (H=20, exponent 0.9) | strain decay `0.3^(ms/1000)`, skill multiplier 1.16 | `SpeedEvaluator` × `RhythmEvaluator` | Per-object difficulty = speed strain × rhythm multiplier; slider strains tracked separately. |
| `Reading` | `HarmonicSkill` (defaults) | strain decay `0.8^(ms/1000)`, skill multiplier 2.5 | `ReadingEvaluator` | First 60 s objects progressively downweighted (partial-memorisation assumption); OD scaling `0.825 + OD^2.2/1125`. |
| `Flashlight` | `StrainSkill` | decay `0.15^(ms/1000)`, multiplier 0.058 | `FlashlightEvaluator` | Only created when FL mod present; map-length bonus; `DifficultyToPerformance(d) = 25*d^2`. |

### 1.4 Osu evaluators (`.../Difficulty/Evaluators/`)

| Evaluator | Input | Output | Core semantics |
| --- | --- | --- | --- |
| `SnapAimEvaluator` | OsuDifficultyHitObject window | snap difficulty per object | velocity (`lazyJump/AdjustedDeltaTime`, slider-extended), acute/wide angle bonuses, wiggle bonus, angle-repetition nerf, velocity-change bonus with rhythm-change penalty, slider velocity bonus, `SmallCircleBonus`, high-BPM bonus `1/(1 - 0.03^(ms/1000)^0.65)`. |
| `AgilityEvaluator` | OsuDifficultyHitObject | agility difficulty per object | capped total movement `min(travel + lazyJump, 1.2 * diameter)` scaled by `1000 / AdjustedDeltaTime`; `SmallCircleBonus^1.5`; high-BPM bonus `1/(1 - 0.2^(ms/1000))`. |
| `FlowAimEvaluator` | OsuDifficultyHitObject window | flow difficulty per object | velocity base × CS bonus × rhythm-change factor × angular-velocity factor; overlap-weighting; acute-angle add-on; velocity-change bonus; slider velocity; result `^1.45`; low-spacing smootherstep gate. |
| `SpeedEvaluator` | OsuDifficultyHitObject | speed difficulty per object | `(1 + speedBonus) * 1000 / strainTime`, where strainTime is OD-window clamped (`/clamp((strainTime/HitWindowGreat)/0.93, 0.92, 1)`); >200 BPM quadratic bonus; high-BPM bonus `1/(1 - 0.3^(ms/1000))`; double-tap feasibility penalty. |
| `RhythmEvaluator` | OsuDifficultyHitObject + up to 5 s / 32-object history | rhythm multiplier ≥ 1 | Island model over delta times; fractional part of delta-ratio penalised (multiples of each other reduced); island repetition/occurrence nerfs; slider lazy/real end deltas; double-tap nerf; returns `sqrt(4 + rhythmComplexitySum * 0.95) / 2`. |
| `ReadingEvaluator` | OsuDifficultyHitObject ± 3 s visibility window | reading difficulty per object | p-norm(1.5) of preempt difficulty, hidden difficulty, note-density difficulty; opacity-weighted past/future visible-object density; constant-angle nerf factor; high-BPM bonus `1/(1 - 0.8^(ms/1000))`. |
| `FlashlightEvaluator` | OsuDifficultyHitObject + previous 10 objects | flashlight difficulty per object | CS-scaled (52/radius) backward jump distances with opacity and stack nerfs, angle repetition nerf, slider velocity/length bonus. |

### 1.5 Final aggregation (`OsuDifficultyCalculator.cs`, `OsuPerformanceCalculator.cs`)

- Skills instantiated: `Aim(true)`, `Aim(false)`, `Speed`, `Reading`, plus `Flashlight` only with FL mod.
- Aim rating: `aimDifficultyValue^0.63 * 0.02275`.
- Speed / Reading / Flashlight rating: `sqrt(difficultyValue) * 0.0675`.
- Performance conversion: aim via `OsuPerformanceCalculator.DifficultyToPerformance` (`4*d^3`), speed/reading via `HarmonicSkill.DifficultyToPerformance` (`4*d^3`), flashlight via `Flashlight.DifficultyToPerformance` (`25*d^2`).
- Cognition: `SumCognitionDifficulty(reading, flashlight)` with flashlight nerf `clamp(flashlight/reading, 0.25, 1)`.
- Base performance: `DiffUtils.Norm(1.1, aimPerf, speedPerf, cognitionPerf)`.
- Star rating: `cbrt(basePerformance * 1.12)` (`PERFORMANCE_BASE_MULTIPLIER = 1.12`, `PERFORMANCE_NORM_EXPONENT = 1.1`).
- Attributes also expose difficult-strain counts, top-weighted slider factors, slider factor, speed note count, and legacy score metadata.

---

## Phase 2 — Concept mapping (official → profiler)

Classification legend:

- `EQUIVALENT` — same observable quantity, same semantic role.
- `PARTIAL_OVERLAP` — related quantity but different definition/scope.
- `OFFICIAL_MORE_COMPLETE` — profiler has a weaker or no counterpart for a richer official signal.
- `OURS_MORE_GENERAL` — profiler's measurement is broader but less precise.
- `REFERENCE_ONLY` — official signal is not appropriate as a deterministic feature in the profiler.
- `NO_EQUIVALENT` — no local counterpart.

| Official concept | Local profiler counterpart | Classification | Evidence / reasoning |
| --- | --- | --- | --- |
| CS-normalised distance (`JumpDistance` / `LazyJumpDistance` / `MinimumJumpDistance`, scale `50/radius`) | `spatial.distance_norm_*` on raw 512×384 normalised coordinates | `PARTIAL_OVERLAP` | Both measure inter-object spacing, but official removes CS and playfield-scale effects; local values mix x/512 and y/384 scales and keep raw CS in `difficulty.CS` only. |
| Slider lazy/tail movement (`LazyEndPosition`, `LazyTravelDistance/Time`, `MinimumJumpTime`, `TravelDistance/Time`) | `slider.duration_ms_*`, `slider.velocity_px_per_s_*`, `slider.length_px_*` | `OFFICIAL_MORE_COMPLETE` | Local estimates duration from `pixel_length / (SliderMultiplier*100*SV) * beatLength`; official simulates the actual nested-object path and follow-circle movement. |
| Angle at object (`Angle`, `NormalisedVectorAngle`, slider-aware angle) | `spatial.angle_deg_*` | `PARTIAL_OVERLAP` | Both are turn angles, but local uses raw object positions only and never slider tail / lazy end positions; official takes `min(angle, sliderAngle)`. |
| Minimum delta cap 25 ms | none (raw deltas; velocity skipped when `delta <= 0`) | `OFFICIAL_MORE_COMPLETE` | Official caps `AdjustedDeltaTime` at 25 ms; local keeps raw deltas, so simultaneous objects have `delta=0` and extreme ratios. |
| `SmallCircleBonus` | `difficulty.CS` raw value only | `REFERENCE_ONLY` | Radius-based bonus is a tuned difficulty constant, not an observable; CS as context is the correct local analogue. |
| `Preempt` / AR reaction window | `difficulty.AR` raw value only | `REFERENCE_ONLY` | Official computes per-object reaction difficulty; local keeps AR as context (8.4 % missing on old maps). |
| Snap aim (velocity, angle bonuses, repetition nerf, velocity change) | `spatial.velocity_*`, `spatial.angle_*`, `spatial.sharp_angle_ratio_lt_60`, `spatial.direction_change_ratio_ge_90` | `PARTIAL_OVERLAP` | Same raw ingredients, but local has no repetition window, no acute/wide/wiggle decomposition, no slider-extension of velocity. |
| Agility (capped distance / time) | `spatial.acceleration_norm_per_s2_*` | `PARTIAL_OVERLAP` | Local acceleration is a discrete velocity derivative; official uses capped `(travel+lazyJump)/deltaTime` with a 1.2-diameter cap. They are different quantities with related intent. |
| Flow aim (angular velocity, overlap factors, spacing gate) | `flow_aim` taxonomy axis + angle/velocity features | `PARTIAL_OVERLAP` | Taxonomy axis exists, but no local feature implements angular velocity or triple-overlap weighting. |
| Speed (strainTime, >200 BPM bonus, OD-window clamp, double-tap feasibility) | `temporal.bpm_*`, `temporal.delta_time_ms_*`, `temporal.burst_*`, `temporal.density_*` | `PARTIAL_OVERLAP` | Local has raw rhythm-rate signals; no OD-window clamp and no double-tap feasibility. |
| Rhythm islands (delta islands, ratios, occurrence nerfs, slider-aware deltas) | `temporal.rhythm_entropy_bits`, `temporal.interval_diversity`, `temporal.interval_ratio_mean` | `PARTIAL_OVERLAP` | Local uses quantized entropy/diversity; official uses exact island structure over a 5 s / 32-object history. |
| Reading (visible-object density, opacity, constant-angle nerf, preempt difficulty, HD) | `difficulty.AR`, `section.density_*`, `spatial.angle_*` | `OFFICIAL_MORE_COMPLETE` | Local has no per-object visibility window, no opacity model, no preempt-derived difficulty. |
| Flashlight (backward window, opacity, stacks) | none | `REFERENCE_ONLY` | Mod-specific; not a target for unmodded map profiling. |
| Strain sections (400 ms fixed; variable-length variant) and decay-weighted top aggregation | `segments/fixed_time.py` (5 s windows) + `section.*` + segment aggregation | `PARTIAL_OVERLAP` | Official sections are 400 ms with decaying initial strain and top-weighting; local windows are 5 s descriptive aggregates (mean/p90/max) without strain state. |
| Harmonic per-object weighting (`HarmonicSkill`) | none (map-level descriptive stats only) | `NO_EQUIVALENT` | Profiler intentionally does not produce a single scalar skill rating. |
| Star rating / difficulty value | none | `NO_EQUIVALENT` | Out of scope by design; official star rating is a tuned product, not ground truth. |

---

## Phase 3 — Feature audit (summary)

The full per-feature review (all 104 features, 18 high-correlation pairs, 8 proxy
relationships, extreme-value and missingness findings) is in
[`FEATURE_CONTRACT_REVIEW_V0.md`](FEATURE_CONTRACT_REVIEW_V0.md).

Key conclusions:

1. All 104 features are deterministic, JSON-safe, and stable across 126,509 maps
   (0 NaN/Inf, 0 missing > 50 %).
2. 18 feature pairs have `|r| > 0.98` on the 20k correlation subset; three pairs
   are exact duplicates **by construction**:
   - `temporal.burst_count_250ms` ≡ `temporal.dense_section_count`
   - `temporal.burst_longest_duration_ms_250ms` ≡ `temporal.longest_dense_section_ms`
   - `section.duration_weighted_density_per_s` ≡ `temporal.density_objects_per_s`
     (functional duplicate, r=1.0: weighted window mean collapses to
     object_count / covered duration)
3. Several measurements diverge from the official semantics in ways that matter
   for cross-CS and cross-era comparability (distance normalisation, missing
   25 ms cap, slider duration estimation, angle definition).
4. No feature should be deleted or redefined in this phase; changes belong to a
   future feature-contract bump (`feature_version`), with regression tests.

---

## Phase 4 — Local-signal opportunities

Official intermediate quantities that are compressed away by star-rating
aggregation but are valuable as per-object / per-segment signals:

| Official intermediate | Local suitability | Notes |
| --- | --- | --- |
| `AdjustedDeltaTime` / `MinimumJumpTime` / `LastObjectEndDeltaTime` | deterministic feature | Cheap, high-value timing signals; 25 ms cap prevents degenerate ratios. |
| CS-normalised `JumpDistance` / `LazyJumpDistance` / `MinimumJumpDistance` | deterministic feature | Best single upgrade for spatial comparability; keep raw distance too if needed. |
| `TravelDistance` / `TravelTime` / lazy slider path | deterministic feature / taxonomy evidence | Requires slider path simulation; directly strengthens `slider_complexity` and `flow_aim` evidence. |
| `Angle` / `NormalisedVectorAngle` (slider-aware) | deterministic feature | Stronger than raw object-position angle for `awkward_aim` / repetition signals. |
| Snap sub-signals (acute/wide/wiggle angle bonuses, velocity-change bonus, angle repetition) | deterministic feature candidates | Each is a measurable local pattern; the final snap *value* itself is a tuned difficulty constant. |
| Agility capped-distance/time | deterministic feature candidate | Cleaner than discrete acceleration for "fast aiming" intent. |
| Flow angular velocity + overlap factor | deterministic feature candidate | Direct evidence for `flow_aim`; no need to copy final flow *rating*. |
| Speed strainTime + OD-window clamp + double-tap feasibility | deterministic feature / weak supervision | Direct evidence for `speed`, `burst`, `stream`; double-tap feasibility is a strong reference signal. |
| Rhythm islands (delta, counts, occurrences, ratio fractional part) | deterministic feature / weak supervision | Direct evidence for `finger_control` / `rhythm_complexity`; entropy is a coarse proxy. |
| Reading visible density, opacity, preempt difficulty, constant-angle nerf | deterministic feature / taxonomy evidence | Direct evidence for `reading`; requires the visibility window model, not AR alone. |
| Flashlight backward-window distances | not suitable for unmodded profiling | Mod-specific; keep as `REFERENCE_ONLY`. |
| Strain peaks / decay-weighted top aggregation / harmonic object weights | official reference signal only | These encode difficulty *policy* (top-weighted, decaying), not observable map properties; useful for benchmarking, not as features. |

Design rules for future use:

- Official difficulty values (aim/speed/reading/star rating) are **not ground
  truth** for skill labels. They are tuned, mod-aware products of many constants
  and human balancing decisions. They may be used as *benchmark/reference*, never
  as a training target for skill profiling.
- `tech` is **not** an official atomic skill. Tech-like difficulty should be
  represented as combinations of observable signals (awkward angles, rhythm
  irregularity, finger-control patterns, flow) as the provisional taxonomy
  already states (`PROVISIONAL_CONVENIENCE_ONLY`).
- Per-object intermediates should be kept as **local signals** (per-object /
  per-segment), not collapsed into a single scalar, so downstream models and
  weak-supervision rules can consume the distribution.

---

## Phase 5 — Licensing / design

### Licensing

- ppy/osu is MIT-licensed (see `LICENCE` at repo root, copyright ppy Pty Ltd).
- If algorithms are **re-implemented** from the audit (formulas, semantics),
  no code copying occurs and no license obligation is triggered, but attribution
  in the feature contract is recommended.
- If code is **ported** (e.g. OsuDifficultyHitObject lazy-slider simulation),
  the MIT copyright notice must be preserved with the ported file(s), and the
  project should keep a `NOTICE` entry naming the upstream repository and commit.
- Do not copy the code wholesale into the feature extractor without a vendor
  boundary; the profiler's feature contract is intentionally independent from
  osu!'s difficulty policy.

### Revision pinning

Any future adoption of upstream semantics must pin all of:

1. Upstream commit: `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`
2. Difficulty version: `20260706` (`OsuDifficultyCalculator.Version`)
3. File-level blob SHAs (recorded in the appendix below or in a `third_party/`
   manifest if files are vendored)
4. A local `feature_version` bump and golden-value regression tests derived from
   the pinned commit

Recommended layout if vendoring becomes necessary:

```text
third_party/ppy_osu/
  LICENCE
  README.md          # upstream commit, date, diffcalc version
  osu.Game.Rulesets.Osu/Difficulty/...
  osu.Game/Rulesets/Difficulty/...
```

Upstream master moves fast; never consume `master` without pinning. The audit
itself is only valid for the commit and version above.

---

## Appendix — Upstream files read (blob SHAs at pinned commit)

### Osu ruleset

| File | Blob SHA |
| --- | --- |
| `osu.Game.Rulesets.Osu/Difficulty/OsuDifficultyCalculator.cs` | `eb7f00f2be6d1b91eeac6508731e500e6ef8533c` |
| `osu.Game.Rulesets.Osu/Difficulty/OsuDifficultyAttributes.cs` | `bfbacd0a864bb76d1bcb9f9040a520a1467a5448` |
| `osu.Game.Rulesets.Osu/Difficulty/Preprocessing/OsuDifficultyHitObject.cs` | `ced184299bf89ea796c513987bb092da105c650a` |
| `osu.Game.Rulesets.Osu/Difficulty/Skills/Aim.cs` | `30a20d2827d534282c4b90f9407374949737a690` |
| `osu.Game.Rulesets.Osu/Difficulty/Skills/Speed.cs` | `f8ab313cb76a0ff6f73ef84e5db5175adb7ef8ce` |
| `osu.Game.Rulesets.Osu/Difficulty/Skills/Reading.cs` | `99190a0220f5bab8f1a9471de47bec34302dca9e` |
| `osu.Game.Rulesets.Osu/Difficulty/Skills/Flashlight.cs` | `85666881ad70165d64e3b0212c2f7ed5a58d204d` |
| `osu.Game.Rulesets.Osu/Difficulty/Evaluators/Aim/SnapAimEvaluator.cs` | `a345b2aa5fb78e9afb8810ee522ee93f0a733909` |
| `osu.Game.Rulesets.Osu/Difficulty/Evaluators/Aim/FlowAimEvaluator.cs` | `cea98ff010f072e0bc16803b46fbb2ceba1f596a` |
| `osu.Game.Rulesets.Osu/Difficulty/Evaluators/Aim/AgilityEvaluator.cs` | `bd5204faaf8d987fdd73027bc0ebf5628bd0f0db` |
| `osu.Game.Rulesets.Osu/Difficulty/Evaluators/Speed/SpeedEvaluator.cs` | `7caa03a0b9c662c032c813e49c4372bb48ab132d` |
| `osu.Game.Rulesets.Osu/Difficulty/Evaluators/Speed/RhythmEvaluator.cs` | `498b130991e3dfadbe8ff11c349d7079c27a7ffb` |
| `osu.Game.Rulesets.Osu/Difficulty/Evaluators/ReadingEvaluator.cs` | `99826ed4170b1ec73fd7b5311f721298eaac8db5` |
| `osu.Game.Rulesets.Osu/Difficulty/Evaluators/FlashlightEvaluator.cs` | `a6d13be579ecab18ffd2720c6399c514452f667e` |

### Shared framework (`osu.Game/Rulesets/Difficulty/`)

| File | Blob SHA |
| --- | --- |
| `DifficultyCalculator.cs` | `bd7f3c2d6b55e012a82f5b01a3426858c9c98043` |
| `DifficultyAttributes.cs` | `c98e2137ac1091afa5b4af5b4a780eba67f02e46` |
| `Preprocessing/DifficultyHitObject.cs` | `8cacf582e5c585202b79395c9fedbeec186f00c8` |
| `Skills/Skill.cs` | `cf45104c942c39cf1b66c7ab7ab6ae4567868c79` |
| `Skills/StrainSkill.cs` | `269888ebd7ede4fd7b4b9e12a4e247c31806acc8` |
| `Skills/StrainDecaySkill.cs` | `431d2faba2ed0a5a173733d10443c7b27851eb6e` |
| `Skills/VariableLengthStrainSkill.cs` | `30b55ae68afecbf0529637325337004dba4984e5` |
| `Skills/HarmonicSkill.cs` | `060a0024e7e9ca5ecca53350424002b67b6693db` |
| `Utils/DiffUtils.cs` | `4548e0a18f8161101b9da356e54e4c0ff3f02600` |
