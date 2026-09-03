# Active Learning & Human Annotation Design v0.1 — Handover

Date: 2026-08-13<br>
Repository: `osu-skill-profiler`<br>
Task source: local Codex attachment (not included in the repository)

## 1. Handover status

This task was paused at the user's request after the read-only design and
repository audit. No Active Learning production module, annotation contract,
test, dry-run batch, or Active Learning report has been created yet.

This handover document is the only file added during the handover step. It is
not evidence that the Active Learning phase has passed.

```text
ACTIVE_LEARNING_IMPLEMENTATION_STARTED:       NO
UNAVAILABLE_CLASSIFICATION_COMPLETED:         NO
ANNOTATION_TASK_SCHEMA_CREATED:               NO
ANNOTATION_RESPONSE_SCHEMA_CREATED:           NO
DRY_RUN_BATCH_CREATED:                        NO
TESTS_RUN_DURING_ACTIVE_LEARNING_TURN:         NONE
COMMIT_OR_PUSH_PERFORMED:                      NO
```

The correct current verdict is therefore:

```text
ACTIVE_LEARNING_ANNOTATION_DESIGN: INCOMPLETE
READY_FOR_SMALL_HUMAN_ANNOTATION_PILOT: NOT_YET_ASSESSED
```

## 2. Current repository checkpoint

Rechecked immediately before creating this document:

```text
branch: main
HEAD: bc8655c2fa5d3f23807048c921cfd7f1e75bcdb9
staged diff: empty
```

Pre-existing tracked changes that must be preserved:

```text
 M docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md
 M src/osu_skill_profiler/weak_supervision/__init__.py
```

Pre-existing untracked files that must be preserved:

```text
?? docs/RED_TEAM_BLOCKER_RECHECK_V02.md
?? docs/REFERENCE_FULL_SHA256_TRANSCRIPTION_ERRATA_V01.md
?? docs/WEAK_EVIDENCE_CONTRACT_V01.md
?? docs/WEAK_SUPERVISION_FOUNDATION_PROVENANCE_V01.json
?? docs/WEAK_SUPERVISION_INFRASTRUCTURE_V01.md
?? docs/WEAK_SUPERVISION_PILOT_V01_REPORT.md
?? docs/WEAK_SUPERVISION_V01_HANDOVER_2026-08-13.md
?? src/osu_skill_profiler/weak_supervision/audit_v01.py
?? src/osu_skill_profiler/weak_supervision/contracts_v01.py
?? src/osu_skill_profiler/weak_supervision/leakage_v01.py
?? src/osu_skill_profiler/weak_supervision/pilot_v01.py
?? src/osu_skill_profiler/weak_supervision/registry_v01.py
?? src/osu_skill_profiler/weak_supervision/runtime_v01.py
?? src/osu_skill_profiler/weak_supervision/v01.py
?? tests/test_weak_evidence_v01.py
?? tests/test_weak_supervision_pilot_v01.py
?? tools/performance_probe.py
?? tools/weak_supervision_pilot_v01.py
```

After this handover is written, this file will appear as one additional
untracked path:

```text
?? docs/ACTIVE_LEARNING_V01_HANDOVER_2026-08-13.md
```

Do not use `reset`, `clean`, `restore`, checkout-overwrite, or an automatic
cleanup routine. Do not commit, push, or deploy. The task explicitly requires
the current Weak Supervision delivery to remain intact.

## 3. Important correction to the older handover

`docs/WEAK_SUPERVISION_V01_HANDOVER_2026-08-13.md` describes a much earlier
checkpoint where Weak Supervision implementation had not started. That status
is now historical and must not be used as the current implementation state.

The current worktree contains the completed Weak Supervision v0.1
infrastructure and bounded pilot delivery. Use current source, tests, reports,
and generated pilot artifacts as the factual baseline.

## 4. Accepted Weak Supervision baseline

The completed baseline reports:

```text
WEAK_SUPERVISION_INFRASTRUCTURE: PASS
READY_FOR_ACTIVE_LEARNING_DESIGN: YES_WITH_CAVEATS
tests: 226/226 PASS
```

The deterministic pilot contains:

```text
maps: 1,000
records: 35,854
MAP records: 4,000
SEGMENT records: 31,854

EMITTED: 11,130
ABSTAINED: 24,682
UNAVAILABLE: 42
INVALID: 0

independently agreeing real-pilot cases: 191
real-pilot directional conflicts: 0
```

