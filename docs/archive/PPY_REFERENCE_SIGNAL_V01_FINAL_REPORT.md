# Official Reference Signal v0.1 + Segment Signal QA - Final Report

Date: 2026-08-11

## 1. Implementation summary

An isolated Official Reference Signal Layer v0.1 (`ref.ppy.*`) was built under
`src/osu_skill_profiler/reference/ppy/` as an independent, pinned
reimplementation of selected ppy/osu per-object evaluator semantics. A
separate Segment Signal QA v0.1 (`tools/reference_signal_qa.py`) compares
Layer A observables (`ls.*`) with Layer B references (`ref.ppy.*`) across the
real corpus. No final difficulty aggregation, star rating, PP, taxonomy or
model training is produced.

## 2. Exact exposed ref.ppy.* signals

1. `ref.ppy.snap_include_sliders`
2. `ref.ppy.snap_exclude_sliders`
3. `ref.ppy.agility`
4. `ref.ppy.flow_include_sliders`
5. `ref.ppy.flow_exclude_sliders`
6. `ref.ppy.speed`
7. `ref.ppy.rhythm`
8. `ref.ppy.speed_with_rhythm` (decomposition product, not official strain)
9. `ref.ppy.reading`

Plus identity fields `ref.original_index`, `ref.time_sorted_index`,
`ref.start_time_ms`, `ref.object_type`, `ref.provenance`.

## 3. Exact upstream pin

- Repository: `ppy/osu`
- Commit: `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`
- Difficulty version: `20260706`

## 4. Upstream source files/functions used

`SnapAimEvaluator.cs`, `FlowAimEvaluator.cs`, `AgilityEvaluator.cs`,
`SpeedEvaluator.cs`, `RhythmEvaluator.cs`, `ReadingEvaluator.cs`,
`OsuDifficultyHitObject.cs`, `DiffUtils.cs`, and `Skills/Speed.cs`
(decomposition boundary only). Blob SHAs are recorded in
`docs/PPY_DIFFICULTY_REFERENCE_AUDIT.md` and `docs/PPY_REFERENCE_SIGNAL_PARITY_V01.md`.

## 5. Reference contract status

`docs/PPY_REFERENCE_SIGNAL_CONTRACT_V01.md` (v0.1.0) - FINAL. Every field is
classified `OFFICIAL_REFERENCE`, `reference_only: true`,
`never_ground_truth: true`, `model_input_safe: false`, `exploratory_safe:
true`.

## 6. Executable upstream parity status

```text
UPSTREAM_EXECUTABLE_PARITY = BLOCKED
```

Blocker: no .NET SDK in the environment; no C# harness was built. Golden
expectations are `SOURCE_AUDITED`, never claimed as official output.

## 7. Golden results

- 13 embedded synthetic fixtures
- 128/128 records PASS
- 0 failures
- tolerances 1e-6 default / 1e-4 legacy-repeat; pathological fixtures assert
  no NaN/Inf + provenance

## 8. Full unit-test results

145/145 PASS (126 pre-existing + 19 new reference-signal tests). CLI smoke
(`extract-reference-signals`) PASS.

## 9. 5k QA

5,000/5,000 maps OK, 0 failures, 0 NaN/Inf maps, 18 geometry-blocked maps /
637 objects, 233,625 unavailable rows, 19 extreme finite rows, 4,672 core
records, 0 ordering/alignment/coverage/serialization/aggregate failures.

## 10. 20k QA

20,000/20,000 maps OK, 0 failures, 0 NaN/Inf maps, 22 geometry-blocked maps /
642 objects, 579,739 unavailable rows, 19 extreme finite rows, 19,672 core
records, all invariants 0.

## 11. Full 126,509 QA

126,509/126,509 maps OK, 0 failures, 0 NaN/Inf maps, 53 geometry-blocked maps
/ 819 objects, 2,924,914 unavailable rows, 19 extreme finite rows, 126,181
core records, all invariants 0. Geometry-blocked counts exactly match the
v0.2 baseline (53/819).

## 12. Missing/unavailable/pathological statistics

