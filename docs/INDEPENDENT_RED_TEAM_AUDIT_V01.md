# Independent Red-Team Audit v0.1

Date: 2026-08-11

Audit role: independent pre-ML foundation review

Repository: `osu-skill-profiler`

Audited branch / HEAD: `main` / `07dcfe73466fa3a7a45d0e28ad938914624582b0`

## Executive Summary

The repository has a substantial amount of sound engineering evidence: the
126,509-row Feature, Local and Reference JSONL artifacts reconcile
independently; their per-map outputs are finite; the declared schema sizes and
version pins are internally consistent; and the three v0.1 split policies pass
an independent implementation of their stated checksum, set and mapper
isolation rules.

Those results are not sufficient to approve the foundation for weak
supervision. Independent source-derived oracles found four core semantic
errors:

1. repeat-slider total duration is compressed to one-span duration in both the
   frozen Feature layer and Local Signal layer;
2. Local repeat travel applies a span-count bonus where pinned ppy/osu applies
   a repeat-count bonus;
3. Reference Reading evaluates the previous object's opacity instead of the
   current object's opacity at the previous object's time; and
4. Feature v0.1 fields named `slider.repeats_*` count spans, not repeats.

These are shared-assumption failures: current tests, golden expectations and/or
contracts encode the same mistakes, so their PASS status did not detect them.
The highest-risk unresolved issue is the repeat-slider duration defect because
it crosses Feature, Local and Reference preprocessing and affects a common,
not merely pathological, object class.

The split membership guarantees themselves are independently verified, but
the pre-training leakage posture is not ready. The target-leakage policy is
prose-only, no machine-readable input/target partition gate exists, and its
claim that no weak labels are generated is already stale relative to the
default baseline and CLI behavior.

```text
FOUNDATION_CORRECTNESS: BLOCKED
READY_FOR_WEAK_SUPERVISION: NO
```

No model training, taxonomy work, remediation, deployment or source-code
modification was performed by this audit.

## Scope and Method

The audit covered phases A-Q from repository provenance through parser,
Feature v0.1, Local Signal v0.2, Reference Signal v0.1, numerical safety,
full-corpus QA, segmentation, disagreement selection, identity, splitting,
benchmark validity, target leakage, licensing, performance and documentation.

Evidence was classified as:

- `DIRECTLY_VERIFIED`: independently recomputed or compared to the primary
  source without using the production expected-value implementation;
- `STRONGLY_SUPPORTED`: multiple independent artifacts support the claim but a
  complete upstream executable parity oracle was unavailable;
- `PARTIALLY_SUPPORTED`: a material part of the claim passes while important
  caveats or gaps remain;
- `UNVERIFIED`: evidence is absent or insufficient;
- `CONTRADICTED`: direct evidence falsifies the claim.

The audit deliberately did not rerun full extraction. It streamed the existing
large JSONL artifacts, created bounded independent micro-oracles, decoded and
checked pinned upstream Git blobs, generated adversarial synthetic maps, and
used one-worker bounded performance probes. Independent expected formulas did
not import the production evaluator under test.

Primary audit evidence is retained under ignored local paths:

- `tmp/red-team-v01/independent_split_audit.json`
- `tmp/red-team-v01/independent_corpus_audit.json`
- `tmp/red-team-v01/micro_oracle.json`
- `tmp/red-team-v01/transcription_oracle.json`
- `tmp/red-team-v01/adversarial_boundaries.json`
- `tmp/red-team-v01/independent_disagreement_sensitivity.json`
- `tmp/red-team-v01/performance_oracle.json`
- pinned source snapshots under `tmp/ppy-osu-pinned/`

## Repository State and Provenance

At audit start and report preparation:

```text
branch: main
HEAD:   07dcfe73466fa3a7a45d0e28ad938914624582b0
tests:  159/159 PASS
```

The following worktree state pre-dated the audit and was not modified:

```text
 M .gitignore
?? docs/BENCHMARK_PROTOCOL_V01.md
?? docs/DATASET_LEAKAGE_THREAT_MODEL_V01.md
?? docs/DATASET_SPLIT_CONTRACT_V01.md
?? docs/DATASET_SPLIT_V01_FINAL_REPORT.md
?? src/osu_skill_profiler/dataset/split_v01.py
?? tests/test_dataset_split_v01.py
?? tools/dataset_split_audit.py
```

The tracked signal implementation and reports are attributable to HEAD. The
split report is not exactly reproducible from Git alone: the split generator,
tests, contract, threat model, benchmark protocol and final report are all
untracked, while generated metadata records only the dirty HEAD and not hashes
of those dirty source files. The local worktree may be internally coherent,
but Git cannot reconstruct the exact generator that produced the published
split artifacts.

Package, public schema, Feature and Reference versions are consistently
declared at `0.1.0`; Local Signal is `0.2.0`. The Reference contract pins
ppy/osu commit `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e` and difficulty version
`20260706`. The audited upstream blobs match the hashes recorded in the formal
reference report. `UPSTREAM_EXECUTABLE_PARITY = BLOCKED` is accurately
disclosed and is not itself a new defect.

