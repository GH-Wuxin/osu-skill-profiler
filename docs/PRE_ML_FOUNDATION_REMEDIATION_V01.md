# Pre-ML Foundation Remediation v0.1 — Final Report

Status: **PASS_PENDING_INDEPENDENT_REVIEW** (all planned gates passed;
artifacts ready for independent re-verification)

Repository: `osu-skill-profiler`

This report closes the independent red-team audit
[`INDEPENDENT_RED_TEAM_AUDIT_V01.md`](INDEPENDENT_RED_TEAM_AUDIT_V01.md) with
versioned semantic repairs, machine-enforceable target-leakage protection and
regenerated corrected artifacts. It does **not** claim weak-supervision
readiness; that decision is reserved for an independent reviewer.

## 1. Red-team finding inventory

The audit produced four High findings and one High/process finding that were
selected as remediation blockers, plus Medium/Low findings that are either
resolved as part of the versioned repair or tracked as technical debt:

| ID | Severity | Title | Remediation status |
| --- | --- | --- | --- |
| RT-01 (H-01) | High | Repeat-slider total duration compressed to one span | FIXED_PENDING_INDEPENDENT_REVIEW |
| RT-02 (H-02) | High | Local repeat travel bonus uses span count instead of repeat count | FIXED_PENDING_INDEPENDENT_REVIEW |
| RT-03 (H-03) | High | Reference Reading evaluates the wrong object's opacity | FIXED_PENDING_INDEPENDENT_REVIEW |
| RT-04 (H-04) | High | Feature `slider.repeats_*` counts spans as repeats | FIXED_PENDING_INDEPENDENT_REVIEW |
| RT-05 (H-05) | High | Target-leakage readiness is prose-only and stale | FIXED_PENDING_INDEPENDENT_REVIEW |
| M-01 | Medium | QA resume treats failed/incomplete rows as completed | FIXED_PENDING_INDEPENDENT_REVIEW |
| M-02 | Medium | Aggregate QA artifacts are not strict JSON | FIXED_PENDING_INDEPENDENT_REVIEW |
| M-03 | Medium | Local segment consistency excluded from PASS gate | FIXED_PENDING_INDEPENDENT_REVIEW |
| M-04 | Medium | Late real slider tick does not update tracking end | FIXED_PENDING_INDEPENDENT_REVIEW (part of RT-01/02 repair) |
| M-05 | Medium | Split artifacts lack reconstructible source provenance | PARTIALLY_FIXED (milestone commit + versioned metadata) |
| M-06 | Medium | Challenge manifests are not held-out challenge sets | PARTIALLY_FIXED (documented; scoring enforcement is a benchmark-side gate, not implemented) |
| M-07 | Medium | No O(n²) hotspot claim not generally valid | PARTIALLY_FIXED (density-dependent bound documented; see performance section) |
| M-08 | Medium | Repository distribution lacks license grant/attribution | BLOCKED (legal/distribution task outside remediation) |
| M-09 | Medium | Reference-disagreement asymmetry is method-dependent | PARTIALLY_FIXED (method pinned and documented; sensitivity reported) |
| L-01..L-06 | Low | Malformed edges, UTF-8 identity, zero-duration segment, near-duplicate diagnostics, prose inconsistencies, stale docs | PARTIALLY_FIXED / DOC_UPDATE_ONLY; tracked as debt |

## 2. Reproduction result for every blocker

All five blockers were reproduced before repair from the audit evidence and
independent micro-oracles:

| Finding | Reproduced? | Minimal reproduction |
| --- | --- | --- |
| RT-01 | Yes | Two-span slider expected 2,000 ms total; production emitted 1,000 ms |
| RT-02 | Yes | One-repeat expected bonus `max(1, 1^0.3)=1.0`; production `span^0.3=1.231` |
| RT-03 | Yes | Five-object Reading oracle: expected 274.365912, production 360.331117 |
| RT-04 | Yes | One/three-span sliders expected repeats 2/2; production emitted 4/3 |
| RT-05 | Yes | No machine-readable role/lineage gate existed; default weak-label path active |

