# Skill Profiler Small-N Human Validation Protocol v0.1

Status: **DESIGN ONLY — no human labels fabricated, no final model training.**

This protocol is part of `SKILL_PROFILER_LABEL_EFFICIENCY_AUDIT_V01`.
It plans human validation for the provisional slider constructs:

- **PATH:** upper-tail single-slider follow path length, repeats counted as
  full traversal. Primary observable: slider-only
  `ls.lazy_travel_distance_cs_normalised` **p90**; secondary **max**.
- **TIME:** upper-tail single-slider follow duration, repeats counted as full
  traversal. Primary observable: slider-only
  `ls.slider_total_duration_ms` **p90**; secondary **max**; cross-check
  `ls.lazy_travel_time_ms`.

All thresholds below are pre-declared defaults. Any deviation must be recorded
before unblinding.

---

## 1. Non-negotiable rules

1. No AI judgment counts as a human participant.
2. Repeated sessions from one person never count as multiple participants.
3. N=1 / small-N evidence supports within-person reliability and construct
   introspection only; it does **not** establish population validity.
4. Target metrics must never appear in participant-facing trials.
5. Pair identity is hidden (`anonymous trial id`); unblinding lives in a
   separate manifest that participants cannot see.
6. Raw answers are append-only. No answer is relabelled.
7. No final model training is triggered by reaching a stopping rule.

---

## 2. Experimenter-contamination protections

Because the N=1 participant may also be the project author:

- All stimuli use anonymous pair ids (`pair-xxxxxxxx`).
- Target feature values, probe class (P1/P2/…), expected direction, and
  FORMAL-vs-candidate status are **not** exposed in the labeling UI.
- Side orientation is pseudo-random and recorded per trial.
- Trial order is pseudo-random per session and per participant.
- Metrics and unblinding metadata are stored only in the unblinding manifest.
- The analysis script and pairing manifest are frozen by SHA-256 before the
  first judgment; the audit report records those hashes.
- Repeated sessions are separated by at least 24 hours where practical.
- A delayed-unblinding field records the earliest permitted unblinding time.

---

## 3. Stimulus pools

1. **FORMAL core:** S-T1-CORE-A, S-T2-CORE-A, S-T2-CORE-B; each asked
   once as PATH and once as TIME (6 formal judgments). Formal status is not
   changed by this protocol.
2. **Candidate pool:** ranked P1–P10 pairs from
   `docs/SKILL_PROFILER_HIGH_INFORMATION_PAIRS_V01.json`. Stress/diagnostic/
   dense/repeat/inversion candidates are **not** silently promoted to FORMAL;
   they are explicitly labelled candidate classes.
3. Selection rule: first take FORMAL pairs; then sample deterministically from
   TOP queues, balancing P1/P2/P3/P4 and reserving P5–P10 for diagnostics.

---

## 4. N=1 protocol (author-as-participant)

| Field | Value |
|---|---|
| Participants | 1 (disclosed author, non-naive) |
| Unique pairs | 24 (12 P1, 12 P2) + 3 FORMAL = 27 |
| Questions per pair | 2 (PATH and TIME), unless a pair is class P1/P2 where only its primary construct is asked; for construct separation use 2 |
| Unique-pair judgments | 54 |
| Hidden repeats | 6 pairs repeated once each (12 judgments) |
| AB-inversion controls | 4 judgments |
| Sanity controls | 2 large-effect pairs (P6) |
| Total judgments | 72 |
| Sessions | 4 sessions of 18 judgments |
| Time burden | ≈ 18 × (30 s playback + 15 s answer) ≈ 14 min/session; ≈ 1 h total |
| Stopping | ≥ 3/4 repeat sessions directionally consistent on 5/6 repeats; otherwise add one session (max 2 extra) and report |
| Defensible | within-person repeat reliability, author construct introspection, UI bugs, wording clarity |
| Not defensible | population generalization, between-person agreement, calibration to other players |

The author must be blinded to metric values and expected direction even in
N=1. If the author knows the hypotheses (they do), the protocol reports the
author as a **non-naive, disclosed** participant and never claims otherwise.

---

## 5. N=3 protocol

| Field | Value |
|---|---|
| Participants | 3 different people |
| Unique pairs | 30 (P1/P2 balanced + 3 FORMAL) |
| Questions per pair | 2 |
| Unique-pair judgments | 60 per participant |
| Hidden repeats | 8 pairs repeated (16 judgments/participant) |
| Inversions | 8 judgments/participant |
| Controls | 4 judgments/participant |
| Total per participant | 88 |
| Total judgments | 264 |
| Sessions | 4 sessions of 22 |
| Time burden | ≈ 1.5 h/person |
| Stopping | directional pair agreement ≥ 0.80 on double-covered pairs for the primary construct; repeat consistency ≥ 0.75; otherwise extend one session per person (max 2) |
| Defensible | within-person reliability, coarse between-person agreement, construct-direction evidence |
| Not defensible | population generalization; agreement may reflect shared interface/culture |

