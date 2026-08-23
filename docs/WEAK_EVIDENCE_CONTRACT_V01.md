# Weak Evidence Contract v0.1

Status: **IMPLEMENTED; PROVISIONAL EVIDENCE ONLY**

Contract version: `0.1.0`

This contract defines versioned evidence about registry-controlled
propositions. It does not define labels, ground truth, calibrated
probabilities, a final osu! skill taxonomy, or a trained model.

## Record identity

`WeakEvidenceRecord` is identified by:

```text
entity stable key
+ proposition key/version
+ rule ID/version
```

Duplicate emission of that tuple in one execution fails. Entities support:

- `MAP`;
- canonical `SEGMENT` identity with map checksum, segment index and bounds;
- reserved `OBJECT` and `OBJECT_PAIR` values for future compatible extension.

The v0.1 pilot emits only `MAP` and `SEGMENT`. Segment bounds and indices come
from the existing Local Signal fixed-time segmentation contract; no competing
segmentation system is introduced.

## Proposition registry

Every proposition is an opaque, versioned registry key. The pilot registry has
four deliberately narrow entries, all marked `PROVISIONAL`:

- `ws01.provisional.movement_demand_high`;
- `ws01.provisional.dense_timing_pressure_high`;
- `ws01.provisional.slider_control_load_high`;
- `ws01.provisional.slider_tracking_travel_high`.

Names describe evidence hypotheses, not canonical player skills. Unknown keys
or versions fail closed.

## Evidence states and values

Every applicable rule emits exactly one status record:

| Status | Meaning |
| --- | --- |
| `EMITTED` | The declared discriminator produced positive, negative, scalar, or pairwise evidence. |
| `ABSTAINED` | Inputs were valid and available, but the rule's assumptions or sparse bounds did not justify evidence. |
| `UNAVAILABLE` | Required source information was absent or geometry/reference evaluation was blocked. |
| `INVALID` | An input violated the rule contract, for example a non-finite or non-numeric value. |

An emitted scalar value of zero is still evidence. It is never converted to
absence. Non-emitted records carry a machine-readable `AbstentionReason` and
cannot carry a value or strength.

Supported value directions are `POSITIVE`, `NEGATIVE`, `SCALAR`, and
`PAIRWISE`. Pairwise representation is schema-supported for future annotation
design; the v0.1 pilot does not emit pairwise records.

## Strength and confidence

`strength` is a deterministic bounded margin in `[0, 1]` relative to the
rule's documented fixed discriminator range. It is not a probability,
posterior, accuracy estimate, or chance that the proposition is objectively
true.

`confidence_band` is `LOW`, `MEDIUM`, or `HIGH` and describes the rule's own
predeclared evidence posture. Each rule documents its semantics. No empirical
calibration claim is made in v0.1.

## Source and lineage

Every record references a registered source ID/version/family. Active source
definitions declare exact field roots, dependencies, reference-only and safety
flags, independence/correlation group, determinism, description, and contract
reference. Unknown sources, dependencies, roots, or versions fail closed.

Source dependencies form a validated DAG. Direct and transitive lineage
closure is materialized into each record. Cycles fail. Evidence shares a
correlation component when it has the same independence group or any shared
semantic root; such records are not counted as independent support.

Schema families include `OBSERVABLE`, `LOCAL_SIGNAL`, `REFERENCE_PPY`,
`DETERMINISTIC_RELATION`, `COMMUNITY`, `HUMAN`, and `MODEL_DERIVED`.
Community, human, and model-derived evidence are interface-compatible but
inactive and not ingested by this phase. Future human/community vote counts,
annotator identities, and reliability metadata can be carried in structured
provenance while pairwise direction remains in the typed evidence value.

## Leakage

`audit_evidence_for_model_inputs()` converts proposition targets and their
complete declared root sets into the existing default-deny Target Leakage
Enforcement v0.1 gate. A model-input candidate fails if it:

- is Reference-only;
- is split, challenge, identity, QA, or provenance metadata;
- overlaps any direct or transitive evidence lineage;
- is unknown to the authoritative role registry.

This gate is necessary but not sufficient for a future materialized training
matrix. No training matrix is created here.

## Serialization

Evidence is stable-key sorted JSONL with UTF-8, sorted object keys, no
timestamps, no absolute paths, and `allow_nan=false`. Any NaN/Infinity fails
before write. Each canonical artifact has a SHA256 and size in its manifest.

The disclaimer is always:

```text
WEAK EVIDENCE != LABEL != GROUND TRUTH
```

## Legacy boundary

The earlier `WeakLabelResult` / `WeakLabelEvidence` API remains unchanged for
the historical deterministic baseline and public output schema. It is not the
v0.1 Weak Evidence contract and its `jump_aim`, `stream`, and
`rhythm_complexity` demonstration strings were not promoted into this
proposition registry. New infrastructure is exposed through
`osu_skill_profiler.weak_supervision.v01`.