## 3. Exact root causes

- **RT-01:** `parser/normalized.py` and `signals/slider.py` computed
  `path_distance / velocity` as total slider duration; pinned ppy/osu uses
  `StartTime + SpanCount() * Path.Distance / Velocity`.
- **RT-02:** `signals/extractor.py` applied `span_count ** 0.3`; pinned
  `OsuDifficultyHitObject.TravelDistance` uses `max(1, RepeatCount^0.3)`.
  M-04 was the same file family: `tracking_end_time_ms` was not updated when a
  late real tick moved after the tail-leniency endpoint.
- **RT-03:** `reference/ppy/evaluators.py` called `_opacity_at(loop_obj,
  loop_obj.start_time_ms)`; pinned `ReadingEvaluator` evaluates
  `currObj.OpacityAt(loopObj.BaseObject.StartTime, false)`.
- **RT-04:** `features/extractor.py` summed/maxed the raw `.osu` `slides`
  field (span count) into fields named `slider.repeats_*`.
- **RT-05:** no executable role/lineage registry existed; documentation could
  not reject a leaked feature matrix.

## 4. Slider repeat/span canonical semantics

`src/osu_skill_profiler/slider_semantics.py` is the single machine-readable
canonical contract used by corrected code:

```text
span_count = max(1, parsed_slides)
repeat_count = span_count - 1
single_span_duration_ms = path_distance / velocity
total_slider_duration_ms = single_span_duration_ms * span_count
end_time_ms = start_time_ms + total_slider_duration_ms
```

No corrected code path uses an overloaded `repeats` variable for both
concepts. Non-positive `.osu` span values retain the existing
`slider_slides_nonpositive` provenance and are interpreted as one span.

## 5. Dependency / blast-radius analysis

Corrected slider end/total duration flows through:

```text
.osu slides -> parsed slider -> normalized duration/end_time
  -> Feature 0.2 (duration family, map duration, density, segment boundaries)
  -> Local 0.3 (end_time, span duration, nested events, lazy travel, jump/angle)
  -> Reference 0.2 (preprocess geometry -> Snap/Flow/Agility/Speed/Rhythm/Reading)
  -> segment summaries -> corpus QA -> disagreement/challenge artifacts
```

Non-repeat sliders (`span_count=1`) are numerically unchanged. Repeat sliders
are the affected class; the full historical Local artifact contains
23,964,086 slider rows with p95 span count 2, so this is a common class, not
pathological-only.

## 6. RT-01 repair details

Canonical duration/end-time semantics implemented in
`src/osu_skill_profiler/slider_semantics.py` and consumed by Feature and Local.
Independent regressions cover zero/one/multiple repeats, odd/even parity,
slider-to-circle and slider-to-slider transitions, inherited timing/SV,
old-format, short/long finite and pathological guards. The historical
one-span mutation fails the new tests.

## 7. RT-02 repair details

Local v0.3 travel bonus is `max(1, repeat_count^0.3)`; `ls.slider_repeat_count`
is exposed as the true repeat count and paired with `ls.slider_span_count`.
M-04 is repaired by updating `tracking_end_time_ms` from the last real tick
before tail reordering, matching pinned source. Schema grows 35 -> 38 numeric
fields.

## 8. RT-03 Reading opacity repair details

Reference v0.2 evaluates the **current object's** opacity at each past
object's start time:

```text
currObj.OpacityAt(loopObj.BaseObject.StartTime, false)
```

An identity-sensitive fixture (opacity differs by object identity at the same
timestamp) fails under the v0.1 mutation and passes under v0.2. Reference v0.2
consumes Local v0.3 so corrected geometry precedes evaluation.

## 9. RT-04 Feature versioning decision

Feature v0.1 stays frozen and replayable. Feature v0.2 (106 fields) removes
`slider.repeats_total` / `slider.repeats_max` from the new schema and adds:

| Feature v0.2 field | Corrected value |
| --- | --- |
| `slider.repeat_count_total` | sum of `span_count - 1` |
| `slider.repeat_count_max` | maximum `span_count - 1` |
| `slider.span_count_total` | sum of span counts |
| `slider.span_count_max` | maximum span count |

The legacy names are classified `DEPRECATED_FOR_NEW_MODELS` by the executable
leakage registry and remain replayable only under `FeatureExtractor("0.1.0")`.

## 10. RT-05 target-leakage enforcement

`src/osu_skill_profiler/dataset/leakage.py` implements a default-deny role and
lineage registry with roles equivalent to OBSERVABLE_INPUT_CANDIDATE,
REFERENCE_ONLY, WEAK_LABEL_SOURCE, HUMAN_LABEL, GROUND_TRUTH,
PROVENANCE_ONLY, SPLIT_METADATA and CHALLENGE_SELECTION. Enforcement rejects:

- `ref.ppy.*` as model input;
- deterministic derivatives of a protected target source when lineage is
  declared;
- split identity / split membership and challenge-selection flags as inputs;
- direct target-in-features configurations;
- unknown/unregistered fields promoted to input without policy.

`tools/target_leakage_audit.py` is the hard-fail CLI validator; no warning-only
mode exists for hard leakage.

## 11. Semantic version cascade

| Layer | Historical | Corrected | Cascade reason |
| --- | --- | --- | --- |
| Parser/normalisation | unchanged contract | corrected duration/end semantics | ARTIFACT_REGEN_ONLY |
| Feature | 0.1.0 (104) | 0.2.0 (106) | VERSION_BUMP_REQUIRED |
| Local Signal | 0.2.0 (35) | 0.3.0 (38) | VERSION_BUMP_REQUIRED |
| Reference Signal | 0.1.0 (14) | 0.2.0 (14) | VERSION_BUMP_REQUIRED |
| Segment Signal QA | 0.1 | corrected derived version | ARTIFACT_REGEN_ONLY |
| Dataset split core | v0.1 | v0.1 (unchanged membership) | DOC_UPDATE_ONLY |
| Challenge subsets | v0.1 | v0.2 (corrected inputs) | ARTIFACT_REGEN_ONLY + versioned |
| Target leakage | prose | executable policy v0.1 | NEW |

## 12. Historical artifact preservation policy

Historical artifacts are immutable:

```text
training/datasets/feature_qa/
training/datasets/golden_v02/
training/datasets/local_signal_qa/
training/datasets/golden_reference_v01/
training/datasets/reference_signal_qa/
training/datasets/splits/v01/
```

Corrected artifacts live only under:

```text
training/datasets/feature_qa_v02/
training/datasets/golden_v03/
training/datasets/local_signal_qa_v03/
training/datasets/golden_reference_v02/
training/datasets/reference_signal_qa_v02/
training/datasets/foundation_remediation_v01/
```

Historical checksums continue to identify historical bytes. See
[`PRE_ML_FOUNDATION_ERRATA_V01.md`](PRE_ML_FOUNDATION_ERRATA_V01.md).

## 13. Independent micro-oracle results

The remediation oracle is `tests/test_foundation_remediation_v01.py`; its
expected side does not import the production slider helper. Independent
hand-derived values cover repeat counts, span counts, one-span/total
durations, end times, post-slider deltas, travel semantics, Reading opacity
identity and mutation detection. The corrected golden generators
(`golden_v03`, `golden_reference_v02`) use independent/source-audited expected
values with `UPSTREAM_PARITY_HARNESS = BLOCKED` disclosed.

## 14. Historical-bug detection tests

For each blocker, a bounded mutation check proves the new test detects the
historical failure mode:

- RT-01: old one-span duration FAILS the duration/end-time regression;
- RT-02: span-count bonus FAILS the repeat-bonus regression;
- RT-03: wrong-object opacity FAILS the identity-sensitive fixture;
- RT-04: legacy repeat/span ambiguity is rejected/versioned by schema and
  leakage registry;
- RT-05: leaked target/input configurations FAIL the validator tests.

## 15. Unit / golden results

