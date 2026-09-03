# Human Annotation Collection 001 — Final Pilot Analysis v0.1

Date: 2026-08-14

Collection: `collection_001`

Final snapshot: `snapshot-a33e951ca690cf1904b0d244`

## 1. Decision

```text
HUMAN_ANNOTATION_PILOT_COLLECTION: COMPLETE_AT_64_RESPONSES
RAW_HUMAN_EVIDENCE_VALIDATED:      YES
ANNOTATION_SURFACE_USABILITY:       PASS_WITH_CAVEATS
READY_FOR_MODEL_TRAINING:           NO
READY_TO_FREEZE_TAXONOMY:           NO
MAJORITY_VOTE_LABELS_CREATED:       NO
```

The pilot is sufficient to show that people can use the current comparison
surface and that the three provisional questions do not behave equally. It is
not sufficient to turn responses into ground truth, train a model, or freeze a
skill taxonomy.

The collection was explicitly stopped before uniform second coverage. This is
a final analysis of this pilot collection, not a claim that further evidence
would have no value.

## 2. Immutable evidence binding

Snapshot directory:

```text
training/datasets/active_learning_v01/human_pilot_v02/
collections/collection_001/analysis/snapshot-a33e951ca690cf1904b0d244/
```

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `manifest.json` | 619 | `b5efbc4ca549c03583f8aae9b8478c87a726d7c1deb4943a03bf2b80b108a0b5` |
| `responses.jsonl` | 37,143 | `a02e9d48630eb2170766dfabf31fedffad4e30103776144cfa278ca5c1195887` |
| `human_evidence.jsonl` | 84,030 | `f309c0b71ea56f98fd2c759e96b17afa4763962e7956fb2793e208f0a2a18a0b` |
| `analysis.json` | 17,080 | `69a529f477d64b70e1862b64a2b1593d90c5fed8d0a2644dcde834548080c710` |
| `REPORT.md` | 1,411 | `315c7d8bedc47b0bc472c9cd3a21d97108cba0c98b9de8990ad083cb12773cc2` |

The analyzer captured the registry and every declared response file through
stable double reads. All 64 records passed task order, response identity,
task/batch/presentation identity, pilot identity, and explicit HUMAN
provenance validation. Recovery codes and token hashes are not copied into the
snapshot.

## 3. Collection state

| Item | Count |
|---|---:|
| Allocated participant IDs | 31 |
| Participants with at least one response | 15 |
| Participants completing at least the initial five | 12 |
| Participants with fewer than five responses | 3 |
| Valid raw responses | 64 |
| Unique response IDs | 64 |
| Covered tasks | 40 / 40 |
| Tasks with one response | 16 |
| Tasks with two responses | 24 |

One participant completed five responses and then requested another five, but
did not answer the added batch. Therefore 11 participants completed their
currently assigned sequence, while 12 completed at least one five-question
batch. No missing answer is imputed.

Compared with the 59-response interim snapshot, the final snapshot adds one
complete five-response participant. All five added responses supplied a second
judgement for previously single-covered tasks; none introduced a new
directional conflict.

## 4. Overall diagnostics

Observed answers:

| Answer | Count |
|---|---:|
| `A_CLEARLY_HIGHER` | 19 |
| `A_SLIGHTLY_HIGHER` | 8 |
| `APPROX_EQUAL` | 4 |
| `B_SLIGHTLY_HIGHER` | 16 |
| `B_CLEARLY_HIGHER` | 17 |
| `CANNOT_JUDGE` | 0 |

Among 60 directional responses, the first-presented-side rate is exactly
`0.5000`. This is a descriptive position diagnostic, not a significance test.

Recorded page elapsed time:

| Statistic | Milliseconds |
|---|---:|
| P25 | 22,336 |
| Median | 39,032.5 |
| P75 | 76,678.25 |

Confidence was optional and unset on 48/64 responses. The 16 supplied values
were HIGH 9, MEDIUM 5, and LOW 2. Confidence is preserved as a
non-probabilistic self-report and is not used as a response weight.

`CANNOT_JUDGE` remained unused. This does not prove every item was clear. It
may reflect judgeability, reluctance to abstain, or the forced-comparison feel
of the interface. Only two optional notes were submitted, so silence cannot be
used as evidence that the wording and playback were universally understood.

## 5. Same-task agreement

Twenty-four tasks have two independent responses. Twenty-one pairs agree in
canonical direction:

```text
directional agreement:             21 / 24 = 0.8750
mean normalized ordinal distance:            0.15625
```

| Provisional proposition | Responses | Double-covered tasks | Directional agreement | Disposition |
|---|---:|---:|---:|---|
| `dense_timing_pressure_high` | 22 | 8 | 8/8 = 1.0000 | retain with construct/wording review |
| `movement_demand_high` | 17 | 7 | 6/7 = 0.8571 | retain with conflict review |
| `slider_tracking_travel_high` | 25 | 9 | 7/9 = 0.7778 | revise/audit before stronger use |

