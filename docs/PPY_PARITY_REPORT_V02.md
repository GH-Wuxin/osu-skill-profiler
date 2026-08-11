# ppy/osu Parity Report — Local Signal Layer v0.2

Status: **PASS (golden) / UPSTREAM_PARITY_HARNESS = BLOCKED**

## Upstream pin

| Item | Value |
| --- | --- |
| Repository | `ppy/osu` |
| Commit | `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e` (master, 2026-08-10) |
| Difficulty version | `20260706` (`OsuDifficultyCalculator.Version`) |
| Audited reference | `docs/PPY_DIFFICULTY_REFERENCE_AUDIT.md` |

No code from upstream is vendored and no upstream master is consumed at
runtime. All semantics are independently reimplemented from the audit.

## Parity harness status

```text
UPSTREAM_PARITY_HARNESS = BLOCKED
```

Reason: no isolated, pinned .NET/osu! reference harness is available in this
environment. Building one would require a full `ppy/osu` checkout plus a
ruleset-only runner; that is a future tooling project and must not become a
runtime dependency of the profiler.

Because the harness is blocked, Gate B validation uses:

1. **audited formula constants** from the pinned commit (radii, scales,
   preempt/fade/hit-window formulas, lazy-cursor constants);
2. **independent synthetic fixtures** with hand-computed and
   formula-derived reference values;
3. documented numeric tolerances instead of exact-match claims where the
   reimplementation may differ on curved geometry.

This is not a claim of bit-exact parity with the C# implementation. It is a
claim that every implemented primitive follows the audited definitions and
matches the reference values within the stated tolerance on the golden corpus.

## Golden corpus

Artifact: `training/datasets/golden_v02/golden_corpus.json`
(fixtures under `training/datasets/golden_v02/fixtures/`).

- fixtures: **20**
- expected checks: **148**
- matched: **148**
- failures: **0**

Each record contains `sample_id`, map checksum, upstream commit, difficulty
version, feature version, per-object expected/local values, tolerance, and
verdict.

| Fixture | Coverage | Checks | Tolerance |
| --- | --- | --- | --- |
| `g_circles_basic` | basic circles, CS4 AR9 OD8 | 15 | 1e-6 |
| `g_stream_200bpm` | 16-note 50 ms stream, CS5 AR9 OD8 | 48 | 1e-6 |
| `g_slider_linear` | linear slider lazy geometry | 20 | 1e-6 |
| `g_slider_repeat2` | 2-span repeat slider lazy geometry | 9 | 1e-4 |
| `g_slider_repeat3` | 3-span repeat slider | 4 | 1e-6 |
| `g_slider_bezier` | Bezier slider | 1 | 1e-6 |
| `g_slider_perfect` | perfect-curve arc | 1 | 1e-6 |
| `g_slider_catmull` | Catmull slider | 1 | 1e-6 |
| `g_low_cs` | CS0 radius/scale | 4 | 1e-5 |
| `g_high_cs` | CS10 radius/scale | 4 | 1e-5 |
| `g_low_ar` | AR0 preempt/fade | 4 | 1e-6 |
| `g_high_ar` | AR10 preempt/fade | 4 | 1e-6 |
| `g_bpm_change` | BPM change 120 -> 240 | 6 | 1e-4 |
| `g_sv_change` | SV change 1 -> 2 | 6 | 1e-4 |
| `g_simultaneous` | same-time objects, 25 ms clamp | 3 | 1e-6 |
| `g_legacy_v3` | legacy v3 format | 2 | 1e-4 |
| `g_spinner_context` | spinner before/after circle context | 9 | 1e-6 |
| `g_slider_tail_follow` | circle after slider tail (flow) | 4 | 1e-6 |
| `g_aspire_like` | absurd finite values keep provenance | 0 (no exact-value claim) | 1e-6 |
| `g_out_of_order` | file order vs time order | 3 | 1e-6 |

## Matched signals (golden, per-fixture)

All of the following are covered by at least one fixture and matched 148/148:

- `adjusted_delta_time_ms`, `last_object_end_delta_time_ms`,
  `minimum_jump_time_ms` (25 ms clamp, slider-tail awareness)
