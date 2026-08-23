# SKILL_PROFILER_PRIOR_ART_AND_MVP_DESIGN_V01

Status: **DESIGN COMPLETE — EXPERIMENTAL MVP DESIGN, NOT PRODUCTION, NOT FINAL MODEL**

Evidence labels used throughout:

- `SOURCE_CONFIRMED` — source document/repository directly inspected
- `CODE_CONFIRMED` — source code directly inspected and formula quoted
- `PROJECT_DATA_CONFIRMED` — local osu-skill-profiler artifact verified
- `HUMAN_SMALL_N` — existing small human pairwise evidence
- `PRIOR_ART_CONSENSUS` — same construct appears independently in multiple projects
- `DESIGN_INFERENCE` — our inference from prior art/local data
- `HEURISTIC` — explicit design heuristic, not calibrated
- `UNRESOLVED` — evidence insufficient

No conclusion below silently upgrades a `DESIGN_INFERENCE` into a fact.

---

## 1. Executive summary

Prior art splits into three layers that must not be confused:

- **MAP DEMAND** — what the beatmap requires;
- **PLAYER PERFORMANCE** — how a player performed on one map;
- **PLAYER SKILL** — latent ability inferred across many performances.

The strongest beatmap-only prior art is ppy/osu difficulty evaluators and
oppai/rosu-pp strain implementations. The strongest standalone skill taxonomy
with inspectable source is Kert/osuSkills. Both map cleanly onto our existing
Feature 0.2 / Local Signal 0.3 fields, so a deterministic **Map Demand MVP
V0.1** is implementable now.

For the player layers, the clearest community prior art is Bathbot
(score-component aggregation), osu-mlpp (score-population calibration),
abraker95/osu-Replay-Analyzer and osu-aim-analyzer (tap-ms / aim-px replay
error). osuSkills is the cautionary layer-confusion case: map-only input
labeled as player skill, with a public reading stub.

Proposed MVP taxonomy (6 axes): **aim, precision, speed, stamina, rhythm,
reading**. `finger_control`, `accuracy`, `consistency`,
`memory/flashlight`, standalone `slider_control`, and `tech` are deferred.
PATH and TIME remain human-validated sub-constructs: PATH maps to slider-aware
aim diagnostics; TIME is `UNRESOLVED` between stamina and a future
slider-control axis, and does not become a first-level axis.

**Status:**

```text
RESEARCH / ARCHITECTURE:      READY
CORRECTED ALGORITHM SPEC:     READY
EXPERIMENTAL IMPLEMENTATION:  QA_PASS_WITH_RISKS
QA VERDICT:                  MAP_DEMAND_MVP_V01_QA_PASS_WITH_RISKS
```

Not claimed: `PRODUCTION_READY`, `PLAYER_SKILL_VALIDATED`,
`HUMAN_CALIBRATED`. No final `READY_FOR_MAP_DEMAND_MVP_V01` verdict without a
QA result.

---

## 2. Prior-art source table

| Project | Source | License | Maintenance | Layer | Evidence |
|---|---|---|---|---|---|
| ppy/osu difficulty/performance (pinned `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`) | <https://github.com/ppy/osu> | MIT | active | map demand + player performance | CODE_CONFIRMED |
| oppai-ng / oppai | <https://github.com/Francesco149/oppai-ng> (single-file oppai.c) | Unlicense | maintenance low, widely forked | map demand + pp | CODE_CONFIRMED |
| rosu-pp | <https://github.com/MaxOhn/rosu-pp> | MIT | active; main tracks pre-20260706 evaluators | map demand + pp | CODE_CONFIRMED |
| Kert/osuSkills | <https://github.com/Kert/osuSkills> | **no license file** | low; last push 2026; public `reading` is a stub | map demand mislabeled as player skill | CODE_CONFIRMED, REFERENCE_ONLY |
| Bathbot osu! cards | <https://github.com/MaxOhn/Bathbot> | ISC | active | player skill from top-score pp components | CODE_CONFIRMED |
| abraker95/osu-Replay-Analyzer | <https://github.com/abraker95/osu-Replay-Analyzer> | MIT | dormant/WIP | map demand + replay performance, explicitly separated | CODE_CONFIRMED |
| osu-aim-analyzer | <https://github.com/rgbeing/osu-aim-analyzer> | GPL-3.0 | dormant | replay aim-error decomposition | CODE_CONFIRMED |
| osu-trainer | <https://github.com/FunOrange/osu-trainer> | no license (uses GPL-3.0 and Unlicense parts) | maintained | training-map generation; AR/OD formulas; oppai preview | CODE_CONFIRMED |
| osu-mlpp | <https://github.com/osu-mlpp> | MIT (org repo); wiki repo no license | design-only WIP | player-skill statistical design | DESIGN_INFERENCE |
| Rewind | <https://github.com/abstrakt8/rewind> | MIT | in development | replay rendering; no skill formulas found | SOURCE_CONFIRMED |
| circleguard | <https://github.com/circleguard/circleguard> | AGPL-3.0 | active | replay forensics; no skill taxonomy | SOURCE_CONFIRMED |
| Ultimate osu! Analyzer | <https://github.com/abraker95/ultimate_osu_analyzer> | MIT | inactive | replay + beatmap analysis | SOURCE_CONFIRMED |

Also reviewed and excluded for lack of algorithm evidence: osu!track,
osuMissAnalyzer, firedigger/osuReplayAnalyzer, McOsu (embeds oppai), and the
empty osu-mlpp code repo. Full structured records are in
`tmp/prior_art/community_v01.json`.

---

## 3. Prior-art algorithm details

### 3.1 ppy/osu difficulty evaluators (pinned commit)

Files inspected under
`osu.Game.Rulesets.Osu/Difficulty/Evaluators/` and
`osu.Game.Rulesets.Osu/Difficulty/Preprocessing/OsuDifficultyHitObject.cs`.

- `NORMALISED_RADIUS = 50`, `NORMALISED_DIAMETER = 100`,
  `MIN_DELTA_TIME = 25` (`CODE_CONFIRMED`).