The generated artifacts are Git-ignored and located at:

```text
training/datasets/weak_supervision_v01/pilot/
```

Files observed there:

```text
audit.json
evidence.jsonl
leakage.json
manifest.json
registries.json
selection.jsonl
```

Rechecked SHA256 values:

```text
manifest.json
c5d1cc458a12b1919f40f64efa44c620a693031a623f97048ede067b03629469

evidence.jsonl
be5d187af8510315943a686c5d43cc9be46a1b95d57ebaba96fef7816ec46a65

selection.jsonl
5befe4cceff267eb7199367142dbe0f3abbea477fbcf7944dc3d06e3ed917c88
```

Do not regenerate the full 126,509-map Foundation corpus. The existing
1,000-map pilot is the primary source population for this task.

## 5. Non-negotiable task boundary

The requested phase establishes deterministic Active Learning and Human
Annotation infrastructure plus a small dry-run batch. It does not authorize:

- model training of any kind;
- freezing or declaring a final skill taxonomy;
- describing weak evidence or human judgement as ground truth;
- modifying Feature 0.2, Local 0.3, or Reference 0.2 semantics;
- changing canonical segmentation;
- weakening target-leakage enforcement;
- large-scale human data collection;
- player profiling, recommendation, or WuxinBot integration;
- commit, push, deploy, or cleanup of existing worktree changes.

If the implementation appears to require a verified Foundation semantic
change, stop that path and report the exact blocker instead of adapting the
Foundation silently.

## 6. Mandatory first action: classify all 42 UNAVAILABLE records

This investigation was not completed before the pause. It is the first
implementation gate and must happen before candidate selection or batch
generation.

Extract every record from `evidence.jsonl` whose `status` is `UNAVAILABLE`,
including entity identity, scope, checksum, rule/source, diagnostics, and
provenance. Then join each record back to the relevant Feature, Local, or
Reference 5k source/QA row.

The aggregate currently reports:

```text
GEOMETRY_BLOCKED: 33
MISSING_REQUIRED_SIGNAL: 6
REFERENCE_UNAVAILABLE: 3
```

Observed source breakdown:

```text
Local slider-travel SEGMENT evidence:
  GEOMETRY_BLOCKED: 30
  MISSING_REQUIRED_SIGNAL: 3

Observable movement tail:
  MISSING_REQUIRED_SIGNAL: 2

Observable slider control:
  MISSING_REQUIRED_SIGNAL: 1

Reference ppy snap:
  GEOMETRY_BLOCKED: 3
  REFERENCE_UNAVAILABLE: 3
```

Every record must be classified as one of:

```text
legitimate_unavailable
unexpected_unavailable
unresolved
```

In particular, determine whether `MISSING_REQUIRED_SIGNAL` means a legitimate
absence—such as no sliders, a one-object/sparse map, a legitimately absent p95,
or an unavailable corrected Local aggregate—or a real join/aggregation defect.

Required machine-readable outputs should include both per-record evidence and
an aggregate summary, for example:

```text
training/datasets/active_learning_v01/dry_run/
  unavailable_classification.jsonl
  unavailable_summary.json
```

If a real pipeline correctness defect is found, do not suppress it or silently
filter it out. Record the evidence and decide explicitly whether it blocks the
Active Learning phase.

## 7. Provisional propositions available for human questions

Weak Supervision v0.1 currently exposes four deliberately provisional
propositions:

```text
ws01.provisional.movement_demand_high
ws01.provisional.dense_timing_pressure_high
ws01.provisional.slider_control_load_high
ws01.provisional.slider_tracking_travel_high
```

Select only approximately two to four propositions that humans can plausibly
judge pairwise from the deterministic presentation. Initial design assessment:

- `movement_demand_high`: suitable for MAP/MAP or SEGMENT/SEGMENT;
- `dense_timing_pressure_high`: likely suitable for MAP/MAP or
  SEGMENT/SEGMENT if presentation is clear;
- `slider_tracking_travel_high`: suitable for SEGMENT/SEGMENT;
- `slider_control_load_high`: potentially difficult to judge from short
  segments alone and should be included only if presentation evidence supports
  it.