- First-object `no_difficulty_row`: 126,509 rows (one per map).
- `reading` missing 2,846,376 (legacy AR-missing maps dominate).
- `speed` missing 279,374; `rhythm` missing 215,685; `speed_with_rhythm`
  missing 368,357.
- Include-variant surplus missingness corresponds to geometry-blocked slider
  rows.
- 19 extreme finite object values are provenance-tagged and never clipped;
  include-variants can reach 1.6e17 (pathological slider/BPM inputs).
- Zero values follow upstream gates (`0.0` only where the evaluator returns
  0); `reading` zero rate 71.8% is a legitimate upstream distribution, not
  missingness.

## 13. Performance

- Full per-map latency: p50 367.6 ms, p95 1,418.0 ms, p99 2,612.1 ms,
  max 436,867 ms, mean 569.3 ms.
- Wall extraction: 5k 330 s (16 workers), 20k 788 s (16 workers), full ~6,355 s
  (~19.9 maps/s wall average).
- Log-log latency slopes: object_count 0.89-1.02, segment_count 1.05-1.16 - no
  O(n^2) hotspot.

## 14. Correlation findings

- Map-level: 28 pairs with |Pearson| > 0.5 on 5k. Pearson=1.0 include-variant
  pairs are driven by extreme finite rows; Spearman 0.4-0.6 is the honest
  rank signal. Snap/agility/flow means are strongly negatively correlated
  with hit-window/preempt (harder timing -> higher reference means).
- Object-level: flow_include ~ lazy_jump Pearson 0.94 / Spearman 0.66;
  snap_include ~ lazy_jump Pearson 0.81 / Spearman 0.36; speed ~
  adjusted_delta Spearman -0.99 (inverse); reading ~ preempt ~ 0.
- Upper-tail overlap: flow_include 38.0% @95, snap_include 26.9% @95, agility
  3.6% @95, speed/reading ~0 (direction/regime mismatch).

## 15. Reference-disagreement findings

- Type A (ref extreme while observables ordinary): 0 candidates in the
  300k-object sample.
- Type B (observable extreme while refs ordinary): 1,496 candidates before
  cap; 50 kept across 41 maps in
  `reference_disagreement_candidates.jsonl`.
- Representative cases: long-travel/high-repeat sliders (e.g. `1214 They
  Might Be Giants - I'm Impressed [Insane]`, travel 793.6 normalised px,
  nested 11, refs ordinary) and large CS-normalised jumps (`46 Hinoi Team -
  Aishiteru [Sweatin]`, jump 595.7, refs ordinary). Neutral wording only; no
  "official blind spot" claims.

## 16. Segment information-preservation findings

- 161,624 segments over 5k; segments/map mean 32.3, p50 25, max 564; 16.0
  objects/segment; 0 empty; 3.46% sparse (<=2 objects).
- Spike preservation: segment max == object max on 3,960-4,985 maps per
  signal.
- Segment p95 retention: 15.9%-43.1% per signal - 5 s windows dilute
  upper-tail concentration; global maxima survive, p95-level structure does
  not.
- Boundary sensitivity: 10.2% of p90+ objects lie within 250 ms of a 5 s
  boundary.
- Sustained peaks: 4,970/5,000 maps have >= 2 segments with max >= map p95.
- Recommendation (future, no production change): overlapping windows,
  adaptive sections, object-count windows, event-centered windows.

## 17. Known deviations from pinned ppy/osu

1. Stacking not modelled (raw coordinates).
2. Slider lazy geometry reused from audited Layer A (shared guards).
3. `speed_with_rhythm` is an evaluator product without 1.16 multiplier /
   strain decay.
4. `reading` unmodded (hidden=false) only.
5. Executable parity blocked; golden expectations source-audited.

## 18. Licensing / attribution status

No upstream code vendored; independent reimplementation from audited
semantics. `diff_utils.py` is a small direct adaptation of ppy/osu `DiffUtils`
(MIT). If distributed outside the project, add a `NOTICE` naming ppy/osu,
commit `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`, and the MIT licence.
Revision pinning is enforced in `contract.py` and the audit appendix.

## 19. Files changed

New:

