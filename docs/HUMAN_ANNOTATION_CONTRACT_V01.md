# Human Annotation Contract v0.1

Status: **IMPLEMENTED FOR A SMALL DRY-RUN; HUMAN EVIDENCE IS NOT GROUND TRUTH**

This contract represents pairwise questions and raw human judgements about a
small set of versioned, provisional phenomena. It is not a label schema, a
final osu! skill taxonomy, or authorization to train a model.

## Task

`AnnotationTask` v0.1 supports only compatible pairs:

- `MAP_PAIR`: MAP versus MAP;
- `SEGMENT_PAIR`: canonical five-second SEGMENT versus SEGMENT.

Each task contains a stable task/batch/version identity, proposition key and
version, two content-addressed entities, selection reason, all acquisition
components, weak-evidence snapshot hashes, provenance, presentation order,
presentation contract version, and an explicit control relationship. MAP to
SEGMENT comparisons fail closed.

The internal task artifact is auditable and therefore contains sampling and
selection metadata. Annotators receive a separate `blind_task_payload` that
omits weak evidence, scores, selection reason, split/challenge membership,
mapper/set sampling identities, and control identity.

## Pairwise answer

The answer space is:

```text
A_CLEARLY_HIGHER
A_SLIGHTLY_HIGHER
APPROX_EQUAL
B_SLIGHTLY_HIGHER
B_CLEARLY_HIGHER
CANNOT_JUDGE
```

`CANNOT_JUDGE` is a first-class abstention. It is never converted to equality
and is excluded from ordinal-direction denominators with the excluded count
reported.

Presentation order is recorded. Responses are normalized to the stable
unordered entity orientation before comparison, so A/B inversions can be
audited without changing semantics.

## Response and HUMAN evidence

`AnnotationResponse` v0.1 records stable response, task, batch, annotator and
session identities; the raw answer and presentation order; optional
non-negative response time; optional non-probabilistic confidence band and
reason codes; and provenance.

The `ResponseLedger` rejects unknown tasks, unknown annotators, duplicate
response IDs and a second response by the same annotator to the same task
version. Accepted responses remain intact. Contradictory responses from
different annotators are preserved rather than voted away.

Every accepted response becomes one `HUMAN` evidence record containing the
raw response, normalized ordinal when applicable, provenance, and:

```text
HUMAN EVIDENCE != LABEL != GROUND TRUTH
```

No annotator “accuracy” against Weak Evidence is defined.

## Controls

The batch builder supports `EXACT_REPEAT`, `AB_INVERSION`, `EASY_ANCHOR`,
`AMBIGUOUS_CONTROL`, `WITHIN_MAP_SEGMENT`, and ordinary `NONE` tasks.

Only exact repeat and inversion controls may intentionally reuse an unordered
pair, and they must reference their source task and control group. Accidental
pair duplication fails closed. Anchor agreement is diagnostic only because
the anchor expectation is not ground truth.

## Presentation v0.1

The deterministic presentation contract requires:

- canonical playable segment window;
- 2,000 ms pre-roll and 1,500 ms post-roll;
- neighboring pattern context;
- object visualization;
- audio where available;
- explicit unmodded (`NM`) context;
- anonymous neutral metadata;
- optional replay/video, never assumed to exist.

MAP tasks use the full map. A later user interface must satisfy this contract
before collecting real responses; this phase does not implement or usability-
validate such a UI.

## Diagnostics

The v0.1 metrics report response distribution, abstention, exact-repeat and
inversion consistency, first-presented-side bias, anchor agreement,
directional inter-annotator agreement, normalized weighted ordinal
disagreement, and diagnostic pairwise transitivity. Famous agreement
coefficients are intentionally omitted where current data does not meet their
assumptions.
