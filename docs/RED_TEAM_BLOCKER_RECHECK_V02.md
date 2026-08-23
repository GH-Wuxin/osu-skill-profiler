# Independent Surgical Red-Team Blocker Recheck v0.2

Date: 2026-08-13

Review role: independent final Pre-ML Foundation gate

Repository: `osu-skill-profiler`

Frozen review target: `main` / `bc8655c2fa5d3f23807048c921cfd7f1e75bcdb9`

## Executive verdict

The five blocking findings from `INDEPENDENT_RED_TEAM_AUDIT_V01.md` were
reconstructed against the corrected implementation, pinned ppy/osu source,
independent hand-written discriminator formulae, executable version boundaries
and the default-deny leakage gate. All five are fixed in their corrected
versions. Explicit legacy selectors still reproduce the historical behavior;
the old behavior was not silently reinterpreted.

```text
REVIEW_TARGET_INTEGRITY:          PASS
RT-01:                           FIXED
RT-02:                           FIXED
RT-03:                           FIXED
RT-04:                           FIXED
RT-05:                           FIXED
HISTORICAL_VERSION_INTEGRITY:    PASS
TARGETED_TESTS:                  PASS
NEW_CRITICAL_OR_HIGH_FINDING:    NONE
BLOCKER_REMEDIATION_VERIFIED:    YES
READY_FOR_WEAK_SUPERVISION:      YES_WITH_CAVEATS
```

`READY_FOR_WEAK_SUPERVISION: YES_WITH_CAVEATS` means only that RT-01 through
RT-05 no longer block entry into **Weak Supervision Infrastructure** work. It
does not mean that the whole repository was red-teamed from scratch a second
time, that future ML design is correct, that Reference signals are ground
truth, that the taxonomy is frozen, or that leakage is impossible outside
declared and mechanically enforced contracts.

## Review target integrity

The target was checked before and after the review:

```text
branch: main
HEAD: bc8655c2fa5d3f23807048c921cfd7f1e75bcdb9
staged diff: empty
pre-existing worktree state:
 M docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md
?? tools/performance_probe.py
```

The modified remediation report contains the final evidence appended after
the source checkpoint; `tools/performance_probe.py` is the reported delivery
artifact. No remediation process was running. The review did not alter either
path and did not alter production code, historical artifacts, or the original
red-team report. The original report still hashes to
`3A98704BBFD03FCA294CBDA94B6BC0B80CE9F9FC39CA2DF0CF377DE3BFB5719C`.

## Method

Remediation claims were treated as indices, not proof. The independent audit
used:

- pinned source snapshots for `Slider.EndTime`, `SpanCount`, repeat travel and
  Reading object identity;
- a temporary audit-only oracle at `tmp/red-team-v02/micro_oracle.py`, whose
  expected side contains hand-written formulae rather than the production
  slider helper;
- production Feature, Local, Reference and leakage entry points as the system
  under review;
- narrow version/mutation/leakage regression tests and one cheap full unit
  suite;
- re-generated corrected Local and Reference goldens under `tmp/red-team-v02/`;
- hashes and compact summaries of completed corpus artifacts, without rerunning
  any 5k, 20k or 126,509-map extraction campaign.

The independent oracle passed **28/28** checks. Its evidence output is
`tmp/red-team-v02/micro_oracle.json`.

## Finding verdicts