## A-Q Evidence Matrix

| Phase | Classification | Independent result |
| --- | --- | --- |
| A. Repository state / provenance | `PARTIALLY_SUPPORTED` | Tracked signal work is attributable to HEAD; current split implementation and reports are untracked and not content-hashed in generated provenance. |
| B. Test independence | `CONTRADICTED` | Repeat duration, repeat bonus and Reading show that implementation, tests/goldens and contract text can share the same wrong transcription. |
| C. Parser / normalisation | `PARTIALLY_SUPPORTED` | Missing Mode, timing inheritance, SV and ordering semantics pass; malformed negative values and replacement decoding have unmarked semantic consequences. |
| D. Feature v0.1 | `CONTRADICTED` | The 104-field count and determinism pass, but repeat duration and `slider.repeats_*` semantics are wrong under the frozen version. |
| E. Local Signal v0.2 | `CONTRADICTED` | Many primitives pass independent formulas, but repeat-slider timing, travel bonus and late-tick tracking diverge from pinned ppy/osu. |
| F. Reference Signal v0.1 | `CONTRADICTED` | Simple Snap/Agility/Flow/Speed/Rhythm checks pass; Reading contains a direct source transcription error and consumes defective Local geometry. |
| G. Numerical safety | `PARTIALLY_SUPPORTED` | Per-map production values remain finite and strict-JSON safe in bounded extremes; aggregate QA reports contain `NaN`/`Infinity`. |
| H. Full-corpus QA claim | `CONTRADICTED` | Counts reconcile, but resume can skip failed/incomplete rows and Local's declared segment consistency is not part of the PASS gate. |
| I. Segment representation | `PARTIALLY_SUPPORTED` | 5 s assignment and indices pass exact boundary oracles; a final boundary object can create a zero-duration segment and one validation flag is ignored. |
| J. Reference disagreement | `PARTIALLY_SUPPORTED` | Published 0 A / 1,496 B reproduces for its exact method; the asymmetry changes materially under reasonable percentile/saturation choices. |
| K. Dataset identity | `PARTIALLY_SUPPORTED` | Checksum identity and set fallback are internally consistent; mapper identity is provisional name-only and near-duplicate detection is diagnostic only. |
| L. Split algorithm | `DIRECTLY_VERIFIED` | Independent code found exact coverage and no checksum/set/mapper crossings; content hashes and deterministic regeneration match. |
| M. Benchmark validity | `CONTRADICTED` | Core split manifests are usable, but every challenge manifest contains training rows and test-only challenge scoring is not machine-enforced. |
| N. Target leakage | `CONTRADICTED` | Policy identifies the right threats but is prose-only and stale relative to already-active weak-label generation. |
| O. Licensing / attribution | `CONTRADICTED` | MIT is declared, but no root license grant exists and the direct `DiffUtils` adaptation lacks the upstream notice. |
| P. Performance / complexity | `CONTRADICTED` | A bounded same-time-object probe scales approximately quadratically, contradicting the general “no O(n²) hotspot” statement. |
| Q. Documentation / code consistency | `CONTRADICTED` | Multiple public docs are stale or stronger than code/artifacts: split method, CLI, counts, weak-label state, QA JSON and paths. |

## Findings by Severity

### Critical

No critical finding was confirmed. The independent split audit did not find
systematic checksum, set or mapper crossing, and no trained model or claimed
ground truth currently exists. The issues below are nevertheless sufficient to
block the foundation before weak supervision.

### High

#### H-01 — Repeat-slider total duration is systematically compressed

- **Claim:** Feature and Local slider duration represent
  `Slider.EndTime - Slider.StartTime` and match pinned ppy/osu semantics.
- **Evidence:** pinned `Slider.cs:28` computes
  `StartTime + SpanCount() * Path.Distance / Velocity`, and `Slider.cs:91`
  derives `SpanDuration` from total duration. Production
  `parser/normalized.py:59-66` and `signals/slider.py:219-226` compute only
  `path_distance / velocity`; Local then divides that value by `span_count`.
  The decoded pinned `IHasRepeats` blob defines span count as repeat count + 1.
  `transcription_oracle.json` shows a two-span slider expected at 2,000 ms and
  a three-span slider expected at 3,000 ms; Feature and Local emit 1,000 ms for
  both.
- **Why it matters:** this corrupts Feature slider duration and map end time,
  Local end time, span duration, nested event timing, lazy travel, subsequent
  end-delta/jump/angle primitives and Reference inputs built from Local
  geometry.
- **Scope:** the full Local artifact contains 23,964,086 slider rows;
  `ls.slider_span_count` has mean 1.168197, p95 2, p99 3, p99.9 7 and maximum
  2,048. Repeat sliders are common enough that this is not a pathological-only
  issue.
- **Reproduction:** run `tmp/red-team-v01/transcription_oracle.py`; inspect
  `repeat_slider_2_span` and `repeat_slider_3_span`.
