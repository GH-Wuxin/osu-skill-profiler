# Official Reference Signal Contract v0.2

Status: **IMPLEMENTED; pending independent re-verification**

Reference version `0.2.0` is the corrected current contract.
Reference `0.1.0` remains historical and replayable. Both remain pinned to:

| Item | Value |
| --- | --- |
| Repository | `ppy/osu` |
| Commit | `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e` |
| Difficulty version | `20260706` |
| Supported scope | osu!standard, unmodded, local/reference analysis only |

This is a semantic delta over
[`PPY_REFERENCE_SIGNAL_CONTRACT_V01.md`](PPY_REFERENCE_SIGNAL_CONTRACT_V01.md).
The 14-field surface and nine `ref.ppy.*` signal names are unchanged. A
version bump is still required because inputs and one evaluator identity
changed.

## Corrected dependencies

Reference v0.2 consumes Local Signal v0.3. Consequently repeat-slider total
duration, end time, repeat bonus, nested timing, lazy travel and downstream
movement are corrected before evaluation. Reference v0.1 continues to consume
Local v0.2 so historical output remains reproducible.

```text
Reference 0.1 -> Local 0.2 -> historical slider semantics
Reference 0.2 -> Local 0.3 -> corrected slider semantics
```

## Reading opacity identity repair

The pinned `ReadingEvaluator` past-visible-object loop evaluates:

```text
currObj.OpacityAt(loopObj.BaseObject.StartTime, false)
```

Reference v0.1 instead evaluated the loop object's own opacity at its own
start, which is effectively fully opaque and overstates past visible density.
Reference v0.2 evaluates the **current object** at each past object's start
time. The time argument is unchanged; the corrected part is object identity.

An identity-sensitive independent fixture constructs objects whose opacity
differs by identity at the same timestamp. It detects the v0.1 mutation and
passes only for the pinned v0.2 interpretation.

## Field policy

Every `ref.ppy.*` field remains:

- `OFFICIAL_REFERENCE`;
- `reference_only: true`;
- `never_ground_truth: true`;
- `model_input_safe: false`;
- exploratory/offline comparison only.

Reference signals are not observable inputs, weak labels, official C# output,
final strain, star rating or PP. `speed_with_rhythm` remains a decomposition
product without the upstream skill multiplier or decay.

## Executable parity status

```text
UPSTREAM_EXECUTABLE_PARITY = BLOCKED
```

No usable .NET SDK was introduced for this remediation. Verification uses the
pinned-source review, independent micro-oracles, mutation checks, corrected
synthetic golden and corpus QA. It must not be described as executable ppy/osu
parity.

## Artifact policy

- `training/datasets/golden_reference_v01/` and
  `training/datasets/reference_signal_qa/` are immutable historical evidence.
- Corrected artifacts belong under `golden_reference_v02/` and
  `reference_signal_qa_v02/`.
- Segment and disagreement artifacts derived from v0.2 must receive new
  derived versions even though their JSON field surface can remain stable.

## Verification evidence

- Identity-sensitive Reading regression and version boundary:
  `tests/test_foundation_remediation_v01.py`.
- Corrected golden: `training/datasets/golden_reference_v02/`, 128/128.
- Corpus semantic delta, corrected Segment QA and challenge results:
  `docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md`.

The machine-readable source of truth is
`src/osu_skill_profiler/reference/ppy/contract.py`.