- `SnapAimEvaluator`: acute angle multiplier 2.41, wide angle 9.67, slider
  travel multiplier 1.5, velocity-change multiplier 0.9, high-BPM bonus
  `1/(1-0.03^(ms/1000)^0.65)` (`CODE_CONFIRMED`).
- `FlowAimEvaluator`: velocity-change multiplier 0.52, angular velocity
  sqrt scaling `0.8 + sqrt(angularVelocity/270)`, final
  `Smootherstep(currDistance, 0, NORMALISED_RADIUS)` (`CODE_CONFIRMED`).
- `SpeedEvaluator`: `strainTime = AdjustedDeltaTime /
  clamp((strainTime / HitWindowGreat) / 0.93, 0.92, 1)`; >200 BPM bonus
  `0.75 * ((BPMToMilliseconds(200) - strainTime) / 40)^2`;
  `speedDifficulty = (1 + speedBonus) * 1000 / strainTime *
  1/(1 - 0.3^(ms/1000)) * doubleTapFeasibility` (`CODE_CONFIRMED`).
- `RhythmEvaluator`: 5 s / 32-object history, delta ratio, island occurrence
  nerf, output `sqrt(4 + rhythmComplexitySum*0.95)/2` (`CODE_CONFIRMED`).
- `ReadingEvaluator`: 3 s density window, 1.5-diameter distance influence,
  preempt pressure `((500-preempt+|preempt-500|)/2)^2.5 / 140000`
  (`CODE_CONFIRMED`).
- Difficulty evaluators are beatmap-only (+ mods); pp consumes score
  statistics only, never replay frames. There is **no** osu!standard
  stamina, finger-control, consistency, or tech skill in this version
  (`CODE_CONFIRMED`).
- `OsuPerformanceCalculator`: `DifficultyToPerformance(d) = 4*d^3`;
  aim/speed/reading pp = `4*rating^3`, flashlight pp = `25*difficulty^2`,
  cognition = `Norm(1.1, reading, flashlight *
  clamp(flashlight/reading, 0.25, 1.0))`, total =
  `Norm(1.1, aimValue, speedValue, accuracyValue, cognitionValue) * 1.12`
  (`CODE_CONFIRMED`).
- Final skill aggregation differs by skill: **Aim** is a
  `VariableLengthStrainSkill` (geometric weighted sum of reduced strain
  peaks, decay weight 0.9); **Speed** and **Reading** are `HarmonicSkill`
  (harmonic-style weighted sum of sorted per-object difficulties); **Flashlight**
  is a `StrainSkill` (`CODE_CONFIRMED`). Star ratings: aim =
  `difficultyValue^0.63 * 0.02275`, others = `sqrt(difficultyValue) * 0.0675`
  (`CODE_CONFIRMED`).

### 3.2 oppai-ng / oppai

- Aim strain: `max(1.5*angle_bonus^0.99/max(107, prev_strain_time) +
  distance^0.99/max(107, strain_time), distance^0.99/strain_time)`
  (`CODE_CONFIRMED`).
- Speed strain: below-75 ms-interval speed bonus and sharp-angle bonus, then
  `(1+(speed_bonus-1)*0.75) * angle_bonus *
  (0.95+speed_bonus*(distance/125)^3.5) / max(delta_time, 50)`
  (`CODE_CONFIRMED`).
- Strain decay: `decay_base = {0.3 speed, 0.15 aim}` per second; strain
  scaling `{1400 speed, 26.25 aim}` (`CODE_CONFIRMED`).
- Peak strains in 400 ms windows sorted descending; difficulty =
  `sum(peak * 0.9^i)`; stars = `sqrt(difficulty) * STAR_SCALING_FACTOR`;
  the separate `sum(peak^1.2)` accumulator feeds the length bonus only,
  not star rating (`CODE_CONFIRMED`).

### 3.3 rosu-pp

MIT-licensed Rust reimplementation of ppy/osu difficulty/performance.
Inputs are parsed beatmap + mods + score/accuracy. As of main it tracks an
**older lazer generation**: single `AimEvaluator` + `SpeedEvaluator` +
`RhythmEvaluator` + `FlashlightEvaluator`; there is **no** Snap/Flow/Agility
split and **no** Reading skill. pp total =
`(aim^1.1 + speed^1.1 + acc^1.1 + flashlight^1.1)^(1/1.1) * 1.14`
(`CODE_CONFIRMED`). Useful as a second implementation oracle, but it is
**not** synchronized with ppy/osu 20260706 and must not be cited as
current-official behavior.

### 3.4 Kert/osuSkills

No license file; treat as **REFERENCE_ONLY** (`CODE_CONFIRMED`).

- Agility/aim: weighted distance/time strain with angle bonus and linear
  decay (`CalculateAimStrains`) (`CODE_CONFIRMED`).
- Precision has two code paths (`CODE_CONFIRMED`):
  - **Master output** is agility rescaled by CS:
    `scaledAgility = (agility+1)^0.28 - 0.995462`;
    `precision = 17.7635 * (scaledAgility * CS)^1.06`.
  - The `humanTime = log2(distance/(2*CSpx)+1)*5` family with
    `precisionDiff = 1000^2/(actualTime-humanTime)^2` lives in
    `strains.cpp` as `GetPrecisionDecayFunc`; it feeds agility v3
    (`precision*0.1` magnitude) but is **not** the final precision skill.
- Stamina: tap strain `Scale / interval^(interval^Pow * Mult)` with decay
  (`CODE_CONFIRMED`).
- Tenacity: longest stream interval/length scaling (`CODE_CONFIRMED`).
- Reaction: pattern-required time divided by AR preempt, exponential
  saturation (`CODE_CONFIRMED`).
- Reading: public master `CalculateReading()` is a stub that always sets
  `reading = 0`; no public formula exists (`CODE_CONFIRMED`).
- Accuracy: `42.2505 * (stamina^2.5 / SS_UR)^0.27` with SS_UR from OD and
  circle count; DT/HT mod adjustments (`CODE_CONFIRMED`).