Do not reintroduce old final-looking names such as `jump_aim`, `stream`, or
`tech`. The purpose of human annotation is to test provisional phenomena, not
to ratify an imagined taxonomy.

## 8. Existing annotation surface and recommended version boundary

The tracked legacy module is:

```text
src/osu_skill_profiler/schema/annotation_schema.py
```

It is an old placeholder with hard-coded skill semantics, primarily absolute
labels, old lower-case pairwise values, no first-class `CANNOT_JUDGE`, and no
complete task/batch/provenance/control/presentation contract. It also reduces
annotator reliability to a single opaque field.

Do not silently break its current callers or tests. Prefer a separate,
versioned Active Learning surface such as:

```text
src/osu_skill_profiler/active_learning/__init__.py
src/osu_skill_profiler/active_learning/contracts_v01.py
src/osu_skill_profiler/active_learning/presentation_v01.py
src/osu_skill_profiler/active_learning/selection_v01.py
src/osu_skill_profiler/active_learning/batch_v01.py
src/osu_skill_profiler/active_learning/metrics_v01.py
```

These names are a recommendation, not an instruction to create unnecessary
modules. Keep the smallest coherent versioned boundary.

## 9. Minimum AnnotationTask contract

The v0.1 task schema should mechanically support at least:

```text
task_id
schema_version
task_version
batch_id
proposition key and version
scope
entity_a
entity_b
selection_reason
selection_score_components
total acquisition score
weak-evidence snapshot hash/reference
provenance
control_type
presentation_order
presentation contract/version
```

Only compare compatible scopes:

```text
MAP vs MAP
SEGMENT vs SEGMENT
```

Cross-scope pairing must fail closed. Pair identities, control relationships,
and ordering must serialize deterministically.

## 10. Minimum response and HUMAN-evidence contract

Recommended conservative ordinal answer space:

```text
A_CLEARLY_HIGHER
A_SLIGHTLY_HIGHER
APPROX_EQUAL
B_SLIGHTLY_HIGHER
B_CLEARLY_HIGHER
CANNOT_JUDGE
```

`CANNOT_JUDGE` is not equality. It is a first-class abstention response.

Responses should include at least:

```text
response_id
task_id and task_version
batch_id
pseudonymous annotator_id
session_id
presentation_order
response time, if collected
confidence band, if collected and explicitly non-probabilistic
optional reason codes
provenance
```

Unknown task/annotator identities and accidental duplicate response IDs must
fail closed or be preserved explicitly as invalid records.

Human responses enter a `HUMAN` evidence family with raw responses preserved.
The design must support multiple annotators, repeats, disagreement, abstention,
and provenance. Do not replace raw responses with majority-vote “truth.”

## 11. Canonical segment and presentation contract

Do not implement a second segmentation system. Use the production canonical
segment implementation directly, including `segment_local_signals(...)` and
the existing five-second fixed-window identity:

```text
map checksum
segment index
start_ms / end_ms
start_idx / end_idx
```

The human presentation must be deterministic and blind to weak-rule outputs by
default. It should define and version at least:

```text
playable window: canonical segment
pre-roll: bounded, proposed 1500–2000 ms
post-roll: bounded, proposed 1000–1500 ms
audio: required where available
object visualization: required
map metadata: neutral subset only
mods: unmodded or explicit
neighbor context: required
replay/video: optional; do not assume it exists
```

The exact pre/post values were not fixed before the pause. Inspect what the
available artifacts can present reliably, choose explicit values, and test the
serialized contract. Do not expose weak labels, acquisition scores,
split/challenge flags, or control identity to ordinary annotators.

## 12. Deterministic candidate scoring

Use an interpretable non-model score. Each selected task must carry its
component values and selection reason. Reasonable bounded components derived
from actual pilot evidence include:

```text
uncertainty
independent disagreement
abstention pressure
boundary proximity
low effective independent support
novelty / underrepresentation
challenge or OOD audit bonus
control priority
```

Do not give these components fake probability semantics. The real pilot has
zero directional conflicts, so disagreement will probably be zero in the
real dry run. Do not fabricate disagreements to make the batch look balanced;
synthetic disagreements belong only in adversarial tests.

Candidate categories should include a bounded mixture of:

- easy anchors backed by genuinely independent same-direction evidence;
- boundary/uncertain examples;
- abstention-heavy examples with complete observables;
- challenge, legacy, pathological, or OOD-like audit examples;
- exact-repeat and A/B-inversion controls;
- ambiguous controls;
- within-map different-segment comparisons.

