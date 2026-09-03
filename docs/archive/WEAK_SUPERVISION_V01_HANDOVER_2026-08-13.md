# Weak Supervision Infrastructure v0.1 — Handover

Date: 2026-08-13<br>
Repository: `osu-skill-profiler`<br>
Task source: local Codex attachment (not included in the repository)

## 1. Handover status

The Weak Supervision Infrastructure v0.1 task has been paused before
implementation. No weak-supervision production code, pilot artifact, registry,
schema, test, or final task report has been created in this work session.

This document is the only file added by the handover step. The next agent must
treat the current disk state as authoritative and must not infer completion
from the design notes below.

```text
WEAK_SUPERVISION_IMPLEMENTATION_STARTED: NO
FOUNDATION_PROVENANCE_SNAPSHOT_CREATED:  NO
SHA_TRANSCRIPTION_ERRATA_CREATED:        NO
PILOT_SELECTED_OR_RUN:                   NO
TESTS_RUN_IN_HANDOVER_STEP:              NONE
COMMIT_OR_PUSH_PERFORMED:                NO
```

## 2. Current repository checkpoint

Checked immediately before writing this document:

```text
branch: main
HEAD: bc8655c2fa5d3f23807048c921cfd7f1e75bcdb9
staged diff: empty
```

Pre-existing worktree state, before this handover document was added:

```text
 M docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md
?? docs/RED_TEAM_BLOCKER_RECHECK_V02.md
?? tools/performance_probe.py
```

The tracked remediation-report diff is substantial: 216 insertions and 32
deletions at the time of inspection. It records completed 20k/full-corpus,
split, performance, hash, and final remediation evidence. It is not an
incidental formatting change.

The next agent must preserve all of the above. Do not use `reset`, `clean`,
`restore`, checkout-overwrite, or automatic cleanup. Do not stage or commit
these paths unless the user separately authorizes it. This handover document
will itself appear as an additional untracked file.

Observed SHA256 hashes of the dirty/untracked delivery files at handover time:

```text
docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md
601925BC5BF6B3BA302EC65AA1BECDCF7096D0E61EBA116C9EF7CBBD6CEF6BBC

docs/RED_TEAM_BLOCKER_RECHECK_V02.md
421E0191457DB01AC8542EB1478705F2675A4489E75F0D9DCF20AFB8B6544EDC

tools/performance_probe.py
C89DB6889EBC9A23A9D626EDA8AC93F0A7200233D9A3A650AAA1565F6EE0D4E8
```

These hashes are handover diagnostics, not an instruction to reject an
intentional later edit.

## 3. Verified foundation entering this task

The independent blocker recheck reports:

```text
RT-01: FIXED
RT-02: FIXED
RT-03: FIXED
RT-04: FIXED
RT-05: FIXED
BLOCKER_REMEDIATION_VERIFIED: YES
READY_FOR_WEAK_SUPERVISION: YES_WITH_CAVEATS
```

Its recorded verification baseline is:

```text
independent micro-oracle: 28/28 PASS
targeted Feature/Local/Reference/leakage tests: 85/85 PASS
full cheap unit suite: 201/201 PASS
corrected Local golden: 155/155 PASS
corrected Reference golden: 128/128 PASS
```

These are results reported by the completed independent recheck, not tests
freshly rerun during this handover step. Re-establish the appropriate baseline
before implementation.

Current corrected semantic versions observed in source:

```text
Feature:           0.2.0   (legacy 0.1.0)
Local Signal:      0.3.0   (legacy 0.2.0)
Reference Signal:  0.2.0   (legacy 0.1.0)
Leakage policy:    0.1.0
Historical split implementation constant: 0.1.0
Corrected generated split artifacts documented as v0.2
```

Do not silently reinterpret the historical versions. New Weak Supervision
must consume the corrected contracts while preserving historical replay.

## 4. Known provenance erratum that must be handled first

`docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md` contains a 65-character
transcription of the Reference full-corpus SHA256. It has an extra `E` after
`...AAFC`:

```text
originally transcribed (invalid, 65 hex characters):
425B05DD1672305F0BD768E3591AAFCEBA9A08B75F5D844656899C4E1F1A86A19

actual artifact hash (valid, 64 hex characters):
425B05DD1672305F0BD768E3591AAFCBA9A08B75F5D844656899C4E1F1A86A19
```

The next agent must create a small standalone errata/provenance note that
preserves both strings and their relationship. Do not edit historical text to
make the typo disappear. The independent recheck classifies this as a bounded
documentation/provenance caveat, not a semantic blocker.

## 5. Critical existing-code discovery

The repository already contains a primitive, tracked weak-label prototype:

```text
src/osu_skill_profiler/weak_supervision/base.py
src/osu_skill_profiler/weak_supervision/engine.py
src/osu_skill_profiler/weak_supervision/rules.py
src/osu_skill_profiler/weak_supervision/__init__.py
tests/test_weak_supervision.py
```