- **PASS impact:** invalidates the semantic portion of Feature v0.1 and Local
  v0.2 PASS. Existing `tests/test_local_signals.py:187-199` explicitly expects
  the erroneous 1,000 ms for a two-span slider, proving a shared assumption.
- **Remediation direction:** correct total/span duration against upstream,
  version affected contracts, independently regenerate expected values and
  assess all downstream artifacts. No remediation was applied here.

#### H-02 — Local repeat travel bonus uses span count, not repeat count

- **Claim:** `ls.travel_distance_cs_normalised` follows
  `OsuDifficultyHitObject.TravelDistance`.
- **Evidence:** pinned `OsuDifficultyHitObject.cs:203` multiplies lazy travel by
  `max(1, RepeatCount^0.3)`. Production `signals/extractor.py:84-89` uses
  `geometry.span_count ** 0.3`. The independent oracle gives expected/actual
  bonuses of 1.0/1.231144 for one repeat and 1.231144/1.390389 for two repeats.
  `LOCAL_SIGNAL_CONTRACT_V02.md:164-167` conflates span and repeat semantics.
- **Why it matters:** the observable travel signal is systematically inflated
  for repeat sliders, contaminating downstream comparisons and potential weak
  labels.
- **Scope:** all repeat sliders with a valid lazy path.
- **Reproduction:** run `tmp/red-team-v01/transcription_oracle.py` and inspect
  `local_repeat_bonus` versus `upstream_expected_repeat_bonus`.
- **PASS impact:** invalidates the relevant Local semantic golden/PASS despite
  finite and deterministic output.
- **Remediation direction:** distinguish repeat count from span count in the
  signal contract and expected-value oracle, then re-version/recompute affected
  artifacts.

#### H-03 — Reference Reading evaluates the wrong object's opacity

- **Claim:** `ref.ppy.reading` is a source-audited transcription of pinned
  `ReadingEvaluator`.
- **Evidence:** pinned `ReadingEvaluator.cs:149` evaluates
  `currObj.OpacityAt(loopObj.BaseObject.StartTime, false)`. Production
  `reference/ppy/evaluators.py:616-637` calls
  `_opacity_at(loop_obj, loop_obj.start_time_ms)`, which is effectively 1 for
  every past object. A five-object independent oracle yields expected past
  influence 3.5 and Reading 274.365912 versus production influence 5.0 and
  Reading 360.331117, a 31.3% overstatement.
- **Why it matters:** Reading's history-density term is systematically wrong in
  ordinary overlapping-preempt windows, not only at numerical extremes.
- **Scope:** any object with visible past objects in the Reading look-back
  window.
- **Reproduction:** run `tmp/red-team-v01/transcription_oracle.py`; inspect
  `reading_past_opacity`.
- **PASS impact:** invalidates Reference Reading's semantic PASS and proves all
  source-audited golden checks can pass while the implementation and manually
  transcribed expectation share a source-reading mistake.
- **Remediation direction:** rebuild the expected side directly from pinned
  source, add an independent opacity fixture, version/recompute Reference
  Reading outputs, and reassess disagreement/benchmark artifacts.

#### H-04 — Frozen Feature `slider.repeats_*` fields count spans as repeats

- **Claim:** `slider.repeats_total` and `slider.repeats_max` measure repeat
  counts (`FEATURE_CONTRACT_REVIEW_V0.md:200-201`).
- **Evidence:** `.osu` hit-object `slides` is the number of spans. Production
  `features/extractor.py:197-199` sums/maxes raw `slider_slides`. For sliders
  with one and three spans, the independent expected repeat total/max are 2/2;
  production emits 4/3. `tests/test_features.py:28` asserts only that the total
  is positive.
- **Why it matters:** two named, frozen v0.1 features have different semantics
  from their contract, and non-repeating sliders contribute one “repeat.”
- **Scope:** every slider-containing map.
- **Reproduction:** run `tmp/red-team-v01/micro_oracle.py`; its two deliberate
  failures are `feature.slider.repeats_total.semantic` and
  `feature.slider.repeats_max.semantic`.
- **PASS impact:** contradicts the claim that all 104 frozen features are
  semantically correct; field-count and determinism PASS remain true.
- **Remediation direction:** decide whether to correct and version the fields
  or rename/document historical semantics; do not silently alter v0.1.

#### H-05 — Target-leakage readiness is prose-only and already stale

- **Claim:** no weak labels are generated and future target/input separation
  will be added before training (`DATASET_LEAKAGE_THREAT_MODEL_V01.md:177-189`,
  `BENCHMARK_PROTOCOL_V01.md:97-101`).
- **Evidence:** three conservative weak rules exist;
  `DeterministicBaselineProfiler` defaults `run_weak_labels=True`
  (`models/baseline.py:33-41`) and applies them at lines 75-88. `profile-map`
  enables this unless `--no-weak-labels` is supplied
  (`cli/main.py:94-100`). No machine-readable feature-role/input-target
  partition or training gate was found; the split verifier validates grouping
  and artifact structure, not algebraic target leakage.