## 13. Pair construction and diversity constraints

Every selected pair must record why it was selected. Suggested default
constraints:

- same provisional proposition;
- same scope;
- no invalid or unresolved-unavailable entity;
- `entity_a != entity_b` unless the relationship is an explicit control;
- anchors may use an obvious difference;
- ordinary informative pairs should avoid useless extreme mismatch;
- bounded ordinary tasks per map, beatmap set, mapper, and broad evidence or
  observable bucket;
- one unordered pair may appear only once unless it is an intentional exact
  repeat or inversion control.

The verified split artifact `training/splits/v02/set_disjoint.jsonl` can supply
`set_group_key` and `mapper_group_key` for sampling and diversity audit only.
Those fields must never become model inputs or annotator hints.

Minimum control types:

```text
NONE
EXACT_REPEAT
AB_INVERSION
EASY_ANCHOR
AMBIGUOUS_CONTROL
WITHIN_MAP_SEGMENT
```

Controls may bypass a normal duplicate restriction only through explicit,
auditable relationships. Accidental duplicates must fail closed.

## 14. Reliability and agreement diagnostics

Do not report a single annotator “accuracy” against weak evidence. At minimum,
implement transparent diagnostics such as:

```text
INTRA_ANNOTATOR_CONSISTENCY
INVERSION_CONSISTENCY
POSITION_BIAS
ANCHOR_AGREEMENT (diagnostic only)
ABSTENTION_RATE
DIRECTIONAL_INTER_ANNOTATOR_AGREEMENT
RESPONSE_DISTRIBUTION
WEIGHTED_ORDINAL_DISAGREEMENT
PAIRWISE_TRANSITIVITY (diagnostic only)
```

`CANNOT_JUDGE` contributes to abstention reporting, is never converted to
`APPROX_EQUAL`, and should be excluded from ordinal-direction denominators
with the excluded count reported.

If Cohen's kappa is implemented, restrict it to matching tasks with exactly
the applicable two-annotator, non-abstain observations and document the
assumptions. Do not add Fleiss/Krippendorff metrics merely for completeness.

## 15. Dry-run target and artifact contract

Generate approximately 100 pairwise tasks and never exceed 200 without a
specific justification. A reasonable starting composition is:

```text
60–75 SEGMENT/SEGMENT
15–25 MAP/MAP
10–20 controls included in the total
```

This is infrastructure validation, not a human collection campaign. It must
not consist only of hard or pathological examples.

Suggested ignored artifact directory:

```text
training/datasets/active_learning_v01/dry_run/
  batch.jsonl
  manifest.json
  diagnostics.json
  unavailable_classification.jsonl
  unavailable_summary.json
  presentation_contract.json
```

Requirements:

- strict JSON/JSONL;
- stable sorting and stable IDs;
- no NaN or Infinity;
- no absolute paths, timestamps, UUIDs, or other run-specific values;
- source artifact hashes and file size/hash manifest;
- repeated generation is byte-identical;
- a concise human-readable report contains no invented human conclusions.

## 16. Required adversarial/oracle tests

Write tests before or alongside implementation for all of the following:

```text
accidental same-pair duplicate rejected
intentional exact-repeat control accepted
A/B inversion control and orientation normalization
all candidate scores equal
insufficient candidates
one map dominates candidate pool
missing weak evidence
CANNOT_JUDGE handling
contradictory human responses preserved
duplicate human response rejected/preserved as invalid
unknown annotator or task identity
deterministic replay
position-bias metric
repeat and inversion consistency
MAP/SEGMENT cross-scope pair rejected
unresolved unavailable excluded
controls bypass only explicit restrictions
weak evidence hidden from blind presentation
split/challenge metadata hidden from presentation
```

Use synthetic records for adversarial behavior and the existing pilot for the
real dry run. Do not alter real pilot evidence to manufacture a test case.

## 17. Recommended continuation order

1. Recheck HEAD, status, staged/unstaged diff, and generated-pilot hashes.
2. Read the task source and current Weak Supervision contracts/reports in full;
   treat this handover as an index rather than an authority over disk.
3. Extract and join all 42 `UNAVAILABLE` records; produce per-record and
   aggregate classifications.