- `jump_distance_cs_normalised` / raw, spinner-context zeroing
- `preempt_ms`, `fade_in_ms`, `hit_window_great_ms`
- `radius_px`, `cs_scale` (CS0/CS10)
- `slider_duration_ms`, `slider_velocity_px_per_ms` (BPM/SV change,
  legacy v3)
- `slider_span_count`, `slider_tick_count`, `slider_nested_object_count`
- `lazy_end_position_x/y`, `lazy_travel_distance_cs_normalised`,
  `lazy_travel_time_ms`, `travel_distance_cs_normalised`, `travel_time_ms`
- `slider_aware_angle_rad`, `spinner_context`, `time_sorted_index`

## Tolerance policy

- Exact-integer / boolean / `None` checks: exact match.
- Float checks: `abs(actual - expected) <= max(1e-9, tolerance * abs(expected))`
  with per-fixture tolerance (1e-6 default, 1e-5 for CS extremes, 1e-4 for
  legacy/BPM/SV/repeat fixtures).
- `g_aspire_like` asserts no NaN/Inf and provenance rather than exact values,
  because its inputs are intentionally absurd finite values.

No "trend is roughly right" comparisons are used.

## Mismatches

**None.** All 148 expected checks matched; no unexplained semantic mismatch
was found.

## Unsupported semantics (explicitly out of scope)

- Final `SnapAimEvaluator` / `FlowAimEvaluator` / `AgilityEvaluator` /
  `SpeedEvaluator` / `RhythmEvaluator` / `ReadingEvaluator` values
- `SmallCircleBonus` and other tuned evaluator constants
- Strain peaks, harmonic aggregation, decay-weighted top difficulty
- Star rating / performance conversion
- Flashlight / Hidden / mod-specific signals

These are Layer B reference concepts, not observable primitives; they are
documented in `docs/PPY_DIFFICULTY_REFERENCE_AUDIT.md` and must not enter the
`ls.*` contract.

## Known semantic deviations from pinned ppy/osu

1. **Path flattening guards** (see
   [`LOCAL_SIGNAL_CONTRACT_V02.md`](LOCAL_SIGNAL_CONTRACT_V02.md)):
   upstream flattens high-degree Bezier paths unconditionally; v0.2 refuses
   paths above `MAX_PATH_CONTROL_POINTS = 4096` or
   `MAX_PATH_FLATTEN_WORK = 5_000_000`, and refuses sliders above
   `MAX_SLIDER_SPANS = 10_000` / `MAX_SLIDER_TICKS = 100_000`. The affected
   slider keeps missing semantics (`None`) plus a provenance flag; no fake
   geometry is fabricated. This is a deliberate robustness deviation to avoid
   the observed O(n^2) hang on pathological Aspire-style maps.
2. **Curved-path numeric parity**: linear sliders match the reference
   exactly; Bezier/perfect/Catmull paths are independent reimplementations and
   may differ from C# floating-point evaluation at sub-1e-4 scale. Golden
   tolerances reflect this. `g_slider_bezier` / `g_slider_perfect` /
   `g_slider_catmull` currently assert structural values (span count), not
   full path equality.
3. **Clock-rate / mods**: all values are unmodded (clock rate 1.0). Modded
   difficulty is out of scope for map profiling.

## Licensing

- Implementation is an **independent reimplementation** of audited semantics;
  no upstream source file is copied verbatim into `src/`.
- No `third_party/ppy_osu/` directory is created; no vendoring is required at
  this phase.
- ppy/osu is MIT-licensed; attribution to the pinned commit is recommended in
  any publication using these signals.
- If a real parity harness is built later, it must be isolated, pinned, and
  documented; it must not become a profiler runtime dependency.

## Regression

- Unit/synthetic Gate A: 126/126 tests PASS.
- Golden Gate B: 148/148 checks PASS.
- Real-corpus Gates C/D/E: 5k / 20k / full 126,509 all PASS, 0 failures,
  0 NaN/Inf, 0 ordering/coverage/serialization failures.