- **Why it matters:** a future pipeline can place a reference or observable
  signal, or a deterministic transform of it, on both sides of the learning
  problem while all current split checks pass.
- **Scope:** any future weak-label, pseudo-label or model-input assembly.
- **Reproduction:** instantiate the baseline with defaults or run
  `profile-map` without `--no-weak-labels`; inspect emitted `weak_labels`, then
  inspect the absence of a machine-readable partition verifier.
- **PASS impact:** does not prove current trained-model leakage because no
  trained model exists; it blocks the claimed readiness to begin weak
  supervision.
- **Remediation direction:** first reconcile the documented current state,
  then introduce a versioned role registry, label provenance ledger and
  enforced input/target partition check before any training run.

### Medium

#### M-01 — QA resume treats failed and incomplete rows as completed

- **Claim:** resumed full-corpus QA safely completes any missing work.
- **Evidence:** Feature, Local and Reference runners add every parseable row
  containing `sample_id` to `done` without checking `ok` or required schema
  (`feature_qa.py:389-399`, `local_signal_qa.py:428-438`,
  `reference_signal_qa.py:463-473`). Adversarial fixtures show both
  `{"sample_id":"audit-resume","ok":false}` and a lone `sample_id` are
  permanently skipped; only truncated invalid JSON is retried.
- **Impact/scope:** interrupted or transiently failed runs can produce a
  superficially complete resumed artifact that silently retains failure or
  incomplete rows.
- **Reproduction:** run `tmp/red-team-v01/adversarial_boundaries.py`; inspect
  `resume.feature`, `resume.local` and `resume.reference`.
- **PASS impact:** weakens provenance of any artifact produced with resume; it
  does not by itself show that the current three full JSONLs contain failures
  (independent streaming found none).
- **Remediation direction:** define completeness per schema and only mark
  successful, complete records done; validate final identity coverage.

#### M-02 — Aggregate QA artifacts are not strict JSON

- **Claim:** QA outputs demonstrate zero NaN/Inf and are JSON reports.
- **Evidence:** `feature_stats_full.json` contains multiple bare `Infinity`
  values, `local_signal_stats_full.json` contains `NaN` and `Infinity`, and
  `reference_qa_stats.json` contains `Infinity`. Their writers use Python's
  default `json.dumps(..., allow_nan=True)` (for example
  `feature_qa.py:947-951`, `local_signal_qa.py:1039-1044`). Strict parsers
  reject those tokens.
- **Impact/scope:** QA/report consumers cannot rely on standard JSON, and
  aggregate numerical overflow is hidden behind a per-map “0 NaN/Inf” claim.
- **Reproduction:** grep the three files for `NaN|Infinity`, or parse with a
  strict JSON implementation.
- **PASS impact:** per-map signal outputs remain finite and independently
  strict-serializable; the defect invalidates only aggregate QA/report safety.
- **Remediation direction:** use scale-safe streaming statistics and
  `allow_nan=False`, recording an explicit failure rather than emitting
  non-standard tokens.

#### M-03 — Local segment consistency is computed but excluded from PASS

- **Claim:** Local full-corpus QA has zero segment consistency failures.
- **Evidence:** `_segment_validation()` emits both `segment_consistent` and
  `coverage_consistent` (`local_signal_qa.py:303-304`), but rollup checks only
  `coverage_consistent` (`local_signal_qa.py:591-593`). Independent streaming
  found 56,841 maps with `segment_consistent=false` while all remained
  `ok=true`.
- **Impact/scope:** a declared validation result is silently ignored by the
  PASS gate. Replaying the first case showed only a `2.842e-14` p90-over-max
  ordering difference, so the observed population is likely scale/tolerance
  noise rather than signal corruption; the gate is still not testing what its
  report claims.
- **Reproduction:** stream
  `training/datasets/local_signal_qa/local_signal_qa_full.jsonl` and count
  `validation.segment_consistent == false` versus `ok`.
- **PASS impact:** contradicts “0 consistency failures” as stated; does not
  establish 56,841 materially wrong maps.
- **Remediation direction:** specify a scale-aware tolerance and make the
  declared invariant part of the rollup, or remove/relabel it explicitly.

#### M-04 — Late real slider tick does not update tracking end

- **Claim:** Local lazy slider tracking follows pinned
  `OsuDifficultyHitObject` tail-leniency behavior.
- **Evidence:** pinned `OsuDifficultyHitObject.cs:306-308` assigns
  `trackingEndTime = lastRealTick.StartTime` before reordering. Production
  `signals/slider.py:301-310` reorders the tick but does not update
  `tracking_end_time_ms`. The oracle expects 625 ms lazy travel time and gets
  619 ms.
- **Impact/scope:** bounded timing error for sliders whose last real tick lands
  after the tail-leniency endpoint.
- **Reproduction:** run `tmp/red-team-v01/transcription_oracle.py`; inspect
  `last_real_tick_tracking_end`.
- **PASS impact:** invalidates this Local edge semantic despite current golden
  PASS.
- **Remediation direction:** add a pinned-source-derived boundary fixture and
  reassess affected Local outputs after the core duration fix.