---

## 6. N=5 protocol

| Field | Value |
|---|---|
| Participants | 5 different people |
| Unique pairs | 40 |
| Questions per pair | 2 |
| Unique-pair judgments | 80/participant |
| Hidden repeats | 10 pairs (20 judgments) |
| Inversions | 10 judgments |
| Controls | 4 judgments |
| Total per participant | 114 |
| Total judgments | 570 |
| Sessions | 5 sessions of 23 |
| Time burden | ≈ 2 h/person |
| Stopping | between-person directional agreement on ≥ 20 double-covered pairs; repeat consistency ≥ 0.75; inversion bias rate ≤ 0.15 |
| Defensible | stable construct direction, threshold rough location, agreement heterogeneity |
| Not defensible | population-representative calibration |

---

## 7. N=10 protocol

| Field | Value |
|---|---|
| Participants | 10 different people |
| Unique pairs | 50 |
| Questions per pair | 2 |
| Unique-pair judgments | 100/participant |
| Hidden repeats | 12 pairs (24 judgments) |
| Inversions | 12 judgments |
| Controls | 4 judgments |
| Total per participant | 140 |
| Total judgments | 1,400 |
| Sessions | 6 sessions of 24 |
| Time burden | ≈ 2.5–3 h/person |
| Stopping | directional agreement ≥ 0.80; weighted ordinal disagreement stable; calibration model parameter SE below pre-declared target |
| Defensible | threshold calibration, simple pairwise models, between-person variance, first limited generalization statement |
| Not defensible | full osu! player population claim |

---

## 8. Participant vs judgment efficiency

The three quantities are reported separately: **participant N**, **unique
stimulus N**, **total judgment N**. Repeated judgments from one participant
never become pseudo-participants.

| Design | Participant N | Unique pairs | Total judgments | Can estimate |
|---|---|---|---|---|
| 1 × 300 | 1 | up to 150 | 300 | within-person reliability, author calibration |
| 3 × 150 | 3 | 75 | 450 | + between-person agreement |
| 5 × 100 | 5 | 50 | 500 | + threshold calibration |
| 10 × 50 | 10 | 50 | 500 | + agreement heterogeneity |
| 20 × 25 | 20 | 25 | 500 | broader agreement, weak generalization |

Interpretation rule: **participant N controls the population claim;
unique-stimulus N controls construct coverage; total judgments control
measurement precision within those limits.**

---

## 9. Pre-declared sequential stopping rules

Admissible quantities only: repeat consistency, pair-level agreement,
construct-direction agreement, calibration stability, and (secondary) held-out
weak-label performance. The rule “collect until it looks good” is forbidden.

- **N=1:** stop after 4 sessions if ≥ 5/6 hidden repeats are directionally
  consistent and no inversion bias; otherwise run at most 2 extra sessions and
  report the failure mode.
- **N=3+:** stop when each primary construct has ≥ 20 double-covered pairs and
  directional agreement ≥ 0.80, or after the pre-registered maximum.
- **N=5+:** add calibration-stability gate: parameter estimates from adjacent
  judgment blocks must not shift beyond their pre-registered band.
- **N=10+:** add held-out weak-label agreement as secondary evidence only; it
  never overrides human evidence and never validates a rule against itself.

---

## 10. Human-label manifest schema (Phase Q)

Participant-facing manifest (no answers, no metrics):

```json
{
  "trial_id": "trial-anonymous",
  "construct": "PATH | TIME",
  "stimulus_refs": {"left": "anonymous", "right": "anonymous"},
  "orientation": "LR | RL",
  "answer_schema": ["LEFT", "RIGHT", "NO_CLEAR_DIFFERENCE"],
  "confidence_schema": [1, 2, 3],
  "participant_id": "pseudonym",
  "session_id": "session-001",
  "hidden_repeat_id": "nullable",
  "control_flag": false
}
```

Unblinding manifest (stored separately, never participant-facing) additionally
contains pair id, map checksums, segment bounds, class, expected sign (nullable),
all metric values, and the frozen-manifest SHA-256.

The offline labeling CLI/UI, when generated, consumes only the participant-
facing manifest and appends responses. It contains no answers.

---

## 11. Bootstrap and uncertainty rules (Phase K)

Bootstrap may be applied to **map/pair distributions and feature stability**.
It must never be applied to one participant to fabricate population N.

---

## 12. Model complexity budget (summary)

| Human judgments | Maximum sensible model |
|---|---|
| 100 | hand-tuned rules or Bradley-Terry with strong priors |
| 300 | linear/logistic/ordinal or simple Bradley-Terry |
| 500 | sparse linear + shallow tree diagnostic |
| 1,000 | shallow GBDT with tight regularization |
| 2,000 | small GBDT / splines |
| 5,000 | modest GBDT; neural nets remain unjustified for this construct set |

Any simulation models used in this audit are disposable and marked
non-production.