```text
unit suite:             201/201 PASS (193 baseline + 8 remediation tests)
Corrected Local golden: 155/155 PASS (golden_v03, 20 fixtures)
Corrected Ref golden:   128/128 PASS (golden_reference_v02, 13 fixtures)
target-leakage tests:   PASS
```

## 16. 5k results

Formal 5k semantic-delta gate (QA schema 0.2.0; 0.3.0 counters re-verified as
the 20k prefix):

```text
status: PASS
maps: 5000/5000, failures: 0
new missing: 0, new nonfinite: 0
workers: 2, wall: 2877.55 s
objects: 2,588,481; sliders: 1,015,546; repeat sliders: 124,381
Local changed objects: 237,861
Reference changed objects: 828,496; Reading-only: 478,235
geometry blocked old/new: 637/637 (Local and Reference)
repeat maps: 4,785 (all changed locally); non-repeat maps: 215 (none changed
locally); Reference changed on 4,779 repeat maps and 120 non-repeat maps.
```

Independent integrity audit passed: strict JSON, 5,000 unique IDs, exact
selection order/set, per-row checksums, reproducible summary.

## 17. 20k results

20k semantic-delta gate (QA schema 0.3.0, workers=2, wall 7,979.23 s):

```text
status: PASS
maps: 20000/20000, failures: 0
new missing: 0, new nonfinite: 0, resolved nonfinite: 0
workers: 2, wall: 7979.23 s
objects: 9,361,482; sliders: 3,888,531; repeat sliders: 462,520
Local changed objects: 890,398
Reference changed objects: 3,095,380; Reading-only: 1,834,789
geometry blocked old/new: 642/642 (Local and Reference)
repeat maps: 19,326 (all changed locally); non-repeat maps: 674
(1 changed locally; Reference changed on 19,315 repeat and 485 non-repeat)
```

Independent audit (`audit_delta_20k.py`) PASS: strict JSON, 20,000 unique
sample IDs, exact selection order/checksum identity, 0 failures, 0 missing,
0 introduced nonfinite, 0 resolved nonfinite, geometry parity, repeat/
non-repeat categories, Reading-only counts, deterministic summary
reproducibility and exact 5k-prefix agreement on discrete statistics.

## 18. Full-corpus results

Corrected full-corpus QA (126,509 maps, workers=2), run in gate order:

```text
Feature 0.2 full: PASS
  records 126509/126509, failures 0, feature count 106 stable
  0 NaN/Inf, 0 serialization/consistency failures
  extraction 2824.39 s (44.79 maps/s)
  core (non-pathological) records 126181

Local 0.3 full: PASS
  records 126509/126509, failures 0, feature count 106 stable
  0 NaN/Inf, 0 serialization/ordering/coverage failures
  extraction 9376.81 s (13.49 maps/s); mean latency 145.16 ms,
  p99 512.61 ms, max 140,278 ms (pathological long tail)
  core (non-pathological) records 126181
  geometry-blocked 53 maps / 819 objects (provenance-tagged)
  extreme finite values 545 (provenance-tagged, never clipped)

Reference 0.2 full: PASS
  records 126509/126509, failures 0, nonfinite maps 0
  0 segment alignment/coverage/ordering/serialization failures
  extraction 20932.86 s (3.04 maps/s); mean latency 329.45 ms,
  p99 1415.17 ms, max 280,722.9 ms (pathological long tail)
  geometry-blocked 53 maps / 819 objects (matches Local)
  unavailable rows 2,924,914 (provenance-tagged)
  scaling slopes vs object count: local 0.88-1.23, reference 1.02,
  segment count 1.12 (no quadratic amplification)
```

## 19. Old vs corrected semantic delta

20k aggregate (feature/local/reference, QA schema 0.3.0):

| layer | changed objects | changed maps (repeat) | changed maps (non-repeat) |
| --- | --- | --- | --- |
| Local 0.2 -> 0.3 | 890,398 | 19,326 | 1 |
| Reference 0.1 -> 0.2 | 3,095,380 | 19,315 | 485 |