#### M-05 — Split artifacts lack reconstructible source provenance

- **Claim:** v0.1 splits are deterministically regenerable from their recorded
  version/HEAD.
- **Evidence:** the current split implementation, verifier, tests, contract,
  threat model, protocol and final report are all untracked. Generated metadata
  records the dirty HEAD but not hashes of those source files.
- **Impact/scope:** current local regeneration is deterministic, but another
  checkout cannot recover the exact generator from the published provenance.
- **Reproduction:** compare `git status --short`, HEAD, and the split summary's
  source metadata.
- **PASS impact:** no split crossing was found; this is a reproducibility and
  audit-chain failure, not evidence of leakage.
- **Remediation direction:** version the split implementation/contracts and
  record content hashes for every dirty or external generator input.

#### M-06 — Challenge manifests are not held-out challenge sets

- **Claim:** `LEGACY_FORMAT_OOD`, `PATHOLOGICAL_CHALLENGE` and
  `REFERENCE_DISAGREEMENT_CHALLENGE` support benchmark challenge reporting.
- **Evidence:** independent manifest joins found train/val/test rows of
  4,154/520/439 for Legacy, 9,241/1,069/1,217 for Pathological and 33/4/4 for
  Reference Disagreement. The protocol does not machine-enforce test-only
  challenge scoring.
- **Impact/scope:** treating an entire challenge file as evaluation data would
  directly score training examples and overstate generalisation.
- **Reproduction:** run `tmp/red-team-v01/independent_split_audit.py`; inspect
  `challenges.*.split_counts`.
- **PASS impact:** core split isolation remains valid; challenge benchmark
  validity is blocked until evaluation selection is explicit and enforced.
- **Remediation direction:** make challenge membership orthogonal to split and
  require `split == test` at scoring time, with a verifier gate.

#### M-07 — “No O(n²) hotspot” is not generally valid

- **Claim:** Reference extraction has no quadratic hotspot
  (`PPY_REFERENCE_SIGNAL_V01_FINAL_REPORT.md:106-113`).
- **Evidence:** Reading performs backward and forward time-window scans per
  object (`evaluators.py:616-656`). Those windows are time-bounded, not
  object-count-bounded. The final same-time-circle replay measured medians of
  0.295 s at 250 objects, 1.088 s at 500 and 4.574 s at 1,000, with empirical
  doubling exponents 1.88 and 2.07. An earlier replay measured 2.22 and 2.03;
  both show the expected near-quadratic dense case. Existing real-corpus report
  already shows a maximum 436.867 s/map. QA also computes Local once directly
  and again inside Reference preprocessing.
- **Impact/scope:** dense/pathological maps can make extraction operationally
  expensive and threaten campaign usability, though no per-map semantic error
  follows solely from latency.
- **Reproduction:** run `tmp/red-team-v01/performance_oracle.py`.
- **PASS impact:** contradicts the general complexity claim; ordinary-corpus
  median performance evidence remains valid.
- **Remediation direction:** document the density-dependent bound, establish
  a performance budget and profile before optimisation.

#### M-08 — Repository distribution lacks sufficient license grant/attribution

- **Claim:** the project is MIT and its ppy/osu-derived layer has adequate
  attribution.
- **Evidence:** `pyproject.toml:11` and `README.md:143-146` declare MIT, but no
  root `LICENSE`/`LICENCE` file is present. `reference/ppy/diff_utils.py:1-8`
  identifies a direct adaptation but does not carry the ppy Pty Ltd copyright
  and MIT notice. The project's own final report at lines 164-170 says a NOTICE
  should be added when distributed.
- **Impact/scope:** public distribution does not currently provide the stated
  project license grant or clearly preserve the adapted upstream notice.
- **Reproduction:** list repository root license files and inspect
  `diff_utils.py` plus pinned `tmp/ppy-osu-pinned/LICENCE`.
- **PASS impact:** no numerical signal is invalidated; distribution readiness
  is blocked.
- **Remediation direction:** add the intended project license and preserve the
  applicable upstream notice/attribution after legal review.

#### M-09 — Reference-disagreement asymmetry is method-dependent

- **Claim:** Type A = 0 and Type B = 1,496 is a meaningful stable description
  of the sampled disagreement space.
- **Evidence:** the exact published seed/method reproduces 0/1,496. Dropping
  the saturated `ls.double_tap_feasibility` observable yields 40 Type A;
  treating percentile cutoffs numerically yields 1,571 Type A; an alternate
  seed retains strict 0/1,534. The published reservoir step uses
  `randrange(seen)` after filling rather than standard Algorithm R's range over
  `seen + 1`.
- **Impact/scope:** the existence of Type B candidates is supported, but the
  claimed one-sided absence of Type A is not robust to obvious methodological
  choices.
- **Reproduction:** run
  `tmp/red-team-v01/independent_disagreement_sensitivity.py`.
- **PASS impact:** candidate files remain reproducible for the declared method;
  interpretation must remain diagnostic and non-taxonomic.
