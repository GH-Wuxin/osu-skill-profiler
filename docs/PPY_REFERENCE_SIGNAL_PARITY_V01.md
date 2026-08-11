# Official Reference Signal v0.1 - Upstream Parity Report

Status: **IMPLEMENTATION PASS / UPSTREAM_EXECUTABLE_PARITY = BLOCKED** (2026-08-11)

## 1. Upstream pin

| Item | Value |
| --- | --- |
| Repository | `ppy/osu` |
| Commit | `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e` |
| Difficulty version | `20260706` (`OsuDifficultyCalculator.Version`) |
| Reference contract | `docs/PPY_REFERENCE_SIGNAL_CONTRACT_V01.md` (v0.1.0) |
| Audited source | `docs/PPY_DIFFICULTY_REFERENCE_AUDIT.md` |

No floating upstream source is consumed at runtime. The pinned source was
fetched into `tmp/ppy-osu-pinned/` and blob-verified against the appendix of
the difficulty reference audit.

## 2. Executable upstream parity

```text
UPSTREAM_EXECUTABLE_PARITY = BLOCKED
```

Blocker: no .NET SDK is available in this environment (runtime only), so a
pinned C# harness against the ppy/osu difficulty code cannot be built here.
Per the goal contract, this does not fake official output and does not block
the implementation; expectations in the golden suite are marked
`SOURCE_AUDITED` and never claimed to be official C# output.

Fallback verification used:

1. audited formula constants and evaluator semantics from the pinned commit;
2. independent synthetic fixtures with hand-computed / formula-derived
   expected values;
3. invariant checks (gates, zero semantics, slider-blocked provenance,
   monotonicity on controlled patterns);
4. documented numeric tolerances instead of bit-exact claims.

## 3. Upstream source files and functions used

| Local module | Upstream file (blob SHA) | Functions mirrored |
| --- | --- | --- |
| `diff_utils.py` | `Utils/DiffUtils.cs` (`4548e0a18f8161101b9da356e54e4c0ff3f02600`) | `Pow`, `Norm`, `Logistic`, `Smoothstep`, `Smootherstep`, `ReverseLerp`, `Clamp`, BPM/ms conversion |
| `preprocess.py` | `Preprocessing/OsuDifficultyHitObject.cs` (`ced184299bf89ea796c513987bb092da105c650a`) | difficulty-row construction, small-circle bonus, adjusted delta, minimum jump time, lazy geometry reuse |
| `evaluators.py` | `Evaluators/Aim/SnapAimEvaluator.cs` (`a345b2aa5fb78e9afb8810ee522ee93f0a733909`) | `EvaluateDifficultyOf` |
| `evaluators.py` | `Evaluators/Aim/FlowAimEvaluator.cs` (`cea98ff010f072e0bc16803b46fbb2ceba1f596a`) | `EvaluateDifficultyOf` |
| `evaluators.py` | `Evaluators/Aim/AgilityEvaluator.cs` (`bd5204faaf8d987fdd73027bc0ebf5628bd0f0db`) | `EvaluateDifficultyOf` |
| `evaluators.py` | `Evaluators/Speed/SpeedEvaluator.cs` (`7caa03a0b9c662c032c813e49c4372bb48ab132d`) | `EvaluateDifficultyOf` |
| `evaluators.py` | `Evaluators/Speed/RhythmEvaluator.cs` (`498b130991e3dfadbe8ff11c349d7079c27a7ffb`) | `EvaluateDifficultyOf` |
| `evaluators.py` | `Evaluators/ReadingEvaluator.cs` (`99826ed4170b1ec73fd7b5311f721298eaac8db5`) | `EvaluateDifficultyOf` (hidden=false) |
| `evaluators.py` | `Skills/Speed.cs` (`f8ab313cb76a0ff6f73ef84e5db5175adb7ef8ce`) | `ObjectDifficultyOf` decomposition only (`speed_with_rhythm`) |

