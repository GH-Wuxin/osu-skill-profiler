# Local Signal Layer v0.2 — Final Report

Date: 2026-08-11

## 1. Implementation summary

A new per-object **Local Signal Layer v0.2** was implemented on top of the
frozen 104-feature v0.1 contract. It extracts deterministic, gameplay-aware,
per-object observable signals (`ls.*`) from `.osu` hit objects, following the
audited ppy/osu difficulty preprocessing semantics at a pinned revision.

New modules: `src/osu_skill_profiler/signals/` (`contract.py`, `extractor.py`,
`path.py`, `slider.py`), a `LocalSignalExtractor`, a new CLI command
`extract-local-signals`, fixed-time 5 s segment summaries (mean/p90/max), 33
new unit tests, a 20-fixture golden corpus, and a three-gate real-corpus QA
tool. Pathological slider geometry is bounded by explicit guards and keeps
missing semantics with provenance instead of hanging or fabricating paths.

## 2. New feature/signal count

- `SIGNAL_SCHEMA` entries: **35** (`ls.*`)
- numeric model-input signals (`NUMERIC_SIGNALS`): **28**
- structural/context/provenance entries: 7
- weak-label candidates: **2**
  (`ls.lazy_travel_distance_cs_normalised`,
  `ls.double_tap_feasibility`)
- signal version: **0.2.0**

## 3. v0.1 compatibility status

- All 104 v0.1 features remain **frozen and unchanged**; v0.2 uses an
  independent `ls.*` namespace.
- Every QA phase asserts `feature_count_distribution == {104: n}`.
- v0.1 tests 93/93 remain green; total suite is now **126/126**.
- The v0.1 -> v0.2 migration table is machine-readable
  (`migration_table()`), with 3 exact-duplicate aliases canonicalised but
  still emitted.

## 4. Upstream pin

| Item | Value |
| --- | --- |
| Repository | `ppy/osu` |
| Commit | `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e` |
| Difficulty version | `20260706` |

Do not follow master; do not change the revision without re-running the golden
corpus.

## 5. Golden parity results

- Golden fixtures: **20**
- Expected checks: **148**
- Matched: **148 / 148**
- Failures: **0**
- `UPSTREAM_PARITY_HARNESS = BLOCKED` (no .NET harness in this environment);
  validated with audited formula constants + independent synthetic fixtures
  under documented tolerances.

## 6. Unit tests

- `run_tests.py`: **126/126 PASS** (33 new local-signal tests + 93 v0.1 tests)
- coverage includes: 25 ms clamp, same-time objects, CS scaling,
  low/high CS, circle jumps, linear/repeat sliders, lazy end, slider-aware
  angle, preempt, double-tap feasibility, pathological finite values, missing
  AR, legacy v3, out-of-order times, segment coverage, determinism, and an
  O(n) complexity regression.

## 7. 5k QA (Gate C)

- records: **5000 / 5000 PASS**, failures: 0
- core (non-pathological/non-aspire) records: 4672
- NaN/Inf: **0**; ordering/coverage/serialization failures: **0**
- geometry-blocked sliders: **18 maps, 637 objects**
  (missing semantics + provenance, never fabricated)
- extreme finite object values (|v| >= 1e12): **543** (provenance-tagged)
- v0.1 frozen: `{104: 5000}`

## 8. 20k QA (Gate D)

- records: **20000 / 20000 PASS**, failures: 0
- core records: 19672
- NaN/Inf: **0**; ordering/coverage/serialization failures: **0**
- geometry-blocked sliders: **22 maps, 642 objects**
- extreme finite object values: **543**
- distribution stable vs 5k (percentiles, missingness, correlations)

## 9. Full-corpus QA (Gate E)

- records: **126509 / 126509 PASS**, failures: 0
- core records: 126181 (328 pathological-flagged, 14 aspire-like separated)
- NaN/Inf: **0**; ordering/coverage/serialization failures: **0**
- geometry-blocked sliders: **53 maps, 819 objects**
- extreme finite object values: **543** (all provenance-tagged)
- v0.1 frozen: `{104: 126509}`

## 10. Performance

| Phase | Elapsed | Maps/sec | latency p50 | latency p99 | max |
| --- | --- | --- | --- | --- | --- |
| 5k | 166.5 s | 30.0 | 57.4 ms | 999.0 ms | 70.2 s |
| 20k | 322.6 s | 62.0 | 56.9 ms | 396.8 ms | 46.4 s |
| full | 1679.7 s | 75.3 | 75.9 ms | 337.0 ms | 108.2 s |

Log-log latency scaling slopes (full): object_count 0.66, slider_count 0.62,
nested_count 0.69, segment_count 0.86 — no superlinear blowup; the dedicated
complexity regression (1k/2k/4k/8k) passes.