- **Remediation direction:** pre-register percentile/tie/saturation handling,
  correct or explicitly freeze the sampler, and publish sensitivity ranges.

### Low

#### L-01 — Malformed gameplay values can succeed without consistent provenance

- **Claim:** parse success yields semantically usable finite objects or marks
  exceptional handling.
- **Evidence:** a spinner ending before it starts is accepted without a flag;
  zero/negative slider spans are clamped to one with provenance; negative
  slider length is accepted, yields negative normalized duration and collapses
  Local geometry to zero. Non-finite times and zero beat-length timing points
  are correctly rejected.
- **Impact/scope:** rare malformed maps can enter the valid path with
  inconsistent semantics.
- **Reproduction:** run `tmp/red-team-v01/adversarial_boundaries.py`; inspect
  `parser.spinner_end_before_start` and `slider_degenerate_values`.
- **PASS impact:** bounded malformed-edge caveat; no evidence that normal corpus
  maps are broadly corrupted.
- **Remediation direction:** define reject/clamp/provenance policy per malformed
  field and test it independently.

#### L-02 — Invalid UTF-8 replacement can merge provisional mapper identities

- **Claim:** name-only mapper grouping conservatively represents mapper
  identity.
- **Evidence:** parser replacement decoding maps distinct invalid byte
  sequences to the same replacement-character creator string without
  provenance. SHA-256 map identity remains distinct, but normalized NAME_ONLY
  grouping can merge creators.
- **Impact/scope:** conservative over-grouping can move unrelated maps together;
  it does not cause the same mapper group to cross a split.
- **Reproduction:** inspect `invalid_utf8_replacement` in
  `adversarial_boundaries.json`.
- **PASS impact:** split isolation under the produced group keys still passes;
  real-world mapper identity remains provisional.
- **Remediation direction:** retain decoding provenance and require reliable
  creator IDs before treating mapper-disjoint scores as final.

#### L-03 — Fixed-window final boundary can produce a zero-duration segment

- **Claim:** fixed 5 s segments have meaningful non-empty durations.
- **Evidence:** an object exactly at the final 5,000 ms boundary is assigned
  exactly once but can produce `start_ms == end_ms`; density calculations use
  a `1e-9` floor. Full QA reports minimum duration 0.0.
- **Impact/scope:** final-segment density can become artificial on exact-boundary
  maps.
- **Reproduction:** run `tmp/red-team-v01/micro_oracle.py`; inspect
  `segment.last_duration_positive`.
- **PASS impact:** assignment, coverage and index semantics still pass.
- **Remediation direction:** specify end-boundary semantics and exclude or
  represent zero-duration terminal buckets explicitly.

#### L-04 — Near-duplicate detection is only a weak diagnostic

- **Claim:** near-duplicate risk is audited before benchmarking.
- **Evidence:** the tool buckets exact normalized artist/title/mapper, compares
  equal object count and duration within 5%, caps large buckets to their first
  200 records and retains 200 examples. It computes no gameplay/content
  fingerprint (`dataset_split_audit.py:342-407`). The docs correctly call this
  lightweight, but it cannot support a no-near-duplicate-leakage guarantee.
- **Impact/scope:** structurally similar maps outside shared set/checksum groups
  may cross splits undetected.
- **PASS impact:** no declared hard split constraint is falsified; benchmark
  independence is only partially supported.
- **Remediation direction:** add a versioned gameplay/content similarity
  diagnostic before making stronger benchmark claims.

#### L-05 — Split counts and weighting prose contain small inconsistencies

- **Claim:** split docs exactly describe manifest counts and assignment weight.
- **Evidence:** raw manifest has 105,155 BeatmapSetID-present rows and 21,354
  fallbacks; the threat model says 105,153/21,356. Assignment weights are
  125,988 unique checksums although prose refers to cumulative map count. A
  row-weight counterfactual changes 20-32 unique memberships without violating
  leakage constraints.
- **Impact/scope:** documentation/reproducibility precision, not isolation.
- **Reproduction:** inspect `manifest` and `row_weight_counterfactual` in
  `independent_split_audit.json`.
- **PASS impact:** independent split PASS remains intact.
- **Remediation direction:** align terms and counts with the exact algorithm.

#### L-06 — Public documentation contains stale CLI, split and local-path text

- **Claim:** README/Dataset/training documentation describes the current public
  interface and reproducible workflow.
- **Evidence:** README's CLI table omits implemented
  `extract-reference-signals` (`cli/main.py:124-132`); `docs/DATASET.md:40-61`
  still describes the older `random.Random` two-fold strategy rather than v0.1
  hash-ranked union-find splits; `training/README.md` contains literal local
  `G:\osu! 20210821\Songs` paths. Several split/benchmark docs are untracked.
- **Impact/scope:** public users can follow obsolete commands or mistake local
  environment paths for portable instructions.
- **PASS impact:** implementation semantics are not changed.
- **Remediation direction:** reconcile public docs only after semantic and
  provenance fixes are versioned.

### Info

#### I-01 — Core split isolation passes independent verification