Reading-only Reference change: 1,834,789 objects. Geometry-blocked sliders
remained exactly 642 old / 642 new in both layers. Per-field magnitude bins,
sums and maxima are recorded in `delta_20000_summary.json`; the full-corpus
aggregate table will be appended after the full gate.

## 20. Segment QA corrected results

Corrected Reference 0.2 5k phase (`reference_signal_qa_v02`) regenerated
Segment Signal QA:

```text
segment alignment failures: 0
sparse segment rate: 0.034568
boundary peak rate: 0.101718
sustained peak maps: 4970
spike preserved maps: snap/agility/flow/speed/rhythm 4972-4985; reading 3805
```

Corrected Reference 0.2 20k phase adds:

```text
segment alignment/ordering/coverage/serialize failures: 0
aggregate nonfinite: 0; empty segments: 0
total segments: 599,250; total objects: 9,361,482
segments per map: mean 29.9625, max 564
```

Corrected Local 0.3 full phase (`local_signal_qa_v03`) segment stats:

```text
total segments: 3,674,160; total objects: 56,547,084
segments per map: mean 29.0427, max 564
objects per segment: mean 14.7258 (mean-of-means), max 546
empty segments: 0; short segments <100ms: 1,174; <1000ms: 10,905
coverage/segment/ordering/serialization failures: 0
segment aggregate nonfinite maps: 0
```

Corrected Reference 0.2 full phase (`reference_signal_qa_v02`) segment stats:

```text
total segments: 3,674,160; total objects: 56,547,084
segments per map: mean 29.0427, max 564 (matches Local 0.3)
empty segments: 0; short segments <100ms: 0; <1000ms: 0
alignment/coverage/ordering/serialization/aggregate failures: 0
aggregate nonfinite: 0
```

The Local 0.3 and Reference 0.2 full phases agree on segment structure
(3,674,160 segments / 56,547,084 objects / 126,509 maps), confirming the
aligned object pipeline is consistent at corpus scale.

## 21. Reference-disagreement corrected results

Corrected Reference 0.2 5k disagreement analysis (`reference_signal_qa_v02`):

```text
disagreement candidates kept: A=0, B=50
```

Historical 0/1,496 was method/version-specific and is treated as historical.
The reference tool generates disagreement candidates from the deterministic
5k object sample (the 20k phase does not regenerate them), so the corrected
candidate file remains A=0, B=50. The v0.2 challenge manifest will be recorded
after the split regeneration.

## 22. Dataset split regression results

`training/datasets/splits/v02` generated with corrected QA versions
(Feature 0.2.0 / Local 0.3.0 / Reference 0.2.0, challenge 0.2.0) and
`dataset_split_audit.py verify` on v02: **VERIFY OK**.

Core membership identity regression: **PASS (identity-equivalent)**.

```text
all four core files: 126,509 rows, same order
identity fields (map/set/mapper keys, checksum class, split assignment):
  0 differences across set_disjoint / mapper_disjoint /
  mapper_disjoint_unknown / strict_disjoint
identity_audit.json: byte-identical to v0.1 (88F7DF3B...)
split counts: identical to v0.1 for every benchmark
source manifest checksum: identical
```

Raw byte comparison differs on 316 rows per core file, and only in the
QA-derived annotation fields `pathological_reasons` / `subset_flags`
(305 rows cleared `qa_short_lt1000ms`, 19 cleared `qa_short_lt100ms`,
0 flags added). This is a direct consequence of the corrected Feature 0.2
duration semantics (RT-01): segment durations changed so those maps no
longer qualify for the short-segment QA flag. No membership, identity or
split assignment changed. v0.1 files remain immutable; the drift is
documented rather than back-filled with stale annotations.

Challenge subsets regenerated under 0.2.0:

```text
legacy_format_ood:              5,113 (same as v0.1)
pathological_challenge:        11,223 (v0.1: 11,527; QA-flag driven)
reference_disagreement_challenge: 41 (same as v0.1; candidates 50)
```

## 23. Target-leakage validator tests

