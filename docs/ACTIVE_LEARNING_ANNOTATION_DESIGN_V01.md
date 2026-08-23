# Active Learning & Human Annotation Design v0.1

Status: **PASS — READY FOR A SMALL HUMAN JUDGEABILITY PILOT WITH CAVEATS**

```text
ACTIVE_LEARNING_ANNOTATION_DESIGN: PASS
READY_FOR_SMALL_HUMAN_ANNOTATION_PILOT: YES_WITH_CAVEATS
```

## Objective and boundary

This phase builds deterministic infrastructure for choosing useful pairwise
questions, preserving raw human responses and auditing annotation behaviour.
It stops before real collection, taxonomy refinement and model training.

It does not modify Feature 0.2, Local 0.3, Reference 0.2, canonical
segmentation, Weak Supervision v0.1 evidence, or target-leakage policy. Weak
Evidence and HUMAN evidence are both evidence, never ground truth.

## UNAVAILABLE gate

All 42 Weak Supervision pilot `UNAVAILABLE` records were joined back to the
Feature/Local/Reference 5k artifacts. Local SEGMENT rows were reconstructed by
calling the production `segment_local_signals(...)`, not a copied segmenter.

```text
legitimate_unavailable: 41
unexpected_unavailable:  1
unresolved:               0
gate:                  PASS
```

The one unexpected record is `ALV01-UNAVAILABLE-001`: the historical pilot
Reference summary retained only values greater than zero, so a map with 511
valid zero values was marked unavailable. Reference 0.2 itself is intact. The
old pilot artifact is preserved unchanged; Active Learning v0.1 explicitly
excludes that map. This is contained and non-blocking for candidate selection,
but remains a known historical pilot defect.

## Propositions

The dry run asks about three existing provisional hypotheses:

- `movement_demand_high`;
- `dense_timing_pressure_high`;
- `slider_tracking_travel_high`.

`slider_control_load_high` is not selected because the current bounded visual
presentation does not yet establish that humans can reliably judge its
combined slider duration/repeat semantics. No proposition is promoted to a
final skill axis.

## Candidate score

Every eligible entity/proposition group retains all Weak Evidence statuses and
snapshot hashes. `UNAVAILABLE` and `INVALID` groups are excluded. The score is
a deterministic acquisition priority, not probability or confidence.

Components in `[0,1]` are:

```text
uncertainty                    0.18
independent disagreement       0.18
abstention pressure            0.18
boundary proximity             0.14
low effective support          0.12
novelty / underrepresentation  0.10
challenge audit bonus          0.10
```

Pair construction additionally records `pair_proximity`; pair acquisition is
`0.8 * mean(entity acquisition) + 0.2 * pair proximity`. The real pilot has no
directional conflicts, so its disagreement component is zero. Tests may use
synthetic conflict, but the real batch never fabricates one.

## Pairing, diversity and controls

Pairs share proposition and scope. Ordinary near-neighbour pairs emphasize
boundary and uncertainty; a bounded low/high contrast supplies anchors. The
builder also selects abstention-heavy, challenge-audit and same-map different-
segment pairs.

Sampling groups from
`training/datasets/splits/v02/set_disjoint.jsonl` are used only for batch
diversity. They are not model inputs or annotator hints. Ordinary source-pair
limits are:

```text
per map:              3
per beatmap set:      5
per mapper:           5
per evidence bucket: 24
```

All six control values are executable. Exact repeat/inversion are the only
explicit duplicate bypass. Blind payloads hide every control identity.

## Response, reliability and presentation

The field contract is in
[`HUMAN_ANNOTATION_CONTRACT_V01.md`](HUMAN_ANNOTATION_CONTRACT_V01.md).
Raw responses, disagreement and abstention are preserved. The diagnostics do
not collapse annotators to “accuracy” against weak rules.

SEGMENT tasks reuse the production canonical entity identity and present a
2,000 ms pre-roll, 1,500 ms post-roll, object visualization, neighboring
context, audio where available and explicit NM. Replay/video is optional.
Weak evidence, acquisition, split/challenge and control metadata are blind.

## Deterministic batch

The generator reads the existing 1,000-map Weak Supervision pilot, corrected
Feature 0.2 rows and v02 split identities. Stable IDs use canonical JSON and
SHA256; outputs contain no timestamp, UUID, absolute path or non-finite value.
The same source bytes, generator version, config and seed must reproduce the
same ordered task bytes.

Dry-run artifacts are under ignored local path:

```text
training/datasets/active_learning_v01/dry_run/
```

The human-readable evidence report records exact counts, hashes and replay
results. No human response or semantic conclusion exists yet.

## Taxonomy refinement hooks

Future analysis can inspect high abstention, low repeat/inversion consistency,
cross-annotator directional disagreement, response distributions and
proposition-specific transitivity. These signals can reveal an unjudgeable
proposition, inconsistent annotator semantics, indistinguishable hypotheses
or a hypothesis that needs decomposition. v0.1 performs no automatic merge,
split, exclusion or taxonomy freeze.

## Caveats

- The three questions have not passed a real annotator usability study.
- Weak-rule thresholds and acquisition weights are deterministic design
  choices, not empirically calibrated quantities.
- The real pilot contains no directional weak-source conflict.
- The presentation is a serialized contract, not a completed annotation UI.
- `ALV01-UNAVAILABLE-001` is contained but the historical Weak Supervision
  artifact is deliberately not rewritten.
- HUMAN evidence remains subjective evidence and cannot authorize training by
  itself.

These caveats support `YES_WITH_CAVEATS` only for a small judgeability pilot.
They do not mean that a taxonomy is correct or that model training should
start.
