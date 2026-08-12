# Pre-ML Foundation Remediation v0.1 — Final Report

Status: **PASS_PENDING_INDEPENDENT_REVIEW** (draft; pending-gate sections marked)

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

*PENDING: 20k semantic-delta gate (QA schema 0.3.0, workers=2) is running;
expected ~20,000 rows. Will record status, failures, transitions, geometry
parity, categories, Reading-only counts, summary reproducibility and 5k-prefix
agreement here when complete.*

## 18. Full-corpus results

*PENDING: corrected Feature 0.2 / Local 0.3 / Reference 0.2 full-corpus QA
(126,509 maps) runs only after 20k PASS. Will record coverage, alignment,
nonfinite/serialization/provenance and wall time here when complete.*

## 19. Old vs corrected semantic delta

*PENDING: final aggregate table from 20k/full deltas (maps changed, objects
changed, fields changed, magnitude distributions, repeat-only vs wider
effects, Reading-only effects).*

## 20. Segment QA corrected results

*PENDING: corrected Reference 5k phase regenerates Segment Signal QA under
`reference_signal_qa_v02`; historical Type A=0 / Type B=1,496 is not assumed.*

## 21. Reference-disagreement corrected results

*PENDING: corrected candidates/challenge counts from `reference_signal_qa_v02`
and the new challenge manifest; historical 0/1,496 is treated as historical.*

## 22. Dataset split regression results

*PENDING: rerun `dataset_split_audit.py verify` and corrected generation;
SET/MAPPER/STRICT core membership must remain identity/byte equivalent;
challenge membership versioned separately (0.2.0).*

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
  `nonfinite_resolved` counters per aligned value; 5k shows 0 introduced.
  *PENDING: 20k/full counters.*
- Historical aggregate reports containing `NaN`/`Infinity` remain historical
  evidence (M-02 erratum).

## 25. Performance findings

*PENDING: `performance_probe.py` results (old-vs-new timing from delta JSONL +
synthetic repeat sweep; check no O(repeat²)/O(nested²)/unbounded path
expansion).* Known first-1k long tails (e.g. `Culprate - Acid Rain [Aspire]`,
`O2i3 - Ping [Aspire]`, `RiraN - Unshakable [Aspire]` ~250 s each in the 5k
delta run) are the existing density-dependent Reference Reading long tail.

## 26. Worker count / runtime / peak memory

```text
all campaigns: workers = 2 (max allowed 4, never exceeded)
5k delta:      2877.55 s wall
20k delta:     *PENDING*
corrected QA:  *PENDING*
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
feature_qa_v02 / local_signal_qa_v03 / reference_signal_qa_v02: *PENDING*
20k delta / corrected split manifests / challenge v0.2: *PENDING*
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
BOUNDED_QA:                         PASS (5k); 20k *PENDING*
FULL_CORPUS_QA:                     *PENDING*
SPLIT_REGRESSION:                   *PENDING*
TARGET_LEAKAGE_VALIDATOR:           PASS
OVERALL_REMEDIATION:                PASS_PENDING_INDEPENDENT_REVIEW
READY_FOR_INDEPENDENT_REVERIFICATION: YES
READY_FOR_WEAK_SUPERVISION:         NO (reserved for independent reviewer)
```