- Memory: computed only with FL; no local HD/FL support here
  (`CODE_CONFIRMED`).

### 3.5 Community replay/analyzer tools

- abraker95/osu-Replay-Analyzer (MIT, dormant) separates beatmap-only
  analyzers from replay analyzers: tap deviation (ms), aim deviation (px),
  Gaussian tap/aim scores (`exp(-(dev/80)^2)` / `exp(-(dev/30)^2)`), and a
  beatmap-only moving-average-cursor reading model
  `exp(dist - radius*sensitivity)` (`CODE_CONFIRMED`).
- osu-aim-analyzer (GPL-3.0, dormant) fits OLS regressions on replay hit
  error vs object position and decomposes aim into offset, width/scale, and
  rotation, with p-values and Cook's distance (`CODE_CONFIRMED`). These are
  the strongest public replay-layer error signals: **tap ms** and **aim px**.
- Rewind, circleguard, and Ultimate osu! Analyzer provide replay hit-error,
  UR, timeline difficulty, and replay inspection. Deeper review found no
  skill-taxonomy formulas in Rewind or circleguard (`SOURCE_CONFIRMED`).
- osu-trainer (no license; GPL-3.0/Unlicense parts) gives the canonical
  AR/OD millisecond conversions under rate change and previews generated
  maps through oppai; it is a map-demand modification tool, not a skill
  classifier (`CODE_CONFIRMED`).

They support the future player layer but do not define our map-demand axes.

### 3.6 Community player-skill aggregations

- Bathbot osu! cards (ISC, active) is the clearest open-source PLAYER SKILL
  pipeline: per top score take `pp_acc/1.1`, `pp_aim/3.7`, `pp_speed/2.5`
  from rosu-pp, weight top scores by `0.95^i`, then squash with
  `map(val) = -101*(8/(val/72+8))^10 + 101`. Relative dominance of the three
  values yields archetypes (Sniper/Ninja/Masher/...). Layers are clean:
  map demand -> per-score performance -> top-score aggregation
  (`CODE_CONFIRMED`).
- osu-mlpp wiki (MIT org, design-only) proposes `P(b,s,l)`: the probability
  that a player of skill level `l` beats score `s` on beatmap `b`, with
  iterative pp re-estimation (`DESIGN_INFERENCE`). It is a useful
  score-population calibration idea, but there is no executable
  implementation to reuse.

Player Profile V0.1 uses both only as conceptual references (section 11).

---

## 4. Strict three-layer separation

- **Map demand:** beatmap-only observables -> demand vector. No player input.
- **Player performance:** one score + map demand -> performance evidence
  (accuracy, combo, misses, pp under mods).
- **Player skill:** many performances -> relative strengths/weaknesses.

Prior-art layer confusion noted:

- ppy star rating is map demand; pp is score performance. pp is often misread
  as player skill (`DESIGN_INFERENCE`).
- osuSkills is the canonical historical confusion: it reads only `.osu` +
  mods (map demand), never score/replay, yet labels its output "Skill
  Points"; its public `reading` skill is a stub that returns 0
  (`CODE_CONFIRMED`).
- Community radar sites often mix all three (`SOURCE_CONFIRMED`).

MVP does not inherit these confusions.

---

## 5. Cross-project taxonomy matrix

| Construct | ppy/osu | oppai/rosu | osuSkills | community replay tools | Beatmap-only? | Local coverage | Classification |
|---|---|---|---|---|---|---|---|
| Aim | Snap/Flow/Agility | Aim strain | Agility | replay aim analyzers | yes | rich (`ls.*`, `spatial.*`) | **CONSENSUS** |
| Flow Aim | FlowAim | angle strain | angle/chaos | partial | yes | rich | **PLAUSIBLE** |
| Precision | radius/SmallCircle | CS scale | agility×CS (human-time family feeds agility v3) | hit-error tools (player) | demand proxy yes; true precision no | rich | **PLAUSIBLE** |
| Speed | Speed | Speed strain | Stamina/tenacity | keypress analyzers | yes | rich | **CONSENSUS** |
| Burst | Speed sub-behavior | speed bonus | tap strains | keypress analyzers | yes | rich | **PLAUSIBLE** |
| Stamina | Speed harmonic strain over time | no explicit | Stamina/Tenacity | replay degradation | demand yes; player needs replay | medium | **PLAUSIBLE** |
| Finger Control | not explicit | not explicit | interval diversity | keypress duration | no (alternation needs replay) | rhythm proxy only | **REPLAY_REQUIRED** |
| Rhythm | RhythmEvaluator | interval angle heuristics | interval/tenacity | partial | yes (complexity) | rich | **CONSENSUS** |
| Reading | ReadingEvaluator | AR/OD inputs | Reaction (reading is a stub) | replay eye/visual tools | demand yes; player needs replay | rich | **CONSENSUS** |
| High-AR Reading | Preempt term | AR input | Reaction | not separate | yes | rich | **PLAUSIBLE** |
| Low-AR Reading | Preempt term | AR input | Reaction | not separate | yes | rich | **PLAUSIBLE** |
| Accuracy | pp accuracy component | acc pp | Accuracy | score accuracy (no replay needed) | no (player layer) | score absent | **SCORE_REQUIRED** |
| Consistency | score spread | no | no | score spread | no (player skill) | score absent | **MULTI_SCORE_REQUIRED** |
| Slider Control | slider travel feeds Aim/Speed | limited | slider TODO | replay slider dev | PATH/TIME only | PATH/TIME rich | **AMBIGUOUS** |
| Memory / Flashlight | FlashlightEvaluator (beatmap + FL mod) | no | Memory | no | needs FL mod state | none | **MOD_SIGNAL_REQUIRED + LOCAL_SIGNAL_UNSUPPORTED** |
| Tech / Control | no | no | composite only | no | no | weak | **DEFER** |