| Finding | Verdict | Independent evidence | Old-bug discriminator | Remaining caveat |
| --- | --- | --- | --- | --- |
| RT-01 | **FIXED** | Pinned `Slider.cs:28` defines `EndTime = StartTime + SpanCount() * Path.Distance / Velocity`; the decoded pinned `IHasRepeats` blob defines `SpanCount() = RepeatCount + 1`. `slider_semantics.py:48-93`, `normalized.py:145-187`, `features/extractor.py:97-114,201-208` and `signals/slider.py:235-253` implement the same count/timing relationship for corrected versions. | At 200 px and 0.2 px/ms, the independent expectation for 1/2/3 spans is 1000/2000/3000 ms, with end times 1000/6000/11000 ms. Production matches exactly; the historical one-span mutation emits 1000/1000/1000. For slider-to-circle and slider-to-slider cases, corrected `LastObjectEndDeltaTime` is 500/100 ms while the compressed-end mutation gives unclamped 1500/2100 ms. | Feature 0.1 and Local 0.2 intentionally retain compressed duration only for explicit historical replay. |
| RT-02 | **FIXED** | Pinned `OsuDifficultyHitObject.cs:200-204` multiplies lazy travel by `max(1, RepeatCount^0.3)`. `signals/extractor.py:85-98` selects `repeat_count` for Local 0.3 and `span_count` only for Local 0.2. The affected public field is `ls.travel_distance_cs_normalised`; Local 0.3 also exposes `ls.slider_repeat_count`. | For one repeat (2 spans), corrected multiplier is 1.0 while the old span multiplier is `2^0.3 = 1.231144...`. For two repeats (3 spans), corrected multiplier is `2^0.3 = 1.231144...` while old is `3^0.3 = 1.390389...`. The oracle confirms Local 0.3 uses the former in both cases and Local 0.2 independently reproduces its historical span multiplier on its own legacy lazy-distance base. | Lazy geometry itself also changes between versions because RT-01 was corrected; the discriminator therefore compares multipliers on each version's own base and separately compares the old substitution on the current base. |
| RT-03 | **FIXED** | Pinned `ReadingEvaluator.cs:143-159`, at exact commit `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`, calls `currObj.OpacityAt(loopObj.BaseObject.StartTime, false)`. `reference/ppy/evaluators.py:617-650` does exactly this for Reference 0.2 and retains the wrong loop-object identity only for Reference 0.1. Reference 0.2 consumes Local 0.3; Reference 0.1 consumes Local 0.2. | In the identity-sensitive eight-object fixture, current-object opacity terms are `[1, 1, .75, .5, .25]`, sum 3.5. The historical loop-object-at-own-start terms are `[1,1,1,1,1]`, sum 5.0. Reference 0.2 returns 3.5 and Reference 0.1 returns 5.0; the two expressions cannot pass by coincidence. | There is still no executable .NET upstream parity harness. This verdict is exact source-identity verification plus independent numeric discrimination, not a claim of universal upstream executable parity. |
| RT-04 | **FIXED** | Feature versions are explicit (`0.1.0` and `0.2.0`). Feature 0.1 retains `slider.repeats_*`; Feature 0.2 removes them and exposes separate `slider.repeat_count_*` and `slider.span_count_*`. The migration and errata documents disclose the historical misnaming. `dataset/leakage.py:87-93` mechanically assigns the old names `DEPRECATED_FOR_NEW_MODELS`. | For one-span plus three-span sliders, Feature 0.1 reproducibly emits historical span values total/max 4/3. Feature 0.2 emits repeat total/max 2/2 and span total/max 4/3. A candidate model schema containing `slider.repeats_total` hard-fails with `FORBIDDEN_INPUT_ROLE`. | The frozen `FEATURE_SCHEMA_V01` and older `FEATURES.md` text still use the historical “repeat count” description. This is acceptable only because the schema is immutable historical evidence and the dedicated migration/errata explicitly corrects its interpretation; new-model use is mechanically forbidden. |
| RT-05 | **FIXED** | `dataset/leakage.py` builds a central role registry, denies unknown inputs, rejects role overrides, traverses declared lineage with cycle-safe transitive closure, and checks closure intersection for every input/target pair. `target_leakage_audit.py` is an executable hard gate with exit 0/1/2 semantics. | The independent matrix passes observable input + independent human target and Reference used only offline. It rejects Reference input sharing target lineage, target in inputs, split membership, challenge selection, unknown input, and deprecated Feature fields. An additional two-hop target lineage (`target -> mid -> ref.ppy.speed`) with a separately derived input from the same Reference source fails with `TARGET_LINEAGE_LEAKAGE`, proving traversal is transitive rather than direct string comparison. | The gate deliberately cannot infer undeclared arbitrary mathematical equivalence. Future materialization must declare lineage and run this gate; PASS is necessary, not sufficient, for an actual training matrix. |