`tests/test_target_leakage.py` covers: observable -> independent future label
PASS; `ref.ppy.*` input -> derived target FAIL; deterministic derivative FAIL;
split membership input FAIL; challenge flag input FAIL; target-in-features
FAIL; reference used only for offline evaluation PASS; unknown field
default-deny FAIL. CLI checks pass.

## 24. NaN/Inf / provenance findings

- Per-map Feature/Local/Reference corrected outputs are finite and strict-JSON
  serializable (full QA gate).
- Aggregate QA writers now use scale-safe statistics and `allow_nan=False`.
- The semantic-delta QA records explicit `nonfinite_introduced` /
  `nonfinite_resolved` counters per aligned value; 5k and 20k both show
  0 introduced / 0 resolved. Local 0.3 full shows 0 NaN/Inf across all
  126,509 maps; Reference 0.2 full shows 0 NaN/Inf across all 126,509 maps.
- Historical aggregate reports containing `NaN`/`Infinity` remain historical
  evidence (M-02 erratum).

## 25. Performance findings

`tools/performance_probe.py` (delta JSONL + synthetic repeat sweep) PASS:

```text
delta 20k new/old timing ratio (20,000 rows):
  local:      median 1.019, p99 1.632, max 2.954
  reference:  median 1.001, p99 1.437, max 2.282
  total:      median 1.003, p99 1.333, max 1.971
synthetic repeat sweep (span 2..1024, single slider):
  log-log slope vs repeat count:
    local old 0.599 / local new 0.636
    reference old 0.662 / reference new 0.658
    feature 0.009
  max nested objects per slider: 1
  verdict: PASS (no O(repeat^2), no unbounded path expansion)
```

Known first-1k long tails (e.g. `Culprate - Acid Rain [Aspire]`, `O2i3 - Ping
[Aspire]`, `RiraN - Unshakable [Aspire]` ~250 s each in the 5k delta run) are
the existing density-dependent Reference Reading long tail; the corrected
repeat traversal adds no quadratic amplification.

## 26. Worker count / runtime / peak memory

```text
all campaigns: workers = 2 (max allowed 4, never exceeded)
5k delta:      2877.55 s wall
20k delta:     7979.23 s wall
corrected QA:  feature 20k extraction 356.43 s (56.11 maps/s); local 20k
               extraction 1091.49 s (18.32 maps/s), report PASS; reference
               20k extraction 2438.00 s (4.16 maps/s), report PASS; full
               campaigns: feature full 2824.39 s (44.79 maps/s) PASS; local
               full 9376.81 s (13.49 maps/s) PASS; reference full 20932.86 s
               (3.04 maps/s) PASS
peak memory:   NOT_MEASURED_MULTIPROCESSING (recorded per campaign summary)
```

## 27. Files changed

Source:

```text
src/osu_skill_profiler/slider_semantics.py            (new canonical contract)
src/osu_skill_profiler/parser/normalized.py
src/osu_skill_profiler/features/{__init__,extractor,schema}.py
src/osu_skill_profiler/signals/{__init__,contract,extractor,slider}.py
src/osu_skill_profiler/reference/ppy/{__init__,contract,evaluators,extractor,preprocess}.py
src/osu_skill_profiler/dataset/{__init__,leakage,split_v01}.py
src/osu_skill_profiler/cli/main.py
src/osu_skill_profiler/segments/{fixed_count,fixed_time}.py
```

Tools/tests/docs:

```text
tools/{feature_qa,local_signal_qa,reference_signal_qa,golden_local_signals,
       golden_reference_signals,foundation_remediation_qa,target_leakage_audit,
       dataset_split_audit}.py
tests/{test_features,test_local_signals,test_reference_signals,
       test_foundation_remediation_v01,test_qa_remediation,
       test_target_leakage,test_dataset_split_v01}.py
docs/{FEATURE_MIGRATION_V01_TO_V02,LOCAL_SIGNAL_CONTRACT_V03,
      PPY_REFERENCE_SIGNAL_CONTRACT_V02,PRE_ML_FOUNDATION_ERRATA_V01,
      TARGET_LEAKAGE_ENFORCEMENT_V01,DATASET_LEAKAGE_THREAT_MODEL_V01,
      DATASET_SPLIT_CONTRACT_V01,DATASET_SPLIT_V01_FINAL_REPORT,
      BENCHMARK_PROTOCOL_V01}.md
.gitignore
```