These rates are small-sample diagnostics. The apparent ordering between
propositions is useful for design decisions but is not a stable population
estimate.

## 6. Direction-conflict audit queue

The same three conflicts present in the interim snapshot remain. None is an
explicit control task, so they are not explained by repeat/inversion handling.

| Task | Question | Samples | BID | Canonical responses | Selection context |
|---|---|---|---|---|---|
| `task-d4f690cb01133542a5b3a3bf` | slider tracking | `entity-28f6c5d83fb0` vs `entity-fda9592fc389` | unavailable vs `2718018` | `A_CLEARLY_HIGHER` vs `B_CLEARLY_HIGHER` | `CHALLENGE_AUDIT`; legacy-format + pathological challenge |
| `task-55b0b9f0e001269a94698d85` | slider tracking | `entity-0cf5e9f3b035` vs `entity-3edce19c73f0` | unavailable vs `131` | `APPROX_EQUAL` vs `B_SLIGHTLY_HIGHER` | `CHALLENGE_AUDIT`; legacy-format challenge |
| `task-b863fbee3a4211e4b959054d` | movement demand | `entity-e1a656902cba` vs `entity-b1dddcc90e75` | `4552836` vs `1644339` | `A_SLIGHTLY_HIGHER` vs `B_SLIGHTLY_HIGHER` | `ABSTENTION_HEAVY`; high-boundary, near-paired candidates |

The two unavailable BIDs are absent from the source `.osu` metadata; the
content-addressed checksums and anonymous sample IDs remain sufficient for
local replay. No response is automatically relabelled.

The conflicts are not a random sample of ordinary items. Both slider
conflicts were deliberately selected from upstream-abstained challenge cases,
and the movement conflict was deliberately selected near a weak-evidence
boundary. This is evidence that the acquisition design surfaced genuinely
ambiguous cases. It also means the three conflicts must not be used alone to
estimate ordinary-item judgeability or to reject an entire proposition.

## 7. Controls and reliability limits

Same-annotator explicit controls still provide almost no evidence:

- exact repeat: 1 comparable pair, directionally and ordinally consistent;
- A/B inversion: 0 comparable pairs.

This is insufficient to estimate intra-annotator reliability.

The one same-person exact-repeat pair was shown consecutively in reverse
source/control order. The participant explicitly noted “又让我再填一遍？” and
gave the same answer both times. The control relationship is correctly marked
in the task contract, so this is not an accidental duplicate; however, the
repeat was recognizable, and the lone consistency result cannot be treated as
a blind retest.

Cross-annotator source/control comparisons contain 18 comparable pairings with
combined directional agreement `0.6667` and strict ordinal agreement `0.5000`.
Those pairings mix presentation/control stability with ordinary differences
between people and are combinatorial comparisons, not 18 independent
reliability trials. They must not be described as annotator retest accuracy.

Easy anchors have 3/3 directional agreement. This is an anchor diagnostic,
not evidence that weak supervision is ground truth.

## 8. What is usable

The technical collection path is usable: one shared link, isolated
pseudonymous sessions, deterministic task assignment, append-only responses,
recovery, and content-addressed analysis all operated without malformed or
duplicate accepted evidence.

For question design:

- dense timing pressure has the strongest directional agreement, but one
  participant explicitly distinguished “高密度单点” from “连续点击段”. This is
  evidence that the player-facing “打串” wording may narrow or shift the
  provisional `dense_timing_pressure` construct, so agreement alone does not
  establish construct validity;
- movement demand is usable for another bounded iteration, but its wording
  combines jump distance and cursor speed and should be inspected on the one
  conflict;
- slider tracking is judgeable often enough to keep investigating, but its
  weaker agreement and two persistent conflicts make it unsuitable as a
  settled label definition.

The data support revising and auditing provisional concepts. They do not
support training, majority-vote label creation, participant ranking, or a
claim that these concepts are final osu! skill dimensions.

## 9. Remaining blind spots

- Sixteen tasks have only one response.
- Pseudonymous sessions do not prove that every participant ID is a different
  human or describe player expertise.
- The interface collected no demographic or osu! experience metadata.
- Same-person repeat/inversion evidence is essentially absent.
- The only same-person repeat was recognizable to its participant.
- No abstentions means the abstention affordance itself has not been validated.
- Agreement may reflect the selected 40 tasks and current presentation, not
  the broader beatmap population.
- Slider-path rendering, wording, and the underlying construct can all
  contribute to slider disagreement; this pilot does not identify one sole
  cause.

## 10. Final bounded recommendation

Preserve this snapshot as raw HUMAN evidence and use it only for taxonomy and
presentation review. The next highest-value work is a direct visual replay of
the three conflict tasks, followed by an explicit decision on whether to
revise the slider question and separate movement distance from movement speed.

Do not train a model, freeze the taxonomy, or collapse responses into majority
labels from this collection.