## Semantic reconstruction details

### RT-01 canonical units and downstream dependency

For the discriminator map, `SliderMultiplier=1`, red timing is 500 ms and
path length is 200 px. Velocity is therefore 100 px per beat / 500 ms =
0.2 px/ms. The independent equations are:

```text
single_span_duration = 200 / 0.2 = 1000 ms
total_duration       = 1000 * span_count
end_time             = start_time + total_duration
```

The corrected Feature map end and Local end-time consumers select total
duration. Local's following-object path computes
`max(next_start - previous_end, 25 ms)` at
`signals/extractor.py:256-269`; changing only previous end from one span to all
spans changes the demonstrated downstream deltas. The corresponding mutation
tests in `test_foundation_remediation_v01.py` explicitly reject the old
one-span result, so reintroducing the historical expression fails rather than
merely changing an unasserted helper.

### RT-02 exact affected signal

The corrected repeat count is used at the final public calculation boundary,
not only stored in a helper. `signals/extractor.py:271-288` assigns the result
of `_travel_distance_cs()` directly to
`ls.travel_distance_cs_normalised`. Both one-repeat and two-repeat cases have
non-zero lazy travel, so the old and corrected multipliers produce distinct
observable values. The targeted mutation regression rejects the old value.

### RT-03 pinned identity

The local pinned tree records commit
`b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`. Its
`ReadingEvaluator.cs:149` names `currObj` as the opacity receiver and the past
`loopObj` only as the timestamp source. The production current branch uses the
same receiver/time pair. The independent expected opacity uses the current
object's preempt/fade-in window, while the old expression evaluates each past
object at its own start and therefore yields 1.0 for every term. The existing
Reading regression also computes its expected terms without importing
`_opacity_at` and fails the legacy branch.

### RT-04 historical schema interpretation

The v0.1 schema text was not retroactively edited. That preserves historical
bytes but makes the dedicated erratum essential. The combined boundary is
unambiguous in executable behavior:

```text
FeatureExtractor("0.1.0") -> historical names and historical span values
FeatureExtractor("0.2.0") -> explicit repeat_count and span_count fields
leakage registry           -> old names forbidden for new model inputs
```

### RT-05 transitive closure

`_lineage_closure()` maintains a visited set, follows every declared source
until exhaustion and is safe under cycles. The validator intersects the full
closure of each target with the full closure of each input. The independent
two-hop negative case passed schema registration and failed specifically on
shared protected lineage, not merely because the input was unknown or had a
forbidden role.

## Historical version integrity

```text
Historical: Feature 0.1 / Local 0.2 / Reference 0.1
Corrected:  Feature 0.2 / Local 0.3 / Reference 0.2
```

The code requires explicit supported versions and routes each layer
separately. Reference 0.1 binds to Local 0.2; Reference 0.2 binds to Local 0.3.
Unsupported versions fail before extraction. Historical and corrected corpus
artifacts coexist under distinct directories:

```text
feature_qa/              -> feature_qa_v02/
golden_v02/              -> golden_v03/
local_signal_qa/         -> local_signal_qa_v03/
golden_reference_v01/    -> golden_reference_v02/
reference_signal_qa/     -> reference_signal_qa_v02/
splits/v01/              -> splits/v02/
```

File timestamps and sizes show both generations remain present. Split v01 and
v02 `identity_audit.json` are byte-identical with SHA256
`88F7DF3BCD745DE082262AB9884C9DEE8100C4FFD9DDC763970FB8654296FE5B`.
Their manifests preserve the same source checksum, seed, split counts and
identity policy, while recording the expected Feature/Local/Reference version
triples. V02 updates challenge versions and QA-derived annotations rather than
rewriting v01. The errata accurately identifies all three historical semantic
failures.

Therefore:

```text
HISTORICAL_VERSION_INTEGRITY: PASS
```

## Targeted and regression tests

Executed with the available Python 3.12.13 interpreter:

```text
independent micro-oracle:                         28/28 PASS
targeted Feature/Local/Reference/leakage modules: 85/85 PASS
corrected Local golden regeneration:             155/155 PASS
corrected Reference golden regeneration:         128/128 PASS
full cheap unit suite:                            201/201 PASS
compileall:                                       PASS
git diff --check:                                 PASS
```

The regenerated Local and Reference golden artifacts are byte-identical to
the archived corrected artifacts. No corpus extraction was run.

```text
TARGETED_TESTS: PASS
```

## Completed corpus evidence (supporting only)

Compact archived reports state:

```text
20k semantic delta: 20,000/20,000 PASS; 0 failed; 0 newly missing;
                    0 nonfinite introduced/resolved; versions explicitly
                    0.1->0.2 Feature, 0.2->0.3 Local, 0.1->0.2 Reference
Feature 0.2 full:   126,509/126,509 PASS; 106 fields; 0 failures
Local 0.3 full:     126,509/126,509 PASS; 0 failures; geometry blocked
                    53 maps / 819 objects
Reference 0.2 full: 126,509/126,509 PASS; 0 failures/nonfinite/segment
                    alignment failures; geometry blocked 53 / 819
```

Five declared artifact hashes matched exactly:

```text
delta_20000.jsonl
D974D8A07B33B3B9D4121B2FA42B0700E6287E407DF40703C67C11139D8602CF

delta_20000_summary.json
46677103D8D187352E3756CEAE02D46D47C25F3D336B3798C10AF6B6E3A72D67

feature_qa_v02/feature_qa_full.jsonl
6CABF2C7A5E1FD82E75186CD1AA911D4CCC34A98D4220747A459E46EA3D8527C

local_signal_qa_v03/local_signal_qa_full.jsonl
787F9D02B02883F92872A08445F27FC473410E2E24063FA2D0112713A3CB1AD0

splits/v02/identity_audit.json
88F7DF3BCD745DE082262AB9884C9DEE8100C4FFD9DDC763970FB8654296FE5B
```

One remediation-report hash has a non-semantic transcription error: the
listed Reference full hash contains **65** hexadecimal characters because of
an extra `E` after `...AAFC`. The actual file has the valid 64-character hash:

```text
reference_signal_qa_v02/reference_qa_full.jsonl
425B05DD1672305F0BD768E3591AAFCBA9A08B75F5D844656899C4E1F1A86A19
```

The artifact itself is coherent with the compact Reference report, the
126,509-map counts, version metadata, regenerated 128/128 golden and Local
geometry-blocked totals. This is a remaining evidence-ledger caveat, not a
semantic RT-01--RT-05 failure or artifact-drift indication. The remediation
report was deliberately not edited by this independent review.

## New blocker assessment

No new Critical or High correctness issue was directly observed in the exact
RT-01--RT-05 paths. The malformed Reference hash in the remediation report is
a bounded documentation/evidence transcription defect and is disclosed above.
The known absence of executable upstream .NET parity remains accurately
disclosed and does not negate the identity-sensitive source check.

```text
NEW_CRITICAL_OR_HIGH_FINDING: NONE
```

## Final gate

All required gate predicates are satisfied:

```text
REVIEW_TARGET_INTEGRITY:          PASS
RT-01_REPEAT_SLIDER_DURATION:     FIXED
RT-02_REPEAT_SPAN_SEMANTICS:      FIXED
RT-03_READING_OPACITY_IDENTITY:   FIXED
RT-04_FEATURE_REPEAT_CONTRACT:    FIXED
RT-05_TARGET_LEAKAGE_ENFORCEMENT: FIXED
HISTORICAL_VERSION_INTEGRITY:    PASS
TARGETED_TESTS:                  PASS
NEW_CRITICAL_OR_HIGH_FINDING:    NONE

BLOCKER_REMEDIATION_VERIFIED:    YES
READY_FOR_WEAK_SUPERVISION:      YES_WITH_CAVEATS
```

This review now stops at the requested final Pre-ML Foundation gate. It does
not start Weak Supervision, alter production code, clean artifacts, refactor,
stage, commit, push, or widen the audit.