Column note: rosu-pp `main` is one evaluator generation behind pinned ppy/osu
(no Snap/Flow/Agility split, no Reading skill); its aim/speed strains are the
older consolidated evaluators (`CODE_CONFIRMED`). osuSkills public master
reading is a stub; its "Reaction" skill is used as the osuSkills reading-like
entry (`CODE_CONFIRMED`). Dependency tags follow §9.1: `accuracy` =
`SCORE_REQUIRED`, `consistency` = `MULTI_SCORE_REQUIRED`,
`memory_flashlight` = `MOD_SIGNAL_REQUIRED + LOCAL_SIGNAL_UNSUPPORTED`;
`REPLAY_REQUIRED` remains only for `finger_control` among the deferred
constructs.

---

## 6. Prior-art formula -> local field mapping

Full machine mapping is in `tmp/prior_art/local_field_mapping_draft_v01.json`;
source-confirmed project/formula evidence is in
`tmp/prior_art/official_v01.json` (4 official/semi-official projects, 16
skill constructs, pinned-commit code excerpts) and
`tmp/prior_art/community_v01.json` (8 included community projects, 7
reviewed-and-excluded projects, 3 academic/community references,
cross-project consensus).
Key mappings with exact local fields:

| Prior formula concept | Exact local field (version) | Gap |
|---|---|---|
| Snap/Flow velocity | `ls.lazy_jump_distance_cs_normalised`, `ls.minimum_jump_distance_cs_normalised`, `ls.adjusted_delta_time_ms` (Local 0.3) | need per-object strain decay wrapper |
| Aim angle bonus | `ls.slider_aware_angle_rad`, `ls.normalised_vector_angle_rad` (Local 0.3); `spatial.angle_deg_*` (Feature 0.2) | official angle formulas use radians; local has both |
| Flow angular velocity | `spatial.direction_change_ratio_ge_90`, `spatial.sharp_angle_ratio_lt_60` (Feature 0.2) | map-level aggregates lose sequence order |
| Precision human-time | `ls.jump_distance_cs_normalised`, `ls.radius_px`, `ls.cs_scale`, `ls.adjusted_delta_time_ms` (Local 0.3) | replay hit error absent |
| Speed tap strain | `ls.delta_time_ms`, `ls.adjusted_delta_time_ms`, `ls.double_tap_feasibility`, `ls.hit_window_great_ms` (Local 0.3) | no keypress alternation |
| Stamina sustained load | `temporal.burst_longest_duration_ms_125ms`, `temporal.longest_dense_section_ms`, `temporal.object_rate_max_1s`, `section.duration_weighted_density_per_s` (Feature 0.2) | duration proxy, not player degradation |
| Rhythm complexity | `temporal.rhythm_entropy_bits`, `temporal.interval_diversity`, `temporal.interval_ratio_mean` (Feature 0.2) | no island structure, but ref diagnostic available |
| Reading preempt/density | `ls.preempt_ms`, `ls.fade_in_ms`, `ls.radius_px`, `section.density_per_s_p95` (Local 0.3 / Feature 0.2) | Hidden/FL absent |
| Official reference comparison only | `ref.ppy.snap_*`, `ref.ppy.flow_*`, `ref.ppy.speed`, `ref.ppy.rhythm`, `ref.ppy.reading` (Reference 0.2) | reference_only; never production input without proof |

Reference 0.2 is used only for comparison, candidate mining, and diagnostics.

---

## 7. Redundancy / proxy / confound audit

Do not double-count these near-duplicates (from label-efficiency audit and
this review):

- `temporal.burst_count_250ms` ≈ `temporal.dense_section_count`
- `temporal.burst_longest_duration_ms_250ms` ≈
  `temporal.longest_dense_section_ms`
- `slider.repeat_count_max` ≈ `slider.span_count_max` (rank-identical here)
- `section.duration_weighted_density_per_s` ≈ `temporal.density_objects_per_s`
- `section.velocity_norm_per_s_p90` ≈ `spatial.velocity_norm_per_s_p95`
- adjacent percentiles of slider velocity and spatial velocity

Confound rules per axis:

- **Aim:** BPM, AR, CS, slider travel, map length. Use CS-normalised fields
  only.
- **Precision:** CS, OD, short-spacing vs speed. Never use raw distance.
- **Speed:** BPM, OD, single-tap vs alternating. Never use BPM alone.
- **Stamina:** map length, breaks, density proxy, mapping style.
- **Rhythm:** BPM, slider ticks, single-tap vs alternating.
- **Reading:** AR, density, BPM, CS, visual repetition.

Metadata (`stars`, `BPM`, `AR`, `CS`, `OD`, object count, slider fraction,
repeat/span counts) are **confound indicators**, never independent skill
evidence.

---

## 8. PATH / TIME placement

Current PATH and TIME are the best human-calibrated sub-constructs in this
repository (`HUMAN_SMALL_N`). Their placement:

- **PATH** (`ls.lazy_travel_distance_cs_normalised` slider-only p90/max)
  maps to **aim** as slider-aware flow/snap diagnostics. Prior art supports
  slider travel entering Aim (`CODE_CONFIRMED`).
- **TIME** (`ls.slider_total_duration_ms` slider-only p90/max) is
  **UNRESOLVED** between stamina (sustained tracking) and a deferred
  `slider_control` axis (`DESIGN_INFERENCE`).
- MVP therefore exposes `slider_path_demand` and `slider_time_demand` as
  evidence sub-scores but does **not** create a slider-control first-level
  axis.

This prevents the taxonomy from being dominated by the one construct that
currently has human experiments.

---

## 9. Proposed MVP taxonomy

Six first-level axes:

1. `aim` — 瞄准 / 位移
2. `precision` — 精细控制 / 小目标
3. `speed` — 手速 / 连打
4. `stamina` — 耐力 / 持续
5. `rhythm` — 节奏 / 变化
6. `reading` — 读图 / 反应

Machine-readable version:
`docs/SKILL_PROFILER_MVP_TAXONOMY_V01.json`.