4. Stop and document the issue if the classification finds a correctness bug
   that blocks safe candidate selection.
5. Select only the human-judgeable subset of the four provisional
   propositions.
6. Define the versioned task, response, presentation, control, and HUMAN
   evidence contracts.
7. Add adversarial/oracle tests first.
8. Implement deterministic candidate extraction, component scoring, pairing,
   diversity limits, and controls using real runtime contracts.
9. Implement response validation and conservative reliability/agreement
   metrics without majority-vote ground truth.
10. Run a tiny synthetic batch and deterministic replay before touching the
    real pilot population.
11. Generate the bounded real dry-run batch, regenerate it independently, and
    verify byte identity and strict serialization.
12. Create:

```text
docs/ACTIVE_LEARNING_ANNOTATION_DESIGN_V01.md
docs/HUMAN_ANNOTATION_CONTRACT_V01.md        (only if it reduces duplication)
```

13. Run targeted tests, the full unit suite if reasonably cheap, `compileall`,
    strict artifact parse/finite checks, and `git diff --check`.
14. Report the required verdicts and stop. Do not begin real annotation or
    model training.

## 18. Acceptance and final report

`ACTIVE_LEARNING_ANNOTATION_DESIGN: PASS` is permitted only when:

- all 42 unavailable records are classified or explicitly unresolved;
- task and response schemas are versioned;
- pairwise MAP and SEGMENT judgements are supported;
- `CANNOT_JUDGE` is first-class;
- HUMAN provenance and raw disagreement are preserved;
- duplicate, inversion, anchor, ambiguous, and within-map controls exist;
- scoring is deterministic and interpretable;
- diversity limits are enforced;
- canonical segmentation is reused unchanged;
- the presentation contract supplies sufficient context and is blind by
  default;
- agreement/reliability diagnostics exist with documented abstention rules;
- the bounded dry-run batch exists and reproduces byte-identically;
- required adversarial tests pass;
- Foundation semantics and leakage policy remain unchanged;
- no taxonomy is frozen and no model is trained.

Otherwise report `ACTIVE_LEARNING_ANNOTATION_DESIGN: BLOCKED` with the exact
reason.

The final response must separately decide:

```text
READY_FOR_SMALL_HUMAN_ANNOTATION_PILOT:
YES | YES_WITH_CAVEATS | NO
```

That verdict means only that a small experiment can test whether the questions
and provisional concepts are judgeable. It does not validate the taxonomy,
make human labels ground truth, authorize ML training, or imply that player
profiling is ready.

Final reporting should include:

- Active Learning design status;
- unavailable classification counts and any defect evidence;
- files added/changed;
- tests and strict-serialization checks;
- dry-run size and candidate/control composition;
- diversity totals and concentration maxima;
- deterministic replay hashes;
- known limitations;
- readiness verdict;
- report and artifact paths.

Then stop. Do not automatically proceed into real annotation collection,
taxonomy refinement, model training, representation learning, profiling, or
recommendation.

## 19. Immediate risks for the next agent

- Starting schema/pairing code before classifying the 42 unavailable records
  could hide an upstream correctness defect in the candidate filter.
- Treating `MISSING_REQUIRED_SIGNAL` as automatically legitimate could mask a
  join or aggregate bug.
- Reusing the old annotation schema unmodified would hard-code premature skill
  semantics and omit first-class abstention/control provenance.
- Copying segmentation logic would create identity drift from the verified
  canonical five-second segments.
- Calling acquisition scores confidence or probability would overstate their
  meaning.
- Treating multiple correlated weak rules as independent agreement would
  invalidate anchor selection.
- Fabricating directional disagreement because the real pilot has none would
  corrupt the dry-run evidence.
- Selecting only pathological/high-score cases would make the annotation
  experiment unrepresentative and remove useful controls.
- Converting `CANNOT_JUDGE` to equality or majority-voting disagreement away
  would violate the human-evidence contract.
- Exposing weak labels, split/challenge status, or control identity to normal
  annotators would bias the experiment or leak audit metadata.
- Adding random UUIDs, timestamps, absolute paths, or unordered collections
  would break deterministic replay.
- The old Weak Supervision handover is historical; following its “not started”
  state would duplicate or overwrite completed work.

The safe immediate continuation is the bounded, evidence-backed classification
of the 42 `UNAVAILABLE` records—not Active Learning scoring code.