Slowest maps (full): False Noise - Hyperlight [Dodecahedral] (108.2 s),
Kotoha - God-ish (IOException) [lean's Extra] (68.6 s), O2i3 - Ping
(OliBomby) [Aspire] (50.5 s). All complete deterministically; the Aspire
cluster is the pathology the geometry guards exist for.

## 11. Numerical / pathological findings

- **543 extreme finite object values** (|v| >= 1e12) across the corpus,
  dominated by `ls.slider_velocity_px_per_ms` (112 sampled); all kept with
  provenance, none clipped.
- **819 blocked slider objects** on 53 maps from the path/span/tick guards
  (425 control-point + 159 flattening-budget sample entries in the outlier
  file, which caps at 50 samples per map).
- `ls.fade_in_ms` is near-constant (1.0): standard AR values give the 400 ms
  cap for almost every preempt >= 450 ms.
- `ls.slider_*` signals are missing on ~57.6 % of objects (non-sliders), by
  design; `ls.preempt_ms` / `ls.fade_in_ms` missing 4.9 % (missing AR on old
  maps); first-object timing/distance signals missing ~0.22 %.
- 17 signal-mean pairs with |r| > 0.98, mostly constructive
  (adjusted/delta, lazy/travel/minimum families); 6 signal-mean vs proxy
  correlations |r| > 0.95 (radius~CS -1.0, hit window~OD -0.9999,
  preempt~AR -0.999).
- 0 NaN/Inf in every phase, including segment aggregates.

## 12. Known semantic deviations from ppy/osu

1. **Path flattening guards**: upstream flattens unconditionally; v0.2 refuses
   paths above 4096 control points / 5e6 flattening operations and sliders
   above 10k spans / 100k ticks, emitting `None` + provenance instead.
2. **Curved-path numeric parity**: linear geometry matches exactly; Bezier /
   perfect / Catmull are independent reimplementations with documented
   tolerances (golden currently asserts structural values for those curves).
3. **Unmodded only**: all signals assume clock rate 1.0 and no mods.

Full details: [`PPY_PARITY_REPORT_V02.md`](PPY_PARITY_REPORT_V02.md).

## 13. Licensing status

- Independent reimplementation of audited semantics; **no upstream source
  copied verbatim**, no `third_party/` vendoring.
- ppy/osu is MIT; attribution to the pinned commit is recommended.
- A future isolated parity harness must stay out of the profiler runtime
  dependency path.

## 14. Files changed

Implementation:

- `src/osu_skill_profiler/signals/__init__.py` (new)
- `src/osu_skill_profiler/signals/contract.py` (new)
- `src/osu_skill_profiler/signals/extractor.py` (new)
- `src/osu_skill_profiler/signals/path.py` (new)
- `src/osu_skill_profiler/signals/slider.py` (new)
- `src/osu_skill_profiler/cli/main.py` (adds `extract-local-signals`)
- `tests/test_local_signals.py` (new, 33 tests)
- `tools/golden_local_signals.py` (new)
- `tools/local_signal_qa.py` (new; this report also fixes exact
  geometry-blocked counting for older artifacts)

Documentation:

- `docs/LOCAL_SIGNAL_CONTRACT_V02.md` (new)
- `docs/PPY_PARITY_REPORT_V02.md` (new)
- `docs/FEATURE_MIGRATION_V01_TO_V02.md` (new)
- `docs/ARCHITECTURE.md` (updated)
- `README.md` (updated)

## 15. Artifacts generated

Golden:

- `training/datasets/golden_v02/golden_corpus.json`
- `training/datasets/golden_v02/fixtures/*.osu` (20 synthetic fixtures)

Corpus QA (`training/datasets/local_signal_qa/`):

- `local_signal_stats_{5k,20k,full}.json`
- `local_signal_correlations{,_5k,_20k}.json`
- `local_signal_outliers{,_5k,_20k}.jsonl`
- `outlier_summary_{5k,20k,full}.json`
- `local_signal_segment_stats{,_5k,_20k}.json`
- `local_signal_slow_maps{,_5k,_20k}.jsonl`
- `selection_{5k,20k,full}.jsonl`
- `local_signal_qa_{5k,20k,full}.jsonl` (per-object / per-map summaries)
- `LOCAL_SIGNAL_QA_REPORT.md`

## 16. Explicit confirmation

This phase performed:

- **no model training** (no neural network, no LightGBM/XGBoost);
- **no gold/human labels and no pairwise annotation**;
- **no taxonomy freeze** (provisional taxonomy untouched);
- **no WuxinBot integration**;
- **no star-rating / PP clone** (no final evaluator scores, no strain
  aggregation, no performance conversion);
- **no feature deletion or silent clipping/imputation** (the 25 ms delta
  clamp is the official semantic clamp; all other anomalies are
  provenance-tagged);
- **no new beatmap corpus downloads** (real-corpus QA uses the existing local
  126,509-map manifest).

## Verdict

**PASS**

Local Signal Layer v0.2 is implemented, documented, and validated:

- 126/126 unit tests
- 148/148 golden checks
- 5k / 20k / 126,509 full-corpus QA all PASS
- 0 NaN/Inf, 0 failures, 0 ordering/coverage/serialization failures
- v0.1 104-feature contract frozen and unchanged
- all anomalies provenance-tagged, never silently corrected