Selection evidence: aim/speed/reading have `CONSENSUS`; precision/stamina/
rhythm have `PLAUSIBLE`; all six map-demand axes are beatmap-only estimates;
local field coverage is sufficient. All MVP weights are
`HEURISTIC` / `HEURISTIC_V01`; no MVP weight is a `PRIOR_ART` fact.

### 9.1 Dependency classification (corrected)

One tag is not enough. Each construct carries explicit layer + dependency:

| Tag | Meaning |
|---|---|
| `BEATMAP_ONLY` | estimable from `.osu` geometry/timing/settings (with supported mod state) |
| `SCORE_REQUIRED` | needs one score's judgement statistics |
| `MULTI_SCORE_REQUIRED` | needs several scores of one player |
| `REPLAY_REQUIRED` | needs replay frames (cursor/key state) |
| `MOD_SIGNAL_REQUIRED` | the construct only exists under a mod state the project does not currently compute |
| `LOCAL_SIGNAL_UNSUPPORTED` | local signal layer cannot yet express the construct |
| `AMBIGUOUS` | definition/placement not settled |
| `DEFER` | composite community label, not a stable atomic skill |

Corrected assignments:

- MVP axes (aim, precision, speed, stamina, rhythm, reading):
  `BEATMAP_ONLY` (map-demand proxies; player-layer truth always needs more).
- `accuracy`: layer `PLAYER_PERFORMANCE`, dependency `SCORE_REQUIRED`.
  Official pp accuracy consumes judgement counts / score statistics; it does
  **not** need raw replay frames (`CODE_CONFIRMED`).
- `consistency`: layer `PLAYER_SKILL`, dependency `MULTI_SCORE_REQUIRED`.
  Replay-based consistency would be a future separate extension.
- `memory_flashlight`: official Flashlight difficulty is beatmap + mod state
  (`CODE_CONFIRMED`); our blockers are `MOD_SIGNAL_REQUIRED` and
  `LOCAL_SIGNAL_UNSUPPORTED`, **not** `REPLAY_REQUIRED`.
- `finger_control`: `REPLAY_REQUIRED` (beatmap timing is only a rhythm proxy;
  actual alternation needs replay/key data).
- `slider_control`: `AMBIGUOUS`; PATH/TIME remain diagnostic sub-constructs.
- `tech_control`: `DEFER` (composite label without a stable atomic
  definition).

Rejected/deferred: finger_control (`REPLAY_REQUIRED`), accuracy
(`SCORE_REQUIRED`, player layer), consistency (`MULTI_SCORE_REQUIRED`, player
layer), memory/flashlight (`MOD_SIGNAL_REQUIRED` +
`LOCAL_SIGNAL_UNSUPPORTED`), slider_control (`AMBIGUOUS`), tech (`DEFER`).

---

## 10. MAP_DEMAND_MVP_V01 corrected algorithm spec

### 10.0 Identity

A demand vector is identified by the full computation context, not by the
beatmap alone:

```json
{
  "identity": {
    "algorithm_id": "MAP_DEMAND_MVP_V01",
    "beatmap_checksum": "sha256:...",
    "ruleset": "osu",
    "effective_mods": [],
    "clock_rate": 1.0,
    "feature_version": "0.2.0",
    "local_signal_version": "0.3.0",
    "map_demand_version": "0.1.0",
    "calibration_id": "map_demand_calibration_v01:..."
  }
}
```

- Experimental V0.1 supports **NM only**:
  `effective_mods = []`, `clock_rate = 1.0`.
- Requested non-empty mods are **not** silently treated as NM; the whole
  output returns `status = UNSUPPORTED_MOD_STATE` with the requested mods
  recorded in warnings.
- Same checksum + different supported mod state / calibration_id /
  algorithm version must produce a different identity/cache key.
- Reference Signal version is provenance/diagnostics only and never enters
  the identity contract of axis computation.

#### V0.2 mod-support addendum

V0.1 above remains the frozen NM baseline and calibration population. Map
Demand V0.2 adds a separate, versioned execution layer without rewriting
Feature 0.2 or Local Signal 0.3 artifacts:

- `MOD_CONTEXT_V01` canonicalizes aliases, conflicts, effective mods, and
  clock rate; NC folds to DT and DC folds to HT for demand identity.
- `MOD_TRANSFORM_V01` re-extracts the copied beatmap for EZ, HR, DT/NC, and
  HT/DC. HR applies osu!standard difficulty and vertical-reflection semantics.
- HD requires `hidden_proxy_v0.1.0`, a bounded
  `HEURISTIC_PROXY_INSPIRED_BY_PPY_HIDDEN` reading adjustment. It is not
  represented as memory/FL and does not change the other five axes.
- The transform receipt and every required mod signal must match the requested
  context before scoring. Missing/mismatched evidence returns
  `UNSUPPORTED_MOD_STATE`; it is never treated as NM.
- FL remains `DEFERRED_SEPARATE_DIMENSION`.

### 10.1 Common normalization

- Per-object components are computed from Local 0.3 rows in file order.
- Percentile uses production linear interpolation `q*(n-1)`.
- Quantile rank uses the versioned calibration table selected by
  `calibration_id`; nothing is re-estimated per map.
- Calibration source is a single canonical scope: `5k` QA selection (full
  corpus is not re-extracted in this task). The manifest records
  `source_scope = 5k` and source SHA-256 where available.
- Every constant that is not quoted from inspected upstream code is tagged
  `HEURISTIC_V01` or `HEURISTIC_SAFETY_CAP` in the machine-readable contract.
- Serialization uses strict JSON (`allow_nan=False`); non-finite values are
  impossible by construction and re-checked at the boundary.

### 10.2 aim

