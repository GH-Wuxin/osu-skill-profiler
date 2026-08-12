# Pre-ML Foundation Errata v0.1

Status: **historical correction index; pending independent re-verification**

This errata preserves the original version history. Historical artifacts and
reports remain evidence of what the project emitted at the time; they must not
be edited to imply that old semantics were correct.

## Supersession table

| Historical version/artifact | Erratum | Corrected replacement |
| --- | --- | --- |
| Feature `0.1.0` / `feature_qa/` | repeat-slider duration compressed to one span; `slider.repeats_*` actually count spans | Feature `0.2.0` / `feature_qa_v02/` |
| Local Signal `0.2.0` / `golden_v02/`, `local_signal_qa/` | total duration compressed; repeat travel used span count; late real tick tracking end incomplete | Local Signal `0.3.0` / `golden_v03/`, `local_signal_qa_v03/` |
| Reference Signal `0.1.0` / `golden_reference_v01/`, `reference_signal_qa/` | inherited Local timing and evaluated the wrong object identity for Reading opacity | Reference Signal `0.2.0` / `golden_reference_v02/`, `reference_signal_qa_v02/` |
| Segment Signal QA `0.1` | derived from historical Local/Reference values | corrected derived Segment QA version (recorded in remediation report) |
| Reference-disagreement challenge v0.1 | membership derived from historical Local/Reference values | corrected challenge version (recorded in remediation report) |
| leakage threat-model prose | target/input separation not mechanically enforced | Target Leakage Enforcement `0.1.0` |

## Historical claims that are no longer valid

The following old PASS statements remain reproducible but cannot be used as
semantic correctness evidence:

- Feature v0.1 slider duration represents total slider duration;
- Feature v0.1 `slider.repeats_*` represents true repeats;
- Local v0.2 slider end, travel and repeat bonus match the pinned source;
- Reference v0.1 Reading is a correct source transcription;
- full-corpus finiteness/determinism alone validates those formulas;
- target-leakage readiness is enforced by documentation.

The old test and QA counts are historical results, not corrected baselines.

## Immutable paths

The remediation does not write into:

```text
training/datasets/feature_qa/
training/datasets/golden_v02/
training/datasets/local_signal_qa/
training/datasets/golden_reference_v01/
training/datasets/reference_signal_qa/
training/datasets/splits/v01/
```

New semantics use new versioned directories. Old checksums therefore continue
to identify old bytes rather than silently pointing at corrected values.

## Compatibility meaning

Historical compatibility means **replayability**, not approval for new model
inputs:

- `FeatureExtractor("0.1.0")` replays Feature v0.1;
- `LocalSignalExtractor("0.2.0")` replays Local v0.2;
- `ReferenceSignalExtractor("0.1.0")` replays Reference v0.1;
- the leakage registry forbids the misleading v0.1 repeat fields in new model
  schemas.

## Corrected evidence

The authoritative remediation matrix, semantic deltas, artifact checksums and
current statuses live in
[`PRE_ML_FOUNDATION_REMEDIATION_V01.md`](PRE_ML_FOUNDATION_REMEDIATION_V01.md).
Only a later independent reviewer may decide whether the corrected foundation
is ready for weak supervision.
