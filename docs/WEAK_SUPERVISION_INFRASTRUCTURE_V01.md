# Weak Supervision Infrastructure v0.1

Status: **PASS**

```text
WEAK_SUPERVISION_INFRASTRUCTURE: PASS
```

## Purpose and non-goals

This phase adds an executable, versioned layer for expressing, validating,
combining, auditing, and exporting weak evidence over verified osu!standard
map signals. It also materializes one bounded deterministic pilot corpus.

It does not train a model, declare evidence to be truth, freeze a skill
taxonomy, ingest human/community labels, perform player analysis, build
recommendations, integrate WuxinBot, or enter Active Learning.

## Architecture

```text
verified Feature 0.2 / Local 0.3 / Reference 0.2
                    |
           registered source DAG
                    |
     deterministic rules with first-class abstention
                    |
        versioned WeakEvidenceRecord JSONL
                    |
 lineage-aware agreement/conflict + leakage audit
                    |
       bounded, content-addressed pilot evidence
```

Implementation:

| Component | Path |
| --- | --- |
| evidence, scope, value, status, abstention and confidence contract | `src/osu_skill_profiler/weak_supervision/contracts_v01.py` |
| proposition/source/rule registries and source DAG | `src/osu_skill_profiler/weak_supervision/registry_v01.py` |
| four provisional propositions and five sparse pilot rules | `src/osu_skill_profiler/weak_supervision/pilot_v01.py` |
| deterministic execution and strict serialization | `src/osu_skill_profiler/weak_supervision/runtime_v01.py` |
| lineage-aware coverage/agreement/conflict audit | `src/osu_skill_profiler/weak_supervision/audit_v01.py` |
| authoritative leakage-gate bridge | `src/osu_skill_profiler/weak_supervision/leakage_v01.py` |
| bounded pilot runner | `tools/weak_supervision_pilot_v01.py` |

The field-level contract is
[`WEAK_EVIDENCE_CONTRACT_V01.md`](WEAK_EVIDENCE_CONTRACT_V01.md).

## Foundation provenance

The consumed Foundation is pinned in
`docs/WEAK_SUPERVISION_FOUNDATION_PROVENANCE_V01.json`: HEAD
`bc8655c2fa5d3f23807048c921cfd7f1e75bcdb9`, Feature `0.2.0`, Local
`0.3.0`, Reference `0.2.0`, split `0.1.0` with corrected v02 artifacts,
and leakage policy `0.1.0`.

The known malformed Reference full-artifact hash is preserved and corrected
without rewriting history in
`docs/REFERENCE_FULL_SHA256_TRANSCRIPTION_ERRATA_V01.md`.

No full-corpus artifact was recomputed or overwritten.

## Source and proposition registries

All five active sources are registered. Three use corrected Feature
observables, one uses corrected Local segment signals, and one uses the pinned
Reference ppy snap policy. The Reference source is explicitly
`reference_only=true` and `model_input_safe=false`.

The registry admits only provisional propositions in v0.1. Unknown
propositions, sources, source versions, roots, or dependencies fail. Source
dependencies are a DAG; cycles fail, transitive closure is deterministic, and
shared ancestry is mechanically detectable.

## Independence and aggregation

Evidence is grouped by entity and proposition. Effective independent support
is the number of correlation components, not raw rule count. A component is
formed by an explicit shared independence group or shared semantic ancestor.

The audit reports records, statuses, rules, sources, propositions, scopes,
per-rule coverage, missing-source patterns, source-family combinations,
correlated groups, independent agreement, and directional conflicts.
Conflicts are retained as examples. No majority-vote label or production
score is generated.

Synthetic adversarial tests prove that two differently named rules with the
same lineage count once, independent same-direction evidence is recognized,
and independent opposite-direction evidence remains an explicit conflict.

## Abstention and confidence

Every applicable rule produces `EMITTED`, `ABSTAINED`, `UNAVAILABLE`, or
`INVALID`; empty output is not used as a semantic substitute. Reasons include
missing signal, insufficient support, geometry blocked, ambiguous evidence,
unsupported semantics, and Reference unavailable.

Deterministic strength is a bounded margin from a documented fixed threshold.
Confidence bands describe rule posture only. Neither is a probability.

## Leakage integration

The existing default-deny gate remains authoritative and was not weakened.
Weak targets carry complete roots, allowing mechanical direct/transitive
overlap checks. The pilot includes three executable controls:

- independent corrected observable input: PASS;
- Reference input overlapping Reference-derived evidence: FAIL with both
  `FORBIDDEN_INPUT_ROLE` and `TARGET_LINEAGE_LEAKAGE`;
- challenge membership as input: FAIL with `FORBIDDEN_INPUT_ROLE`.

Adversarial tests also cover direct and transitive Reference overlap, unknown
inputs/lineage, target-as-input, split/challenge fields, and a valid independent
configuration.

## Pilot rules

| Rule | Scope/family | Evidence hypothesis | Sparse discriminator |
| --- | --- | --- | --- |
| observable movement tail | MAP / OBSERVABLE | movement demand high | distance p95 + movement-rate p95 |
| ppy snap tail | MAP / REFERENCE_PPY | same hypothesis, independent reference view | object snap p90; reference-only |
| dense timing | MAP / OBSERVABLE | dense timing pressure high | one-second rate + sustained 125ms burst |
| slider control load | MAP / OBSERVABLE | slider control load high | corrected slider ratio/duration/repeats |
| Local slider travel | SEGMENT / LOCAL_SIGNAL | slider tracking travel high | canonical 5s segment lazy-travel p90 |

Every rule declares rationale, dependencies, scope, source lineage, confidence
semantics, abstention conditions, discriminator, and failure modes in the
machine-readable registry artifact. Middle bands abstain.

## Pilot selection and storage

The pilot consumes the existing corrected 5k QA artifacts. Selection first
takes deterministic bounded quotas from Reference disagreement, pathological,
and legacy challenge sets, then fills by a seed/version/checksum hash rank.
Challenge flags are selection-only and never enter rule contexts or evidence.

The 1,000-map output contains 35,854 records (4,000 MAP and 31,854 SEGMENT).
Estimated evidence size was 38.5 MB; actual size is 37,364,440 bytes. This is
bounded and avoids copying giant source rows. Canonical artifacts are
selection, evidence, and registries; audit/leakage reports are regenerable;
temporary smoke output resides outside the repository and is safely deletable.

Full counts and hashes are in
[`WEAK_SUPERVISION_PILOT_V01_REPORT.md`](WEAK_SUPERVISION_PILOT_V01_REPORT.md).
Generated data remains ignored under
`training/datasets/weak_supervision_v01/pilot/`; no historical Pre-ML artifact
was deleted.

## Testing and adversarial cases

Dedicated tests cover registry validation/version mismatch, direct/transitive/
shared lineage, unknown nodes, cycles, positive/negative/scalar contracts,
abstention/unavailable/invalid, zero versus absent evidence, duplicate
emission, canonical segment scope, future pairwise shape, leakage, correlation,
conflict preservation, strict finite serialization, stable ordering, bounded
selection, input order independence, and machine-local output rejection.

The full pre-existing 201-test Foundation suite remains green alongside the
new tests. An 8-map real-data smoke emitted 300 records before the bounded
campaign. Exact final counts are recorded in the pilot report.

## Known limitations

- Pilot thresholds are hand-declared QA discriminators, not empirically
  calibrated decision boundaries.
- Only four provisional hypotheses and five rules are active.
- Reference semantics are unmodded-only and lack executable upstream .NET
  parity, as already disclosed by the Foundation.
- Map-level p90/tail summaries lose ordering; the one segment rule is narrow.
- The 1,000-map real pilot produced independent agreement but no directional
  conflict. Conflict retention is demonstrated synthetically, not claimed as
  a discovered real-corpus taxonomy fact.
- Existing source lineage cannot infer undeclared arbitrary mathematical
  equivalence; declarations and the leakage gate remain mandatory.
- No human or community evidence has been collected, and no proposition has
  been validated as a human-interpretable skill.

## Next-phase gates

Before Active Learning design, review the sparse rule semantics, inspect
independent agreement and selected abstention cases, decide whether pairwise
human questions match any provisional proposition, and specify annotator and
split isolation. Before any model work, materialize a candidate schema and run
the default-deny leakage gate on the exact inputs/targets.

This phase does not perform those steps.

```text
READY_FOR_ACTIVE_LEARNING_DESIGN: YES_WITH_CAVEATS
```

The caveats are the provisional, uncalibrated propositions and absence of
human validation. This verdict does not authorize immediate training.
