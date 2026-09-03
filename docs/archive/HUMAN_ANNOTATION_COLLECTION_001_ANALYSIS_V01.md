# Human Annotation Collection 001 — Interim Analysis v0.1

Date: 2026-08-14<br>
Repository: `osu-skill-profiler`<br>
Collection: `collection_001`<br>
Snapshot: `snapshot-dcb68f7c644b4527dba02381`

## 1. Status and boundary

This is a content-addressed, point-in-time analysis of the live multi-annotator
collection. The live response directory may continue to grow after this
snapshot; later responses must produce a new snapshot instead of rewriting
this one.

```text
MULTI_ANNOTATOR_COLLECTION_ANALYSIS: INTERIM_PASS
RAW_HUMAN_EVIDENCE_VALIDATED:        YES
READY_TO_CONTINUE_COLLECTION:        YES
READY_FOR_MODEL_TRAINING:             NO
READY_TO_FREEZE_TAXONOMY:             NO
MAJORITY_VOTE_LABELS_CREATED:         NO
```

`INTERIM_PASS` means that the captured records satisfy the response,
assignment, provenance and identity contracts and already support bounded
usability/agreement diagnostics. It does not mean that the three provisional
phenomena are final skills or that human responses are ground truth.

## 2. Immutable evidence binding

Generated snapshot directory:

```text
training/datasets/active_learning_v01/human_pilot_v02/
collections/collection_001/analysis/snapshot-dcb68f7c644b4527dba02381/
```

SHA-256:

| Artifact | SHA-256 |
|---|---|
| `manifest.json` | `7f6c168e9c58ad2ac4269baa3ac37933c8eba081717371977dabec7ff125485e` |
| `responses.jsonl` | `245b85c99b43fdfd12d305e03da29501e9fd4d8998d4faf33d38333b094e2486` |
| `human_evidence.jsonl` | `16fdc2aed9609fee7734d5624695f679620dcf96fdfacbef4ab492e8c205ebb8` |
| `analysis.json` | `8aa460001eff4e9fead000bcc14c56638145f7c0b00e3d41c4fdfa71c5dca3a9` |
| `REPORT.md` | `4f0798051023d7f80fc1aa6bb8c3cbb059a2e572891c640073d4f238e1ef8f70` |

The snapshot contains no recovery code or persisted `session_token_hash`.
Raw response timestamps and pseudonymous annotator/session identities remain
preserved as response provenance.

## 3. Capture and validation

The analyser reads `collection.json` and every declared response file twice.
If the registry or a response file changes during capture, it retries instead
of mixing two collection states. It then validates:

- the collection points to the exact immutable 40-task v0.2 pilot;
- response paths remain inside the collection directory;
- participant, session and response paths are unique;
- each response file is a prefix of that participant's assigned five tasks;
- response, task, batch, presentation-order and pilot identities agree;
- each response ID equals the deterministic session/task identity;
- submissions carry explicit HUMAN provenance;
- duplicate responses, undeclared files and malformed JSONL fail closed.

Accepted capture:

| Item | Count |
|---|---:|
| Allocated participant IDs | 31 |
| Participants with at least one response | 14 |
| Complete five-response sessions | 11 |
| Partial sessions | 3 |
| Valid raw responses | 59 |
| Unique response IDs | 59 |
| Covered tasks | 40 / 40 |
| Tasks with one response | 21 |
| Tasks with two responses | 19 |

Partial sessions are preserved as partial HUMAN evidence. Missing answers are
not imputed.

## 4. Overall response diagnostics

Observed response distribution:

| Answer | Count |
|---|---:|
| `A_CLEARLY_HIGHER` | 16 |
| `A_SLIGHTLY_HIGHER` | 6 |
| `APPROX_EQUAL` | 4 |
| `B_SLIGHTLY_HIGHER` | 16 |
| `B_CLEARLY_HIGHER` | 17 |
| `CANNOT_JUDGE` | 0 |

Position diagnostic among the 55 directional responses:

```text
first-presented-side rate: 0.4909
```

No material first-side tendency is visible in this small snapshot. This is a
descriptive diagnostic, not a significance test.

Recorded response time:

| Statistic | Milliseconds |
|---|---:|
| P25 | 20,635.5 |
| Median | 40,099 |
| P75 | 77,570 |

These are page elapsed times. They are not direct measurements of attention,
expertise or effort.

Confidence was optional and unset on 48/59 responses. The remaining values
were HIGH 8, MEDIUM 2 and LOW 1. They are preserved as non-probabilistic
self-reports and are not used as response weights.

## 5. Same-task inter-annotator evidence

Nineteen tasks have two independent responses. Across those nineteen pairs:

```text
directional agreement:             16 / 19 = 0.8421
mean normalized ordinal distance:            0.1711
```

Breakdown:

| Provisional proposition | Overlap pairs | Directional agreement |
|---|---:|---:|
| `dense_timing_pressure_high` | 8 | 8/8 = 1.0000 |
| `movement_demand_high` | 6 | 5/6 = 0.8333 |
| `slider_tracking_travel_high` | 5 | 3/5 = 0.6000 |

The slider proposition is the weakest observed presentation/judgement surface
in this snapshot. Five overlap pairs are too few to estimate a stable general
rate, but the difference is large enough to justify targeted monitoring as
second coverage continues.

The three direction-disagreeing tasks are:

| Task | Proposition | Canonical answers |
|---|---|---|
| `task-55b0b9f0e001269a94698d85` | slider tracking | `APPROX_EQUAL`, `B_SLIGHTLY_HIGHER` |
| `task-b863fbee3a4211e4b959054d` | movement demand | `A_SLIGHTLY_HIGHER`, `B_SLIGHTLY_HIGHER` |
| `task-d4f690cb01133542a5b3a3bf` | slider tracking | `A_CLEARLY_HIGHER`, `B_CLEARLY_HIGHER` |

The last row is a maximum-direction conflict and is the highest-priority item
for a third independent judgement or direct presentation review. No answer is
automatically relabelled.

## 6. Controls

Controls are paired explicitly through `source_task_id`; the analysis does not
infer repeat/inversion relationships from response order.

Same-annotator control evidence currently has almost no power:

| Control | Comparable pairs | Directional | Strict ordinal |
|---|---:|---:|---:|
| Exact repeat | 1 | 1/1 | 1/1 |
| A/B inversion | 0 | unavailable | unavailable |

This cannot establish intra-annotator reliability.

Cross-annotator source/control comparisons:

| Control | Comparable pairs | Directional agreement | Strict ordinal agreement |
|---|---:|---:|---:|
| Exact repeat | 8 | 0.7500 | 0.3750 |
| A/B inversion | 7 | 0.7143 | 0.7143 |
| Combined | 15 | 0.7333 | 0.5333 |

These comparisons mix control/presentation stability with ordinary differences
between people. They must not be reported as repeat reliability for one
annotator.

Easy anchors have 3 comparable responses and 3/3 directional agreement. This
is an anchor diagnostic, never annotator accuracy.

## 7. Judgeability observations

`CANNOT_JUDGE` was selected 0/59 times even though the interface explicitly
offers it. This does not prove all questions were easy to judge. Possible
explanations include genuinely judgeable samples, reluctance to abstain, or
the remaining wording/interaction still encouraging forced choices. The
current evidence cannot distinguish these explanations.

Only two optional notes were submitted. Absence of a note is not evidence that
the question had no usability issue.

## 8. Interim decision and next evidence gate

The response pipeline is usable and the current HUMAN evidence is internally
valid. The strongest current finding is proposition-specific:

- dense timing pressure is the most consistently judged surface so far;
- movement demand is mostly directionally consistent but has one conflict;
- slider tracking remains materially less stable and contains the only
  maximum-direction conflict.

The natural next collection milestone is uniform second coverage:

```text
40 tasks × 2 responses = 80 responses
current responses       = 59
remaining for 2× cover  = 21
```

This is a recommended evidence milestone, not a training gate. Once reached—or
if collection is explicitly stopped earlier—the analyser should capture a new
snapshot and repeat the same diagnostics. A third judgement should be
prioritised for direction-conflict tasks only after the second-coverage tier is
complete, matching the allocator's existing least-answered-first policy.

No model was trained, no taxonomy was frozen, no majority-vote label was
created, and no Foundation or Weak Supervision semantic was changed.