It currently uses `WeakLabelResult` / `WeakLabelEvidence`, free-form `skill`
strings, numeric `confidence`, three hard-coded demonstration skills/rules,
empty-list abstention, and a taxonomy version. It has no source registry,
proposition registry, explicit lineage DAG, correlation model, first-class
abstention record, or transitive weak-evidence leakage contract.

It is also consumed by
`src/osu_skill_profiler/models/baseline.py`; the baseline emits these records
under `weak_labels`. README and architecture documentation mention this old
surface. Therefore the new task is not safely implemented by blindly deleting
or renaming the prototype. The next agent must first inventory compatibility
and decide on a versioned migration boundary. The requested v0.1 system must
not freeze the old `jump_aim` / `stream` / `rhythm_complexity` examples as the
final taxonomy merely because they already exist.

This is an implementation concern, not permission to change the verified
Feature, Local, Reference, segmentation, or leakage semantics.

## 6. Authoritative reading list

Before semantic design or edits, read these completely:

1. The full task source named at the top of this document, sections 0–26.
2. `docs/INDEPENDENT_RED_TEAM_AUDIT_V01.md`
3. `docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md`
4. `docs/RED_TEAM_BLOCKER_RECHECK_V02.md`
5. `docs/PRE_ML_FOUNDATION_ERRATA_V01.md`
6. Feature v0.1/v0.2 schema, extractor, migration, and contracts.
7. Local Signal v0.2/v0.3 contracts and extractor.
8. Reference Signal v0.1/v0.2 contracts and extractor.
9. Canonical segment contracts and implementations.
10. `src/osu_skill_profiler/dataset/leakage.py`
11. `tests/test_target_leakage.py`
12. `docs/TARGET_LEAKAGE_ENFORCEMENT_V01.md`
13. Dataset split contracts and code relevant to future model inputs.
14. The existing weak-supervision prototype, its tests, and all consumers.

Do not treat remediation claims as proof; use them as an index into source,
contracts, tests, and artifacts.

## 7. Required product boundary

The task is to build the first versioned, executable infrastructure for
representing, validating, combining, auditing, and exporting **weak evidence**,
plus a bounded pilot evidence corpus.

It is explicitly not permission to:

- train a final model;
- freeze a skill taxonomy;
- describe weak evidence as ground truth or probability without calibration;
- implement player profiling, recommendation, tournament analysis, or
  WuxinBot integration;
- ingest community tags or start human annotation;
- enter Active Learning;
- modify ppy Reference semantics or verified Foundation semantics;
- weaken default-deny target leakage;
- run a 126,509-map weak-supervision campaign;
- clean historical artifacts, commit, push, or deploy.

If implementation appears to require a Foundation semantic change, stop that
line of work and record `WEAK_SUPERVISION_INFRASTRUCTURE: BLOCKED` with the
specific dependency.

## 8. Minimum infrastructure contract

The implementation should use the smallest coherent versioned schema that
mechanically supports the following, rather than copying prompt field names
without need.

### Evidence records

- entity identity and scope, at least `MAP` and canonical `SEGMENT`;
- registry-controlled opaque proposition key;
- positive, negative, scalar/ordinal where justified, and future-compatible
  pairwise direction/value representation;
- deterministic bounded strength or documented ordinal confidence semantics;
- first-class abstention and machine-readable reason/status;
- registered source ID/family/version;
- declared dependencies and explicit semantic lineage;
- independence/correlation group;
- provenance, diagnostics, and schema version;
- strict finite, deterministic serialization.

`ABSTAIN`, unavailable, invalid, emitted zero, and absent evidence must remain
distinct states.

### Registries

- versioned proposition registry, with every pilot proposition provisional;
- versioned source registry, unknown source rejected by default;
- active source metadata sufficient to identify family, contract, lineage,
  reference-only status, model-input/target safety, determinism, and
  correlation group;
- schema compatibility for future COMMUNITY, HUMAN, and MODEL_DERIVED sources,
  without ingesting them now.

### Lineage and independence

- direct and transitive ancestry;
- shared-lineage detection;
- unknown-node and cycle rejection;
- no treatment of two rule IDs derived from one root as independent votes;
- deterministic conflict and correlation reporting;
- no naive majority-vote label aggregation.

### Rules

Each deterministic rule declares ID/version, exact input dependencies, source
lineage, output proposition, scope, confidence/strength semantics, abstention
conditions, rationale, discriminator examples, and expected failure modes.
Prefer sparse defensible evidence over coverage.

### Leakage

The existing default-deny gate remains authoritative. Extend its philosophy
without weakening it so future dataset construction can reject direct and
transitive target/input overlap, Reference-derived target plus Reference
input, split/challenge/QA metadata leakage, reference-only ordinary inputs,
and unknown lineage/input nodes.

## 9. Pilot scope and output

Choose only approximately three to five mechanically defensible provisional
hypotheses after inspecting real current fields. At least one active rule must
depend only on observable/local data, and at least one must use
`REFERENCE_PPY` as explicitly reference-only weak evidence. Do not merely
reproduce osu!oracle categories or combine propositions into a final label.