## 28. New artifact versions / checksums

```text
golden_v03 / golden_reference_v02: PASS (see section 15)
foundation_remediation_v01/delta_5k:
  delta_5000.jsonl       3AE67A6EB93E8DA6383F4676799189B65C62F3876125F8CBF07B38052199326A
  delta_5000_summary.json 42DB9A34CF2D91AD878FF337E335F4715F2403765FF323741B6A0196CB2136D9
foundation_remediation_v01/delta_20k:
  delta_20000.jsonl       D974D8A07B33B3B9D4121B2FA42B0700E6287E407DF40703C67C11139D8602CF
  delta_20000_summary.json 46677103D8D187352E3756CEAE02D46D47C25F3D336B3798C10AF6B6E3A72D67
feature_qa_v02:
  feature_qa_5k.jsonl      27CD071E0589AECB45E9CF0E455E690AA07F3E6330667E8B6AC7AA4D1E09CDC7
  feature_qa_20k.jsonl     A538AC8E4746DDCC6E8682418BF8756CDAC826EE87CE3357F0CDE23A5E5ACA2E
  feature_qa_full.jsonl    6CABF2C7A5E1FD82E75186CD1AA911D4CCC34A98D4220747A459E46EA3D8527C
local_signal_qa_v03:
  local_signal_qa_5k.jsonl  A51980FEA5FCB4B0E4CB0B05234B7D746861F8ED72D478E3EF0F60C7DB16DC1D
  local_signal_qa_20k.jsonl A8B485479E8CB825F6D8A7A7B0084287BE27BB73EA64470FB95BA487A0BABFDD
  local_signal_qa_full.jsonl 787F9D02B02883F92872A08445F27FC473410E2E24063FA2D0112713A3CB1AD0
  local_signal_stats_full.json 2C25FD2DA6B61C5264C81C8D1A853936713C219F8E70E5C5C6200CC0DD25AA93
  local_signal_correlations.json D8F7C68A873A16058CBC2B5C3C241D6686054E60BDF0210AE44DA86C01912A90
  local_signal_segment_stats.json A416F5D008A5AD28927578C918E7644DF154A2E3E068A942164DEAC222D7E731
  local_signal_slow_maps.jsonl BE244CC672A21C9B7D00F9271164EF874237BDFC4C812E6409D06233701E76EA
  local_signal_outliers.jsonl 96B9DB6E2A5EABF96E225EC17C15D8FEA9A86E5E8D790E5223AD0F2A6CC19EBA
reference_signal_qa_v02:
  reference_qa_5k.jsonl    823B0C51952D402B3D937892524D17AAD1F4091A92769401E2EB3A3CA4A92A6B
  reference_qa_20k.jsonl   7A0871784BE1FD48E349246E32043C31B5269B11E0741D7EDFB441F35ED7390C
  reference_qa_full.jsonl  425B05DD1672305F0BD768E3591AAFCEBA9A08B75F5D844656899C4E1F1A86A19
  reference_qa_stats.json  E5E42949E79B1F8517CF9CA3AE31E062FDA303D9842F224937B5321086CF2651
  REFERENCE_QA_REPORT.md   0ADD6F043F565D06A708F283CA5085481D863E377E10700326A633B8934120BF
split v0.2:
  set_disjoint.jsonl        78F5DCEA558097D105E0ABB8614050DC3F9AEFCAAF7B04C8DDC711D0136D8806
  mapper_disjoint.jsonl     C0136CB0FF2E40AF7AF89E86AFB3ACE4509C22BCE8E72566A5F7856FAB324957
  mapper_disjoint_unknown.jsonl E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855
  strict_disjoint.jsonl     A8648A4CE7BE30DA767496A28DE0CE587F322AEA5B4F8E30B7406B70C1E5FB52
  legacy_format_ood.jsonl   89AD5866BF0AC9D36C0EEA6D575E648A05F67F18095A305AB9A71E5551CDB725
  pathological_challenge.jsonl 858CF9D33A54D49204313F4019280CA9FC738241C825452FB0A79AA942C09B93
  reference_disagreement_challenge.jsonl D2213730CE84F74F13FA9F7D02C67BC725650E75878F6472B04D1589A9D15EF6
  distribution_audit.json   AE8A25FF91CA591D797A102F5776F49A07F24CFB5E9911DC649BF51990CD59A0
  identity_audit.json       88F7DF3BCD745DE082262AB9884C9DEE8100C4FFD9DDC763970FB8654296FE5B
  summary.json              091ACA9EE8B36B7250E3F8E3B84067AE5BF97CBBD84789942E2754211FA6EC0A
  manifest.json             B324E64374D11098199AA00D0961A178C2FA829496FE741E19CDFD934084E492
```