An independent implementation read 126,509 manifest rows / 125,988 unique
checksums and found zero checksum crossings for all splits, zero set-group
crossings for SET and STRICT, and zero name-only mapper crossings for MAPPER
and STRICT. Canonical order, exact coverage, published SHA-256 hashes and
deterministic assignment all match. There are 11 checksum conflict classes,
2,296 BeatmapID conflicts, 4,512 name-only mapper groups and no unknown mapper
rows; those anomalies are represented rather than silently crossed.

#### I-02 — Per-map corpus artifacts reconcile

Independent streaming found exactly 126,509 rows in each Feature, Local and
Reference JSONL, with 56,547,084 objects and 3,674,160 segments reconciled.
Each has 125,988 unique checksums and 126,509 unique row identities. No per-map
feature, signal or aggregate output contains NaN/Inf; serializability flags are
true. The aggregate-report defect in M-02 must not be misreported as per-map
signal corruption.

## Rejected Findings

The following suspicions were investigated and rejected or narrowed:

| Suspicion | Evidence checked | Conclusion |
| --- | --- | --- |
| Local angle orientation is reversed | Independent vector cases and pinned ppy/osu convention | Not a bug. Straight continuation is π, reversal is 0 and a right angle is π/2 by the chosen ppy-style convention. |
| Missing Mode is parsed incorrectly | Synthetic file without `Mode` | Not a bug. It defaults to osu!standard as documented. |
| Inherited timing/SV is wrong | Independent red/green timing-point oracle | Not a bug for the tested cases; BPM, SV and parent beat length match. |
| 25 ms clamp / CS scale / jump distance are mistranscribed | Independent formulas | Not a bug in bounded cases. |
| Simple Snap, Agility, Flow, Speed or equal-interval Rhythm are wrong | Minimal formulas derived separately from pinned source | These tested regimes match; this does not rescue the confirmed Reading error. |
| Fixed-window objects are double-counted at 5 s boundaries | Objects at 4999.999, 5000 and 5000.001 ms | Not a bug. Every object is assigned exactly once and indices are correct. The zero-duration final bucket is a separate caveat. |
| Production outputs silently clip extreme finite inputs | BPM ~1e302, SV ~1e303, pixel length ~1e306 and ±1e308 aggregate values | Not reproduced. Production per-map values remain finite/strict-JSON safe or explicitly unavailable. QA streaming arithmetic is the failing layer. |
| Split leakage exists under the declared set/mapper rules | Independent split parser, union/group checks and content hashes | Not reproduced. All declared hard isolation constraints pass. |
| `UPSTREAM_EXECUTABLE_PARITY=BLOCKED` is hidden | Contracts, parity reports and final reports | Not a defect; the limitation is disclosed accurately. |

## Subsystem Verdicts

| Subsystem | Verdict | Basis |
| --- | --- | --- |
| Parser | `PASS_WITH_CAVEATS` | Core timing, defaults and ordering pass; malformed-value/provenance and invalid-encoding identity issues remain. |
| Feature v0.1 | `BLOCKED` | Frozen repeat fields and repeat-slider duration are semantically wrong. |
| Local Signal v0.2 | `BLOCKED` | Repeat total timing, repeat bonus and late-tick tracking diverge from pinned source. |
| Reference Signal v0.1 | `BLOCKED` | Reading has a direct transcription bug and Reference preprocessing inherits defective Local geometry. |
| Segment QA | `BLOCKED` | Assignment works, but a declared Local consistency invariant is excluded from PASS and exact-boundary duration is underspecified. |
| Reference Disagreement | `PASS_WITH_CAVEATS` | Exact method reproduces; asymmetry is method-dependent and candidates are diagnostic only. |
| Dataset Identity | `PASS_WITH_CAVEATS` | SHA-256 identity is consistent; mapper identity is NAME_ONLY and near-duplicate checks are weak. |
| Split / Leakage | `BLOCKED` | Hard split isolation passes, but generator provenance and target-leakage enforcement are not ready for training. |
| Benchmark Protocol | `BLOCKED` | Challenge manifests contain train rows; held-out challenge scoring is not enforced. |
| Licensing | `BLOCKED` | No root license grant and insufficient direct-adaptation attribution. |
| Reproducibility | `BLOCKED` | Tracked core is reproducible, but untracked split generator provenance, resume semantics and invalid aggregate JSON prevent an end-to-end guarantee. |

## Shared-Assumption Risk

Yes: implementation and tests can be wrong in exactly the same way and still
PASS.

1. **Repeat duration:** Local production computes one-span total duration, and
   unit tests explicitly expect the same 1,000 ms result for a two-span slider.
2. **Repeat travel bonus:** the Local contract conflates repeat/span terminology
   and expected data follows the same interpretation.
3. **Feature repeat fields:** tests assert positivity and field presence rather
   than independent repeat semantics.
4. **Reading opacity:** “source-audited” golden formulas were manually
   transcribed and inherited the wrong-object reading; 128/128 checks therefore
   cannot rule out a shared transcription error.
