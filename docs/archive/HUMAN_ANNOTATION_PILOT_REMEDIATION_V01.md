# Human Annotation Pilot Remediation v0.1

Date: 2026-08-13<br>
Repository checkpoint inspected: `bc8655c2fa5d3f23807048c921cfd7f1e75bcdb9`<br>
Remediation status: `PASS`

This report separates direct observations from interpretation:

- **OBSERVED** means reproduced from the immutable tasks, responses, source
  assets, generated artifacts, or tests.
- **INFERRED** means the most conservative explanation supported by those
  observations.
- **UNKNOWN** means the available single-session evidence cannot decide the
  question.

## FIRST_PILOT_DISPOSITION

Raw response artifact:

```text
training/datasets/active_learning_v01/human_pilot_v01/
responses/annotator_001/pilot_session_001.jsonl
```

Verified SHA-256:

```text
e366289f6dd18264e9c1f1ac1fbcb731553448b120abdee14fa04dc2c75e046b
```

**OBSERVED**

- The artifact contains 40 of 40 expected responses, in the original task
  order, for `annotator_001`, `pilot_session_001`, and
  `al01-human-pilot-001`.
- Task identities, presentation orientation, response enums, JSONL syntax,
  and control relationships validate; no duplicate response exists.
- The raw response artifact and its v0.1 task/manifest artifacts were not
  rewritten by this remediation.
- `docs/HUMAN_ANNOTATION_PILOT_SESSION_001_DISPOSITION.json` binds the exact
  response hash and records `immutable: true`, `usability_evidence: true`, and
  `training_eligible: false`.
- `assert_training_eligible(...)` fails closed when the disposition is
  missing, has the wrong schema or hash, or explicitly excludes training.

Disposition:

```text
USABILITY_EVIDENCE: YES
TRAINING_ELIGIBLE: NO
```

The exclusion is not a judgement that the human answered carelessly. The
session exposed presentation-invalid content, empty proposition domains,
ambiguous wording, and an over-concentrated candidate mix. It was also a
single-annotator usability pilot, not an accepted source of training
supervision.

## FIRST_PILOT_RECONSTRUCTION

### Composition and timing

**OBSERVED**

- 40 responses: 10 MAP/MAP and 30 SEGMENT/SEGMENT.
- 30 of 40 tasks used
  `ws01.provisional.slider_tracking_travel_high`.
- No `CANNOT_JUDGE` response was selected.
- Total recorded response time was 1,364,090 ms; the median was 23.223 s.
- Five slider tasks had no slider on at least one presented target side.
- One Aspire map expanded to an approximately 119.8-minute object timeline
  and also carried presentation-unsafe timing behaviour.

### Reliability controls

**OBSERVED**

| Diagnostic | Result |
|---|---:|
| Easy-anchor directional agreement | 2/2 |
| Exact-repeat strict ordinal consistency | 0/2 |
| Exact-repeat directional consistency | 0/2 |
| Exact-repeat ordinal distances | 4, 1 |
| A/B-inversion directional consistency | 2/2 |
| A/B-inversion strict ordinal consistency | 1/2 |
| A/B-inversion ordinal distances | 0, 1 |

**INFERRED**

- The exact-repeat results are a serious warning about the combined task,
  presentation, and single-session measurement process.
- The anchors and orientation-normalized inversions show that the responses
  were not simply random or consistently tied to screen position.

**UNKNOWN**

- Two repeats are not enough to estimate general annotator reliability or
  proposition-class reliability.
- This session cannot isolate how much repeat disagreement came from human
  judgement, multidimensional propositions, wording, sample eligibility,
  playback, or fatigue.

### Notes

**OBSERVED**

- 13 responses contain free-text notes.
- Notes 8, 18, 23, and 32 explicitly point to a side with no or effectively no
  visible slider; note 22 says both sides have little slider content.
- Notes 13 and 30 point to an extremely small slider sample. In particular,
  note 13 says side B has only its final slider and explicitly compares that
  single slider. This is evidence about the sample/question combination, not
  proof that the annotator misunderstood the question.