```text
for object i>0:
  jump  = ls.lazy_jump_distance_cs_normalised[i]        # None -> skip row
  time  = max(ls.minimum_jump_time_ms[i], 25)
  angle = ls.slider_aware_angle_rad[i]                  # None -> angle_bonus 1
  velocity = jump / time
  angle_bonus = 1 + min(1.0, abs(sin(angle - pi/3))) * 0.5   # HEURISTIC_V01
  snap_proxy[i] = clamp(velocity * angle_bonus, 0, 200)      # cap: HEURISTIC_SAFETY_CAP
flow_proxy = p90 of |angle_i - angle_{i-1}| / max(adjusted_delta_time_ms_i, 25)
                                                             # HEURISTIC_V01
aim_snap_proxy = p90(snap_proxy)
aim_flow_proxy = flow_proxy
aim_score = 0.7 * rank(aim_snap_proxy) + 0.3 * rank(aim_flow_proxy)
                                                             # combination_policy=HEURISTIC_V01
```

Evidence: ppy 20260706 combines snap/flow **per object with a dynamic
logistic probability**, which V0.1 does not reimplement. The angle function
and the 0.7/0.3 mix are our own heuristic and must never be cited as an
official ppy formula. `aim_snap_proxy` and `aim_flow_proxy` are emitted as
independent diagnostics so the combination policy can be replaced without
losing evidence. Method tag:
`HEURISTIC_PROXY_INSPIRED_BY_PPY_AIM`.

### 10.3 precision (corrected)

Upstream `GetPrecisionDecayFunc` facts (`CODE_CONFIRMED`): `humanTime` and
`actualTime` are both milliseconds; infeasible patterns get `INFINITY`
pressure, not zero. Kert/osuSkills has **no license**, so V0.1 is an
independent clean-room adaptation labelled
`HEURISTIC_PROXY_INSPIRED_BY_OSUSKILLS_HUMAN_TIME`, not a direct port.

```text
for each consecutive local pair:
  distance_cs = max(ls.minimum_jump_distance_cs_normalised[i], 0)  # None -> skip
  human_time_ms = log2(distance_cs / 100 + 1) * 5                 # milliseconds
  actual_time_ms = ls.minimum_jump_time_ms[i]                      # milliseconds

  if distance_cs <= 0:
      pressure = 0
  else:
      gap_ms = actual_time_ms - human_time_ms
      if gap_ms <= 0:
          pressure = PRECISION_PRESSURE_CAP
      else:
          pressure = min(PRECISION_PRESSURE_CAP,
                         1_000_000 / max(gap_ms, 1)^2)

precision_p90 = p90(pressure)
precision_score = rank(precision_p90)
```

- `PRECISION_PRESSURE_CAP = 1_000_000` is versioned and tagged
  `HEURISTIC_SAFETY_CAP`; it equals the upstream finite upper bound at a
  1 ms denominator and guarantees no Infinity/NaN.
- The old spec errors are removed: no `/1000` time conversion, no
  `actual_time <= human_time -> 0`, no raw
  `CS_factor = (5.5 - CS) / 4.5` (it pointed the wrong direction, collapsed
  on common CS values, and double-encoded size normalisation already present
  in `distance_cs`).
- `precision` depends on `difficulty.CS` only through the already
  CS-normalised distance field; no extra raw-CS multiplier is used as a main
  signal.

### 10.4 speed (proxy)

```text
for object i>0:
  dt = ls.adjusted_delta_time_ms[i]                 # None -> skip
  hw = ls.hit_window_great_ms[i]                    # None -> row unavailable
  strain_time = dt / clamp((dt / hw) / 0.93, 0.92, 1)
  double_tap_penalty = 1 - ls.double_tap_feasibility[i]  # missing -> 1.0
  tap_strain = 1000 / max(strain_time, 25) * clamp(double_tap_penalty, 0, 1)

speed_p90 = p90(tap_strain)
speed_score = rank(speed_p90)
```

Method tag: `HEURISTIC_PROXY_INSPIRED_BY_PPY_SPEED`. This is **not** an
official SpeedEvaluator clone: the 200 BPM quadratic bonus, high-BPM decay
bonus, RhythmEvaluator multiplier, and HarmonicSkill aggregation are not
implemented in V0.1. The double-tap term follows the official penalty
direction (higher double-tap feasibility lowers demand).

### 10.5 stamina (proxy)

```text
sustained_ms = temporal.longest_dense_section_ms
duration_share = sustained_ms / max(temporal.map_duration_ms, 1)
density = section.duration_weighted_density_per_s
stamina_score = 0.6 * rank(sustained_ms) + 0.2 * rank(duration_share)
              + 0.2 * rank(density)                 # HEURISTIC_V01
```

Stamina is an experimental map-demand proxy. ppy/osu standard has no
independent stamina skill (`CODE_CONFIRMED`); the word "stamina" here never
means official stamina.

### 10.6 rhythm (proxy)

```text
rhythm_score = 0.5 * rank(temporal.rhythm_entropy_bits)
             + 0.3 * rank(temporal.interval_diversity)
             + 0.2 * rank(temporal.interval_ratio_mean)   # HEURISTIC_V01
```

Timing-complexity proxy only. This is not a reimplementation of the ppy
island/rhythm-evaluator model.

### 10.7 reading (proxy, three diagnostics)

```text
preempt_ms = effective_ar_preempt_ms              # see legacy AR rule below
reading_high_ar_proxy = ((500 - preempt_ms + |preempt_ms - 500|)/2)^2.5 / 140000
reading_density_proxy = section.density_per_s_p95
reading_visual_change_proxy = spatial.direction_change_ratio_ge_90   # direct, not inverted
reading_score = 0.2 * rank(reading_high_ar_proxy)
              + 0.5 * rank(reading_density_proxy)
              + 0.3 * rank(reading_visual_change_proxy)   # HEURISTIC_V01_REV2
```

Legacy effective-AR rule (`REV3`, MapDemand layer only):

```text
explicit ApproachRate present            -> effective AR = ApproachRate, provenance EXPLICIT_AR
ApproachRate missing + OverallDifficulty -> effective AR = OverallDifficulty, provenance LEGACY_AR_FALLBACK_TO_OD
both missing                             -> reading axis abstains
```

This mirrors ppy/osu `LegacyBeatmapDecoder`. Frozen Feature 0.2 / Local 0.3
artifacts are **not** rewritten: the local layer may still expose
`ls.preempt_ms = None` for OD-only legacy maps; MapDemand resolves the
effective AR above those artifacts and records provenance. The first 5k
audit (REV2) therefore overstated reading abstention: all 913 AR-missing
maps had OD and are recoverable.