Skill aggregation files (`Skills/StrainSkill.cs`, `HarmonicSkill.cs`,
`OsuDifficultyCalculator.cs`) were read only to confirm the boundary; no final
strain aggregation, weighted sums, star rating or PP is implemented or
exposed.

## 4. Implementation boundary

Architecture:

```text
src/osu_skill_profiler/reference/ppy/
  contract.py        # machine-readable contract + upstream pin
  diff_utils.py      # numerical utilities transcribed from DiffUtils
  preprocess.py      # RefObject difficulty-row preprocessing boundary
  evaluators.py      # per-object evaluator reimplementation
  extractor.py       # ReferenceSignalExtractor + 5 s segment summaries
```

The reference layer:

- consumes already parsed beatmaps;
- reuses audited Layer A primitives (distances, timing, angles, lazy slider
  geometry) through a private `_geometries_out` hook; Layer A row semantics are
  unchanged and the hook is backward compatible;
- does not mutate normalised core objects;
- is not imported by normal local-signal extraction;
- requires no runtime network access and no ppy/osu checkout.

## 5. Golden results

Artifact: `training/datasets/golden_reference_v01/golden_reference_signals.jsonl`

| Metric | Value |
| --- | --- |
| Fixtures | 13 (embedded synthetic maps) |
| Expected checks | 128 |
| Passed | 128 |
| Failed | 0 |
| Expectation provenance | `SOURCE_AUDITED` (harness blocked) |

Fixture coverage: basic circles, simple jumps, repeated jumps, acute angle
patterns, obtuse/reversal patterns, simple flow, streams, bursts, BPM changes,
rhythm changes, low/high spacing, low/high CS, low/high AR, slider
entry/exit, slider-heavy patterns, repeat sliders, slider-to-circle
transitions, simultaneous / 25 ms timing, old format maps, pathological finite
geometry, and geometry-blocked cases.

Tolerance policy: exact match for identity / `None` / gate-zero semantics;
float checks use `abs(actual - expected) <= max(1e-9, tolerance * abs(expected))`
with per-fixture tolerance (`1e-6` default, `1e-4` legacy/repeat/slider-heavy);
pathological fixtures assert no NaN/Inf and provenance rather than exact
values.

## 6. Known deviations from pinned ppy/osu

1. **Stacking is not modelled.** Upstream `StackedPosition` (lazer stacking)
   is not reproduced; raw coordinates are used. This affects maps with
   stacked objects, mainly snap/flow angle geometry. The deviation is
   documented and the values remain reference-only.
2. **Slider lazy geometry is reused from Layer A.** Curved-path flattening and
   span/tick guards follow the audited Local Signal v0.2 implementation;
   rows whose geometry exceeds guards are blocked with provenance instead of
   fabricated values.
3. **`speed_with_rhythm` is a decomposition product.** It does not include the
   1.16 skill multiplier or harmonic strain decay and is not an official
   strain value.
4. **`reading` is unmodded only** (`hidden=false`).
5. **Executable parity is blocked**; golden expectations are source-audited,
   not C#-harness output.

## 7. Licensing / attribution

- No upstream source file is vendored.
- `diff_utils.py` is a direct, small adaptation of ppy/osu `DiffUtils`
  numerical helpers; `evaluators.py` is an independent reimplementation from
  audited semantics.
- ppy/osu is MIT-licensed. If this reference layer is distributed outside the
  project, a `NOTICE` entry should name the upstream repository
  (`ppy/osu`), commit `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`, and the MIT
  licence.
- Revision pinning: blob SHAs are recorded in
  `docs/PPY_DIFFICULTY_REFERENCE_AUDIT.md`; `contract.py` pins repository,
  commit and difficulty version; `REFERENCE_VERSION` must be bumped with any
  semantic change.

## 8. Regression protection

Before final verdict:

- full unit suite: 145/145 PASS (126 existing + 19 new reference tests);
- reference golden: 128/128 PASS;
- CLI smoke (`extract-reference-signals` on a fixture): PASS;
- Feature v0.1 and Local Signal v0.2 semantics unchanged (reference layer is
  additive; the only production touch is the backward-compatible geometry
  hook).