- Note 17 identifies a within-map relationship; this is not itself a defect.
- Note 39 identifies the Aspire content.
- Note 40 explicitly reports that the comparison was hard and approximately
  equal, but the formal answer remained `APPROX_EQUAL` rather than
  `CANNOT_JUDGE`.

The notes are retained only as usability evidence. No response was relabelled
from its note.

Per-note usability classification:

| Response index | Note (verbatim) | Primary issue classification |
|---:|---|---|
| 1 | `右边连打更多一点` | other: gameplay judgement rationale |
| 8 | `A有滑条吗你就来移动距离？？` | missing relevant object / empty proposition domain |
| 13 | `这B怎么只有结尾一个滑条。。。不过B确实更长，我指的是单个滑条距离` | sample-composition oddity and proposition ambiguity |
| 14 | `都很低。。。` | genuine difficulty/equality judgement rationale |
| 17 | `这难道不是同一首歌？` | sample relationship observation (intentional within-map comparison) |
| 18 | `A的滑条呢？` | missing relevant object / empty proposition domain |
| 22 | `都没什么滑条` | insufficient relevant content / sample-composition oddity |
| 23 | `左边的滑条呢。。。` | missing relevant object / empty proposition domain |
| 25 | `A连个连打都没有` | sample-composition/control-design oddity |
| 30 | `A的滑条都是短的，但是B只有一个滑条啊` | insufficient relevant content / sample-composition oddity |
| 32 | `B都没什么滑条` | missing relevant object; note/answer relationship remains unresolved |
| 39 | `虽然A是Aspire，但是B还是更高` | pathological content / presentation eligibility defect |
| 40 | `不好判断，感觉都差不多` | genuine difficulty judging and abstention-affordance evidence |

These categories describe the interface or sample issue surfaced by each
note. They do not reinterpret, correct, or invalidate the associated formal
answer.

## ROOT_CAUSE_CLASSIFICATION

### Presentation

**OBSERVED**: the first runner admitted content that parsed but could not be
meaningfully played or rendered, including the Aspire timeline. The v0.1
slider question did not operationally distinguish a high-tail statistic from
total distance, longest individual slider, or slider count.

### Eligibility

**OBSERVED**: parse success and audio-path presence were insufficient. Some
slider questions had an empty human proposition domain; one Aspire task had
unsafe time and timing presentation properties.

### Proposition semantics

**OBSERVED**: the machine slider signal is a canonical five-second-segment
P90 over corrected CS-normalised Local lazy slider-follow distance across
object rows; non-slider rows are zero. A human question about typical long
slider following is not meaningful when a side contains no slider.

### Balancing

**OBSERVED**: slider tracking occupied 75% of v0.1. The source selection
ranked across uneven proposition availability without a pilot-level maximum,
so the most available segment proposition dominated.

### Controls and statistical power

**OBSERVED**: v0.1 contained only two exact repeats, two inversions, and two
easy anchors. That is enough to expose a problem, but not enough to estimate a
stable rate.

### Annotation contract

**OBSERVED**: `CANNOT_JUDGE` was available but selected zero times while notes
still recorded uncertainty or insufficient content. The old interface did not
make sufficiently clear that abstention is valid and useful rather than a
failed answer.

### Genuine human inconsistency

**OBSERVED**: the two exact repeats disagree after canonical orientation
normalization. The disagreement is preserved.

**UNKNOWN**: current evidence cannot assign that disagreement solely to the
annotator. The second pilot is an experiment to test whether remediation
improves judgeability; it does not guarantee agreement.

## PRESENTATION_ELIGIBILITY

Human Presentation Eligibility contract version: `0.2.0`.

The validator resolves the real map and canonical entity, parses the `.osu`,
probes audio coverage, reconstructs the requested presentation window, and
checks concrete renderer and temporal properties. It rejects fail-closed for:

- unavailable map or audio assets;
- unknown audio duration or uncovered audio window;
- non-std maps or unresolved/empty entities;
- non-finite timing, presentation-unsafe BPM or SV;
- an excessively long interactive timeline;
- objects outside the supported renderer;
- unrenderable slider geometry or unrepresentable traversal;
- an empty proposition domain;
- a proposition not yet human-judgeable.

Operational presentation limits are:

```text
interactive timeline: 45 minutes
BPM:                  1000
SV:                    100
```

These are not canonical osu! validity rules. In the inspected 153-map v0.1
source batch, the longest non-Aspire timeline was approximately 35.9 minutes,
the maximum non-Aspire BPM was 780, and the maximum non-Aspire SV was 50. The
Aspire case was approximately 119.8 minutes. The limits therefore form a
conservative browser-presentation envelope around observed non-Aspire source
content.

**OBSERVED**

- Of 93 v0.1 source tasks inspected, 79 pass and 14 fail v0.2 presentation
  eligibility.
- Side-level rejection occurrences are: audio duration unavailable 6, audio
  unavailable 4, empty proposition domain 7, object outside renderer 2, and
  one each for uncovered audio window, unsafe BPM, unsafe SV, excessive
  timeline, unrenderable slider geometry, and unrepresentable traversal. A
  task or side may have more than one reason, so these are not task totals.
- Every selected v0.2 task passes the gate.
- A synthetic entity carrying `pathological_challenge` but remaining
  playable passes. Challenge labels are diagnostics and never the rejection
  shortcut.

Aspire disposition: rejected from ordinary human annotation because of its
concrete presentation properties, retained in the underlying challenge data.

## EMPTY_DOMAIN_SEMANTICS

Affected active proposition:

```text
ws01.provisional.slider_tracking_travel_high
```

Human presentation policy:

```text
EMPTY_DOMAIN_POLICY: PAIR_INELIGIBLE
```

If either target segment has no slider, the pair cannot enter the human
batch. Both-empty and one-empty cases are covered by tests.

This does not change verified machine semantics. Non-slider object rows
remain zero in the machine signal. The remediation only refuses to turn an
empty set of sliders into a human comparison of “the longer group of
sliders.” A computed zero remains distinct from unavailable, undefined, and
an empty human proposition domain.

## PROPOSITION_REMEDIATION

Three propositions remain eligible for the second usability pilot:

| Proposition | Scope | Human judgement |
|---|---|---|
| `movement_demand_high` | MAP/MAP | which map more often combines faster cursor movement with larger spans |
| `dense_timing_pressure_high` | MAP/MAP | which map more often contains sustained rapid-click density |
| `slider_tracking_travel_high` | SEGMENT/SEGMENT | which segment's longer group of sliders typically requires farther continuous following |

Each serialized contract states the machine semantic, Chinese question,
what to observe, what is explicitly not being asked, scope, empty-domain
policy, presentation requirements, `CANNOT_JUDGE` criteria, and known
ambiguity.

For slider tracking, the interface explicitly says:

- do not sum all slider distances;
- do not compare only the single longest slider;
- do not compare slider count.

`slider_control_load_high` is marked
`NOT_YET_HUMAN_JUDGEABLE` and excluded. Its current conjunction of slider
ratio, duration P90, and repeat count cannot yet be translated into one stable
human judgement without silently changing the phenomenon.

The blind payload never includes weak evidence, expected direction,
acquisition score, hidden control relation, split/challenge classification,
or first-pilot answers.

## BALANCING

Old composition:

```text
slider tracking: 30 / 40 (75%)
MAP/MAP:          10 / 40
SEGMENT/SEGMENT:  30 / 40
```

The v0.2 builder uses fixed, explicit base proposition quotas followed by
deterministic within-proposition acquisition ranking. Controls are allocated
separately and transparently. It does not lower or reinterpret Weak Evidence
scores.

Resulting v0.2 composition:

```text
movement demand:       10 / 40
dense timing pressure: 14 / 40
slider tracking:       16 / 40 (40%)
MAP/MAP:               24 / 40
SEGMENT/SEGMENT:       16 / 40
```

The balancer fails closed when a required proposition lacks enough eligible
candidates and records the shortage. An adversarial dominated input confirms
that raw slider abundance cannot take over the batch.

## PILOT_V02

Pilot identity and generator:

```text
pilot_id:          al02-human-pilot-001
batch_id:          al02-human-pilot
schema_version:    0.2.0
generator_version: 0.2.0
seed:              osu-skill-profiler-second-human-pilot-v02
```

Composition:

| Item | Count |
|---|---:|
| Total tasks | 40 |
| MAP/MAP | 24 |
| SEGMENT/SEGMENT | 16 |
| Exact repeats | 4 |
| A/B inversions | 4 |
| Easy anchors | 2 |
| Ambiguous controls | 2 |
| Explicit hidden controls | 12 |
| Unique maps / sets / mappers | 61 / 61 / 60 |
| Formal responses | 0 |

Paired repeat/inversion controls are separated from their source by at least
20 task positions. Repeat interpretation records strict ordinal consistency,
directional consistency, and ordinal distance. Inversion responses are
canonicalized for A/B orientation before those metrics. Anchors report
`anchor_agreement`, never annotator accuracy. Ambiguous controls allow
approximate equality or `CANNOT_JUDGE` according to the contract.

The response interface is Chinese-first, shows CS, requires explicit play,
supports play/pause/seek/resume, animates slider traversal including repeats,
and explains that `CANNOT_JUDGE` is a valid and useful answer. Browser QA was
performed muted with `?qa_muted=1`; it submitted no response and observed no
browser warning or error.

Generated v0.2 artifacts live separately under:

```text
training/datasets/active_learning_v01/human_pilot_v02/
```

The formal response directory exists and is empty.

## DETERMINISM

The latest canonical generation reports manifest SHA-256:

```text
sha256:2a301d77a6a8518bdefa2d8ea2661022cfaac1de7a3f1061f0cc22212abab19c
```

Key output hashes:

```text
pilot_tasks.jsonl  sha256:5b0e8f433f1ec1f1f4ff54e9745a5e54b5c1195f5b02e2212fca59963faa51e5
blind_pilot.jsonl  sha256:4b99f6e327029fa9f53b54c8e9ed3a8d767b411c0ffc976cdbc6232db766a811
control_manifest   sha256:0283bbc64a4bb3b8381e05532d8f91feea3dfc2f65bbf95ad4f421188f54708d
eligibility_report sha256:101419508c4d3c78ab837b4c21c16b05d9de97611b963b2cce8a9e6a0f177163
```

Generation uses stable IDs, stable ordering, strict finite JSON, source
hashes, and an explicit seed. Final validation independently regenerates the
entire output into two temporary directories and requires byte-identical
files.

## LIMITATIONS

- Pilot v0.2 remains a second experiment with the same single annotator; it
  cannot establish inter-annotator reliability.
- Four repeats and four inversions improve diagnostic power but still do not
  justify a universal reliability claim.
- The 45-minute/BPM/SV limits describe the current browser-presentation
  envelope, not osu! legality or final dataset policy.
- Audio duration probing is a bounded preflight, not a full media decoder.
- Human-readable propositions remain provisional and multidimensional. A
  human answer is evidence, not taxonomy ground truth.
- `slider_control_load_high` needs semantic redesign before another human
  pilot can include it.
- Pilot v0.2 contains no formal response yet, so remediation success means
  “ready to test,” not “shown to improve agreement.”
- No model was trained, no taxonomy was frozen, and no verified Foundation or
  Weak Supervision semantics were changed.

Final bounded validation:

```text
targeted Active Learning / human annotation tests: 37 / 37 PASS
full unit suite:                              263 / 263 PASS
compileall:                                            PASS
strict JSON/JSONL and finite-value audit:              PASS
blindness audit:                                       PASS
independent byte-identical regeneration:               PASS
immutable v0.1 / Foundation hashes:                    PASS
git diff --check:                                      PASS
Pilot v0.2 formal response count:                         0
```

Final decision:

```text
HUMAN_ANNOTATION_PILOT_REMEDIATION: PASS
READY_FOR_SECOND_SINGLE_ANNOTATOR_PILOT: YES_WITH_CAVEATS
PILOT_V02_FORMAL_RESPONSE_COUNT: 0
WAITING_FOR_SECOND_HUMAN_ANNOTATION: YES
```

`YES_WITH_CAVEATS` means only that the corrected questions and presentation
are ready for a second small experiment with the same annotator design. It
does not make Session 001 training data, establish annotation reliability,
validate or freeze a taxonomy, authorize multi-annotator collection, or
authorize model training.