5. **Full-corpus QA:** deterministic, finite output can consistently encode the
   wrong formula. Artifact scale strengthens reliability evidence but is not a
   semantic oracle.
6. **Split:** production tests may share helper logic, but this risk was reduced
   materially by the independent split implementation, which does pass.

Executable upstream parity remains blocked, so untested Reference branches may
still contain shared mistakes. The bounded independent micro-oracle supports
simple Snap/Agility/Flow/Speed/Rhythm regimes only; it is not a complete second
implementation.

## Benchmark Trust Assessment

The three core split membership files are trustworthy for their exact declared
group keys and current artifacts. They demonstrate checksum isolation,
BeatmapSetID/local-folder isolation and provisional normalized-name mapper
isolation. They do not demonstrate gameplay near-duplicate independence,
creator-ID identity, temporal generalisation or semantic correctness of model
inputs.

`TEMPORAL_OOD = BLOCKED` is correct because no trustworthy chronological
metadata exists; file mtime must not be promoted to ground truth. The three
challenge manifests are useful tagged subsets but are not themselves held-out
benchmarks because they include train and validation rows. Reference
disagreement candidates are methodology-sensitive and must not be interpreted
as taxonomy or “official blind spots.”

Accordingly, benchmark split mechanics can be retained as evidence, but no
model benchmark should run until semantic inputs are repaired/versioned,
test-only challenge selection is enforced, and source provenance is committed
or content-addressed.

## Target-Leakage Readiness

The threat model correctly names reference-as-input, weak-label, pseudo-label,
preprocessing and identity leakage risks. It is not machine-enforceable. In
particular:

- `ref.ppy.*`, `ls.*`, Feature fields, challenge flags, split metadata, weak
  labels and future human labels have no single versioned role registry;
- no verifier rejects target-derived inputs or deterministic algebraic
  transforms of the target;
- the documented “no labels generated” state is stale; and
- challenge membership and split assignment are not prevented from entering a
  future model feature table.

Weak-label output being marked as weak is good provenance, but labeling alone
does not prevent target leakage. The project should not begin weak supervision
until a machine-readable input/target contract is enforced on the exact
training matrix and label artifact.

## Recommended Remediation Order

No remediation is performed in this audit. Recommended sequence:

1. Freeze use of current Feature/Local/Reference artifacts for label or model
   work; preserve them only as historical evidence.
2. Correct and version repeat-slider total/span timing across normalized,
   Local and Reference preprocessing; independently recompute affected fields.
3. Correct repeat-count versus span-count semantics in Feature and Local,
   deciding explicitly how frozen v0.1 fields migrate.
4. Correct Reference Reading opacity and add an independent upstream-derived
   fixture that cannot share production helpers.
5. Rebuild semantic goldens from independent formulas and add counterexamples
   for every confirmed shared-assumption failure.
6. Repair QA completeness contracts: successful-resume criteria,
   scale-aware segment consistency, strict JSON and final identity coverage.
7. Commit/content-address the split generator and contracts, then enforce
   test-only challenge scoring.
8. Implement a machine-readable signal-role/target partition and provenance
   gate before any weak-label/model run.
9. Resolve license/NOTICE distribution requirements.
10. Reconcile public documentation and establish density-aware performance
    limits.

After remediation, rerun bounded independent oracles first, then regenerate
official artifacts and repeat this review. Existing expected values must not be
edited merely to match new output without an independent semantic oracle.

## Reproduction Commands

From the repository root with Python 3.10 or newer:

```powershell
python tmp/red-team-v01/micro_oracle.py
python tmp/red-team-v01/transcription_oracle.py
python tmp/red-team-v01/adversarial_boundaries.py
python tmp/red-team-v01/independent_corpus_audit.py
python tmp/red-team-v01/independent_split_audit.py
python tmp/red-team-v01/independent_disagreement_sensitivity.py
python -c "import runpy,sys; sys.path.insert(0, 'src'); runpy.run_path('tmp/red-team-v01/performance_oracle.py', run_name='__main__')"
python run_tests.py
```

The corpus and split scripts use existing local artifacts and do not perform
full extraction. Exact output JSON files named in Scope are the audit evidence.

## Explicit Confirmations

This audit made no modification to:

- production code;
- tests or expected golden values;
- semantic contracts or official generated artifacts;
- weak-supervision rules;
- taxonomy;
- human labels;
- model/training code or data;
- WuxinBot;
- deployed services.

It performed no model training, no taxonomy generation, no human annotation,
no WuxinBot work, no deployment and no git commit. Writes are limited to this
audit report, the ignored audit checkpoint and bounded ignored evidence under
`tmp/`.

## Final Verdict

```text
FOUNDATION_CORRECTNESS: BLOCKED
READY_FOR_WEAK_SUPERVISION: NO
```

The split algorithm's hard isolation properties and the corpus artifact counts
are credible. The foundation as a whole is blocked because multiple versioned
semantic layers are directly contradicted by independent pinned-source oracles,
and the target-leakage boundary is not yet enforceable.