Weight rationale (`HEURISTIC_V01_REV2`, recorded after the first 5k audit):
the original `0.5 high-AR / 0.3 density / 0.2 visual-change` mix made the
high-AR term dominate. In the 5k calibration, 3904/4087 maps with AR data
have `preempt >= 500`, so the high-AR term is exactly 0 for them and its
empirical-CDF rank is already 0.955 before any discrimination; a 0.5 weight
forced a score floor near 0.49. REV2 lowers high-AR to 0.2 and raises density
to 0.5 and visual change to 0.3 so the axis still separates ordinary maps
while keeping high-AR as a minority diagnostic.

- The high-AR pressure term is quoted from official `ReadingEvaluator`
  (`CODE_CONFIRMED`) but used here only as a heuristic diagnostic; QA shows
  official reference reading correlates weakly with `preempt_ms` alone, so
  this term is never described as a sufficient reading proxy.
- `reading_visual_change_proxy` uses the direction-change ratio directly
  (more visual change -> more demand); the earlier inverted "repetition
  nerf" form is removed.
- `ref.ppy.reading` is diagnostic comparison only, never a target or an
  axis input.

### 10.8 Missing-signal / pathological / unsupported behavior

- Per-axis required signals missing -> `status=INSUFFICIENT_EVIDENCE`, no
  score, abstention entry with reasons. Never fabricate 0.
- Requested mods unsupported -> whole output
  `status=UNSUPPORTED_MOD_STATE` (NM-only V0.1).
- Geometry-blocked sliders keep provenance and are excluded with a warning.
- Pathological finite values are clamped only through explicit versioned
  `HEURISTIC_SAFETY_CAP` constants; saturation is reported as a warning.
- Non-finite values are never serialized (`allow_nan=False` plus a final
  finite-value check).
- Reference `ref.ppy.*` fields have role `DIAGNOSTIC_ONLY` and are blocked
  by a field-role gate from entering axis computation or calibration.

---

## 11. Player Profile V0.1 design

Inputs (none available locally yet; interface only):

- score id, beatmap checksum, mods, accuracy, 300/100/50/miss, max combo, pp,
  timestamp, optional playcount/recency;
- cached `MapDemandMVP` vector for the beatmap.

Prior-art anchors for this layer:

- Bathbot osu! cards (`CODE_CONFIRMED`, ISC): top-score weighted
  (`0.95^i`) per-score pp components + monotone squash + intra-player
  archetypes. We borrow the layer structure and relative-to-self idea only;
  we do **not** inherit ppv2 component definitions.
- osu-mlpp wiki (`DESIGN_INFERENCE`): population-probability calibration
  `P(b,s,l)`. Recorded as a future calibration direction, not implemented
  in V0.1.
- abraker95/osu-Replay-Analyzer and osu-aim-analyzer (`CODE_CONFIRMED`):
  future replay-layer signals are tap deviation (ms) and cursor-to-target
  deviation (px, decomposed into offset/scale/rotation).

Per-axis performance evidence:

```text
quality(score, axis) =
    normalized_accuracy * combo_factor * miss_penalty
    * demand_achievement(axis_demand)
```

Player estimate is **relative to own history**:

- For each axis, compare evidence on high-demand maps vs personal baseline.
- Output relative label: `above_personal_baseline`, `below_personal_baseline`,
  `unclear`, plus evidence list.
- No global percentile in V0.1.

Bias controls (recorded, not silently corrected):

- BP = historical peak / preference, not current form.
- recent = form, not latent skill.
- farm/map-selection/retry bias are warnings.
- Mods are explicit fields; no silent skill mapping.
- Failed plays can enter as negative evidence only when the score API is
  trusted; otherwise excluded with warning.
- Same-map multiple scores: keep latest and best, report both.

---

## 12. Evidence-first output contract

Every skill estimate has:

```json
{
  "skill": "reading",
  "level": "below_personal_baseline",
  "confidence": 0.58,
  "status": "EMITTED | INSUFFICIENT_EVIDENCE | UNKNOWN",
  "sample_count": 17,
  "coverage": 0.83,
  "disagreement": 0.12,
  "warnings": ["farm_bias_suspected"],
  "evidence": [
    {
      "signal": "section.density_per_s_p95",
      "direction": "negative",
      "strength": 0.7,
      "source": "Feature 0.2"
    }
  ]
}
```

A radar number without evidence is forbidden.

---

## 13. Confidence / abstention

Confidence considers: sample size, feature coverage, number of independent
signal families, directional agreement, confound count, score diversity.
If evidence is insufficient, return `INSUFFICIENT_EVIDENCE` or `UNKNOWN`.
No dimension is forced to fill a radar.

---

## 14. Human calibration integration

Parallel lines, not sequential blockers:

- MVP heuristic line: deterministic map-demand scores.
- N=1/N=3/N=5 human line: existing PATH/TIME protocol continues.
- Human evidence currently validates constructs/thresholds/directions only.
- No population-calibrated skill score is claimed until the small-N protocol
  reaches its pre-declared stopping rules.

---

## 15. Active learning status

The label-efficiency audit found surrogate active-learning strategies did not
beat random with the current oracle. This phase therefore does not redesign
the active learner unless prior-art research finds a genuinely independent
label source. It did not; community tools are replay/score tools, not
independent skill labels.

---

## 16. Licensing / provenance

| Project | License | Use here |
|---|---|---|
| ppy/osu | MIT | formulas reimplemented independently; cite pinned commit |
| oppai-ng | Unlicense | formulas reimplemented independently |
| rosu-pp | MIT | implementation oracle only |
| Kert/osuSkills | **no license** | REFERENCE_ONLY; do not copy code |
| Bathbot | ISC | layer/aggregation concept only |
| abraker95/osu-Replay-Analyzer | MIT | replay-error signal concept only |
| osu-aim-analyzer | GPL-3.0 | concept only; no code copied |
| osu-trainer | **no license** (GPL-3.0/Unlicense parts) | AR/OD conversion formulas cited; no code copied |
| osu-mlpp | MIT (org repo) | architecture reference only |
| Rewind | MIT | concept only |
| circleguard | AGPL-3.0 | concept only; no code copied |
| Ultimate osu! Analyzer | MIT | concept only |