Execution order:

1. synthetic/unit discriminators;
2. tiny real-map smoke;
3. deterministic stratified pilot of roughly 1,000–5,000 maps.

Do not exceed 5,000 without explicit justification. Include ordinary, legacy,
pathological, and Reference-disagreement representation where available.
Split/challenge metadata may select examples but may never become evidence or
model input.

Before materializing the pilot, estimate output volume and classify artifacts
as canonical, regenerable, or temporary. Use stable strict JSON/JSONL or an
already-supported efficient format, with hashes, stable ordering, no
NaN/Infinity, and a human-readable summary. Do not produce verbose redundant
full-corpus JSON.

## 10. Required adversarial coverage

At minimum, mechanically test:

- valid/duplicate/unknown/version-mismatched source registration;
- direct, transitive, and shared lineage;
- unknown lineage node and cycle rejection;
- positive, negative/scalar where supported, abstention, missing dependency,
  and deterministic replay;
- direct, transitive, Reference, split/challenge, and unknown-input leakage;
- valid independent input/target configuration;
- two rule IDs with identical lineage;
- conflicting independent evidence with conflict preserved;
- all rules abstaining;
- missing Local/Reference data;
- geometry-blocked input;
- unknown proposition/source;
- zero-valued evidence versus absent evidence;
- duplicate evidence emission;
- correlated evidence not counted as independent support;
- deterministic strict serialization and round-trip;
- deterministic pilot selection and reproducible output hash.

## 11. Required documentation and verdicts

The task requires:

- `docs/WEAK_SUPERVISION_INFRASTRUCTURE_V01.md`;
- optionally a compact `docs/WEAK_EVIDENCE_CONTRACT_V01.md` if it avoids
  bloating the architecture report;
- a pilot report with selection identity/hash, evidence counts, coverage,
  dependence, conflict, leakage, strict serialization, hashes, and sizes;
- a machine-readable Foundation provenance snapshot;
- the standalone SHA transcription errata/provenance note.

Final acceptance may say
`WEAK_SUPERVISION_INFRASTRUCTURE: PASS` only if registries, explicit lineage,
cycle/transitive checks, mechanical correlation representation, first-class
abstention, documented confidence semantics, default-deny leakage, deterministic
rules/selection/serialization, preserved conflicts, provisional taxonomy, and
unchanged Foundation semantics are all evidenced.

The final report must separately decide:

```text
READY_FOR_ACTIVE_LEARNING_DESIGN: YES | YES_WITH_CAVEATS | NO
```

That verdict is only about readiness to design a future annotation strategy.
It does not validate a taxonomy, final label model, training, player inference,
or recommendation.

## 12. Recommended continuation sequence

1. Re-run `git rev-parse HEAD`, `git status --short`, staged diff, and diff
   stats. Record any drift since this handover.
2. Read the authoritative list completely and build a requirement-to-evidence
   checklist before editing.
3. Re-establish the cheap verified Foundation test baseline; do not recompute
   full-corpus artifacts.
4. Create the compact Foundation provenance snapshot and standalone SHA typo
   errata first.
5. Inventory the legacy weak-label API and baseline consumer. Define a
   versioned compatibility/migration boundary before replacing it.
6. Design the minimal proposition registry, source registry, lineage DAG,
   evidence/abstention schema, deterministic rule interface, leakage bridge,
   and audit structures.
7. Write registry/schema/oracle/adversarial tests before or alongside the
   runtime implementation.
8. Select a tiny pilot rule set from actual verified fields, document every
   dependency and failure mode, and run synthetic discriminators.
9. Run a tiny real-map smoke. Confirm correctness, deterministic replay,
   leakage failure behavior, and storage estimate.
10. Only after those gates pass, run the bounded deterministic pilot and
    produce hashed artifacts and the required report.
11. Run focused and full tests, strict serialization checks, determinism,
    leakage adversarial tests, and a requirement-by-requirement audit.
12. Report files, tests, pilot counts, conflicts, limitations, both required
    verdicts, and stop. Do not commit or continue into Active Learning.

## 13. Immediate risks for the next agent

- Treating the existing hard-coded weak-label prototype as the requested
  infrastructure would freeze exactly the semantics this task says to keep
  provisional.
- Replacing it without checking `DeterministicBaselineProfiler` could break the
  public output schema or existing 201-test baseline.
- Counting multiple thresholds derived from one Local/Reference root as
  independent support would invalidate the core evidence model.
- Calling deterministic strength a probability would overstate calibration.
- Encoding abstention as an empty list alone would lose unavailable/invalid
  coverage accounting.
- Adding weak targets without transitive lineage into the current leakage gate
  would recreate RT-05 under a new name.
- Using split/challenge flags as evidence would create metadata leakage.
- Running the full 126,509-map corpus would violate the bounded-pilot and
  storage requirements.
- Editing the malformed historical SHA in place would destroy the requested
  provenance trail.

The safe next action is repository and contract audit, not immediate rule
authoring.