## 29. Old artifacts retained

All historical directories listed in section 12 remain untouched. The
independent red-team audit report is byte-identical to the handoff-time hash
`3A98704BBFD03FCA294CBDA94B6BC0B80CE9F9FC39CA2DF0CF377DE3BFB5719C`.

## 30. Documentation created / updated

Created/updated contracts, errata, leakage enforcement, split/benchmark
documentation and this report; see section 27. The red-team audit was not
modified.

## 31. Remaining blockers

- Executable upstream parity remains `BLOCKED` (no .NET SDK; out of scope by
  design).
- Licensing/attribution (M-08) remains blocked pending legal review.
- Held-out challenge scoring enforcement (M-06) remains a benchmark-side
  gate, not implemented in this remediation.
- Independent re-verification has not yet returned.

## 32. Technical debt

- NAME_ONLY mapper identity remains provisional; creator IDs unavailable.
- Near-duplicate detection remains a lightweight diagnostic (L-04).
- Malformed-value provenance policy is partially explicit (L-01).
- Zero-duration terminal segment semantics remain documented, not redesigned
  (L-03).
- Public README/CLI docs still contain stale text (L-06) pending the final
  report cycle.

## 33. Explicit confirmations

```text
red-team audit report not modified:            YES
old versioned artifacts not overwritten:       YES
Feature v0.1 historical semantics preserved:   YES
Local v0.2 historical semantics preserved:     YES
Reference v0.1 historical semantics preserved: YES
no training:                                   YES
no weak labels:                                YES
no taxonomy:                                   YES
no active learning:                            YES
no WuxinBot work:                              YES
no deployment:                                 YES
no commit (remediation code):                  YES (milestone commit was an
                                               explicit user request; data and
                                               tmp excluded)
workers <= 4:                                  YES
```

## Final statuses

```text
RT_01_REPEAT_SLIDER_DURATION:       FIXED_PENDING_INDEPENDENT_REVIEW
RT_02_REPEAT_SPAN_SEMANTICS:        FIXED_PENDING_INDEPENDENT_REVIEW
RT_03_READING_OPACITY:              FIXED_PENDING_INDEPENDENT_REVIEW
RT_04_FEATURE_REPEAT_CONTRACT:      FIXED_PENDING_INDEPENDENT_REVIEW
RT_05_TARGET_LEAKAGE_ENFORCEMENT:   FIXED_PENDING_INDEPENDENT_REVIEW
VERSIONING_INTEGRITY:               PASS
BOUNDED_QA:                         PASS (5k + 20k)
FULL_CORPUS_QA:                     PASS (feature/local/reference 126,509)
SPLIT_REGRESSION:                   PASS (identity-equivalent; QA annotation
                                    drift documented, see section 22)
TARGET_LEAKAGE_VALIDATOR:           PASS
OVERALL_REMEDIATION:                PASS_PENDING_INDEPENDENT_REVIEW
READY_FOR_INDEPENDENT_REVERIFICATION: YES
READY_FOR_WEAK_SUPERVISION:         NO (reserved for independent reviewer)
```