- `src/osu_skill_profiler/reference/__init__.py`
- `src/osu_skill_profiler/reference/ppy/__init__.py`
- `src/osu_skill_profiler/reference/ppy/contract.py`
- `src/osu_skill_profiler/reference/ppy/diff_utils.py`
- `src/osu_skill_profiler/reference/ppy/preprocess.py`
- `src/osu_skill_profiler/reference/ppy/evaluators.py`
- `src/osu_skill_profiler/reference/ppy/extractor.py`
- `tests/test_reference_signals.py`
- `tools/golden_reference_signals.py`

Modified:

- `src/osu_skill_profiler/cli/main.py` (added `extract-reference-signals`)
- `src/osu_skill_profiler/signals/extractor.py` (backward-compatible
  `_geometries_out` hook)
- `tools/reference_signal_qa.py` (repaired/implemented real segment QA)

Docs:

- `docs/PPY_REFERENCE_SIGNAL_CONTRACT_V01.md`
- `docs/PPY_REFERENCE_SIGNAL_PARITY_V01.md`
- `docs/SEGMENT_SIGNAL_QA_V01.md`
- `docs/PPY_REFERENCE_SIGNAL_V01_FINAL_REPORT.md`

## 20. Artifacts generated

- `training/datasets/golden_reference_v01/golden_reference_signals.jsonl`
  and summary
- `training/datasets/reference_signal_qa/reference_qa_{5k,20k,full}.jsonl`
- `training/datasets/reference_signal_qa/reference_qa_stats.json`
- `training/datasets/reference_signal_qa/segment_stats.json`
- `training/datasets/reference_signal_qa/reference_disagreement_candidates.jsonl`
- `training/datasets/reference_signal_qa/REFERENCE_QA_REPORT.md`

Large corpus artifacts remain local and are not committed.

## 21. LOC composition

- Production reference implementation: 1,613 lines (7 reference modules).
- Tests: 367 lines (`tests/test_reference_signals.py`).
- Golden tooling: 511 lines (`tools/golden_reference_signals.py`).
- QA tooling: 1,339 lines (`tools/reference_signal_qa.py`, includes repaired
  segment QA).
- Docs: ~600 lines across 4 new documents.
- Modified production files: `cli/main.py` (+~14 lines),
  `signals/extractor.py` (+~8 lines hook).

10 largest changed/new files:

1. `tools/reference_signal_qa.py` (1,339)
2. `src/osu_skill_profiler/reference/ppy/evaluators.py` (778)
3. `tools/golden_reference_signals.py` (511)
4. `src/osu_skill_profiler/signals/extractor.py` (461)
5. `tests/test_reference_signals.py` (367)
6. `src/osu_skill_profiler/reference/ppy/contract.py` (268)
7. `src/osu_skill_profiler/reference/ppy/preprocess.py` (204)
8. `src/osu_skill_profiler/reference/ppy/extractor.py` (196)
9. `src/osu_skill_profiler/cli/main.py` (184)
10. `src/osu_skill_profiler/reference/ppy/diff_utils.py` (104)

## 22. Technical debt discovered

- `TECH_DEBT_QA_COMMON`: `reference_signal_qa.py` reuses `build_selection`,
  reservoir and percentile helpers from `feature_qa.py` but duplicates
  stats/segment/correlation/report infrastructure. A future QA-common module
  is recommended; no refactor performed during this goal.
- Segment `start_idx`/`end_idx` are time-sorted positions; documented in the
  contract to avoid future join bugs.
- `maps_per_second` in stats is a CPU-throughput metric; wall-clock rates are
  reported separately in the QA docs.

## 23. Explicit confirmations

- No model training
- No human labels
- No taxonomy freeze or unsupervised taxonomy
- No player profiling
- No tournament implementation
- No replay/live implementation
- No WuxinBot integration
- No star rating clone
- Feature v0.1 unchanged
- Local Signal v0.2 unchanged
- No commit
- No deployment

## Final statuses

```text
IMPLEMENTATION:            PASS
UPSTREAM_EXECUTABLE_PARITY: BLOCKED
CORPUS_QA:                 PASS
SEGMENT_QA:                PASS
OVERALL:                   PASS
```

The BLOCKED parity status is the only non-PASS status and is a documented
environment limitation (no .NET SDK), not a correctness downgrade.
