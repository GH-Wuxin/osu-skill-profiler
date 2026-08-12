# Target Leakage Enforcement v0.1

Status: **IMPLEMENTED; hard gate**

Policy version: `0.1.0`

This document closes red-team finding RT-05. The prose threat model remains
useful context, but future dataset/model schemas now have an executable,
default-deny input/target gate.

## Components

| Component | Purpose |
| --- | --- |
| `src/osu_skill_profiler/dataset/leakage.py` | role registry, declared-lineage closure and deterministic audit result |
| `tools/target_leakage_audit.py` | CLI hard gate; exit 0 on PASS, 1 on leakage, 2 on unreadable/invalid JSON |
| `tests/test_target_leakage.py` | synthetic PASS/FAIL and CLI regressions |

No model, labels, pseudo-label dataset or training matrix is created by this
infrastructure.

## Signal roles

The central registry supports:

```text
OBSERVABLE_INPUT_CANDIDATE
REFERENCE_ONLY
WEAK_LABEL_SOURCE
HUMAN_LABEL
GROUND_TRUTH
PROVENANCE_ONLY
SPLIT_METADATA
CHALLENGE_SELECTION
IDENTITY_ONLY
DEPRECATED_FOR_NEW_MODELS
```

Important policy assignments:

- corrected Feature v0.2 and Local v0.3 observable fields are candidates,
  not automatically approved training inputs;
- every `ref.ppy.*` evaluator field is `REFERENCE_ONLY`;
- split membership, group identity and challenge-selection fields are
  forbidden inputs;
- provenance is forbidden unless a future experiment changes the central
  policy explicitly;
- historical Feature v0.1 `slider.repeats_total` and
  `slider.repeats_max` are `DEPRECATED_FOR_NEW_MODELS`.

Candidate schemas cannot override an existing central role.

## Default-deny schema

The validator reads a JSON object with these fields:

```json
{
  "input_fields": [],
  "target_fields": [],
  "weak_label_sources": [],
  "offline_evaluation_fields": [],
  "split_fields": [],
  "provenance_fields": [],
  "challenge_fields": [],
  "field_roles": {},
  "declared_lineage": {}
}
```

Unknown inputs fail. A candidate cannot self-promote an unknown field merely
by declaring it observable; a derived candidate must be explicitly registered
with lineage and an allowed role. Targets require an explicit
`WEAK_LABEL_SOURCE`, `HUMAN_LABEL` or `GROUND_TRUTH` role.

## Declared lineage

The gate checks transitive declared source closure. It deliberately does not
attempt arbitrary symbolic algebra.

Example:

```json
{
  "input_fields": ["derived.ref_speed_zscore"],
  "target_fields": ["label.derived_ref_speed"],
  "declared_lineage": {
    "derived.ref_speed_zscore": ["ref.ppy.speed"],
    "label.derived_ref_speed": ["ref.ppy.speed"]
  }
}
```

This fails because input and target share protected lineage
`ref.ppy.speed`. Unknown lineage sources also fail; they never silently pass.

## Enforced cases

Synthetic regressions cover:

| Case | Expected |
| --- | --- |
| observable input to independent future human label | PASS |
| `ref.ppy.flow` input to target derived from the same source | FAIL |
| deterministic derivative of `ref.ppy.speed` on both sides | FAIL |
| split membership as input | FAIL |
| challenge flag as input | FAIL |
| target directly included as input | FAIL |
| Reference signal used only for offline evaluation | PASS |
| unknown input or lineage source | FAIL |
| candidate override of central Reference role | FAIL |
| historical misnamed Feature repeat field | FAIL |

The validator returns exact violation codes and reasons; hard violations do
not have a warning-only mode.

## Command

```powershell
python tools/target_leakage_audit.py path/to/candidate-schema.json \
  --out path/to/leakage-evidence.json
```

A PASS is necessary but not sufficient for a future training run. The exact
materialized matrix, label artifact and fit-on-train preprocessing still need
their own content-addressed verification before weak supervision begins.

## Explicit non-goals

- no weak labels;
- no heuristic or pseudo targets;
- no taxonomy;
- no model training;
- no arbitrary mathematical equivalence solver;
- no claim that every observable candidate is useful or causally valid.