Copied code: none in production. Short excerpts were fetched under
`tmp/prior_art/` for audit citation only.

---

## 17. Risks

1. Quantile-rank normalization depends on the fixed corpus; a different corpus
   changes scores. Version the calibration table.
2. Precision/stamina/reading are map-demand proxies, not player abilities.
3. PATH/TIME human work may still be construct-ambiguous (zero-inclusive vs
   slider-only p90, percentile method mismatch).
4. Reference signals must not leak into production inputs.
5. No player score/BP data exists; Player Profile V0.1 is interface-only.
6. osuSkills has no license; treat formulas as inspiration only.
7. Bathbot player-skill prior art inherits ppv2 component definitions;
   copying its axes would re-import ppv2 blind spots (no stamina/reading).
8. Kert master precision is agility-dependent; upstream uses the human-time
   family only inside agility v3, so our precision V0.1 is a design
   adaptation, not a direct port.
9. osuSkills public `reading` is a stub; any future "osuSkills reading"
   reference must not rely on a non-public website formula.
10. The 5k QA found multiple axis pairs with Spearman `|rho| > 0.8` and a
    reading coverage gap (missing AR -> 938 abstentions). The axes are
    correlated difficulty facets; do not present them as independent skills
    without further human/construct work.

---

## 18. Experimental implementation — completed

**`MAP_DEMAND_MVP_V01`** is implemented outside production `src/`:

- `tools/map_demand_v01/` package: `contract.py`, `model.py`,
  `calibration.py`, `qa.py`, `cli.py`;
- thin entry: `tools/skill-profiler-map-demand-v01.py`;
- tests: `tests/test_map_demand_v01.py` (39 tests);
- QA artifacts (canonical REV3):
  `training/datasets/map_demand_qa_v01_rev3/`
  (`qa_report.json`, `qa_report.md`); REV1/REV2 calibration and QA runs are
  preserved unchanged.

No production `src/` change was made by this task.

Required inputs (NM-only V0.1):

- `LocalSignalExtractor("0.3.0")` object rows;
- `FeatureExtractor("0.2.0")` map features;
- optional `ReferenceSignalExtractor("0.2.0")` diagnostics with role
  `DIAGNOSTIC_ONLY`.

Required outputs: corrected §10 identity, six axes with per-axis
`signals`, `warnings`, `abstentions`, `diagnostics`, strict JSON
(`allow_nan=False`), `calibration_id`.

Calibration: generate versioned artifacts without overwriting history.
REV1/REV2 builds are preserved; the canonical REV3 build (legacy effective-AR
resolution) is `training/datasets/map_demand_calibration_v01_rev3/`
(`calibration.json` + `calibration_manifest.json` +
`calibration_samples.jsonl`), consuming the existing
`feature_qa_v02/feature_qa_5k.jsonl` and
`local_signal_qa_v03/local_signal_qa_5k.jsonl` artifacts. The legacy-AR audit
is `training/datasets/map_demand_legacy_ar_audit_v01.json`. Canonical
calibration source for this task: `5k`; full-corpus re-extraction is not
performed.

Validation fixtures:

- `training/datasets/golden_v03/` fixtures;
- `training/datasets/feature_qa_v02/feature_qa_5k.jsonl`;
- `training/datasets/local_signal_qa_v03/local_signal_qa_5k.jsonl`;
- PATH/TIME human pairs for sanity checks only.

Stop conditions: no final model training, no production profiler change, no
Player Profile implementation, no commit/push until a separate instruction.

---

## 19. Final status

```text
RESEARCH / ARCHITECTURE:      READY
CORRECTED ALGORITHM SPEC:     READY
EXPERIMENTAL IMPLEMENTATION:  QA_PASS_WITH_RISKS
QA VERDICT:                  MAP_DEMAND_MVP_V01_QA_PASS_WITH_RISKS
```

QA headline (canonical 5k, calibration
`mdcal_v01_5k:79cec83c7e741b4105fa`, REV3 with legacy effective-AR
resolution): 5000 maps; emitted aim 4976 / precision 4985 / speed 4985 /
stamina 4991 / rhythm 4979 / reading 4975; reading abstained 25 (visual
change feature missing), down from 938 before the legacy-AR fix
(A=913 OD-only maps recovered via `LEGACY_AR_FALLBACK_TO_OD`; B=0; C=0);
no non-finite axis scores; direct recompute of 20 maps matches cached
components exactly; ref gate blocked. Risks that prevent a plain `QA_PASS`:

1. Several axis pairs still have Spearman `|rho| > 0.8` (strongest
   aim/precision 0.883; aim/speed 0.862, precision/speed 0.877,
   aim/stamina 0.832, precision/stamina 0.838, stamina/reading 0.837,
   aim/reading 0.849). None exceed 0.9 and none are rank-identical, but the
   axes are correlated difficulty facets.
2. Reading still abstains for 25/5000 maps because
   `spatial.direction_change_ratio_ge_90` is missing.
3. The `HEURISTIC_V01_REV2` reading weights remain justified under the
   corrected input semantics: the high-AR pressure term is exactly zero for
   4814/5000 maps (effective preempt >= 500), so its empirical-CDF rank
   starts at 0.9628; keeping it at weight 0.2 prevents another score floor
   while preserving the minority high-AR diagnostic.

No `PRODUCTION_READY`, `PLAYER_SKILL_VALIDATED`, or `HUMAN_CALIBRATED`
claim is made. The verdict is
`MAP_DEMAND_MVP_V01_QA_PASS_WITH_RISKS`; a plain `QA_PASS` is not claimed
because the cross-axis correlations and the remaining reading coverage gap
are material.
