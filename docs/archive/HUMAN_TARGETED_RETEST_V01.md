# Human Targeted Retest v0.1 — Discriminative Probe Package (P2A)

Date: 2026-08-14
Repository: `osu-skill-profiler`
Status: **PREPARED_NOT_LAUNCHED.** This package defines the retest; it does not
recruit participants, does not collect answers, and does not start any formal
collection. Launch requires explicit authorisation.

Companion artifacts:
- `docs/HUMAN_QUESTION_DEFINITIONS_V02.md` / `.json` — the single-axis
  question definitions this package uses.
- `docs/HUMAN_TARGETED_RETEST_V01.json` — machine-readable package
  (probes, expected directions, percentiles, confounders, controls,
  preregistered rules).

## 1. What this retest is for

P1 found the pilot's questions blended axes (movement speed+span; slider
distance+duration) and the dense question outran its own feature. P1.5 built
falsifiable structure: 4 counterbalanced slider pairs and a dense
candidate-elimination table. This package converts that into a minimal human
recheck:

- each **slider** pair is judged on **two independent questions** (path
  distance, follow duration) — never one blended question;
- each **dense** pair is judged on the single UNDER_REVISION phenomenon
  question (no algorithm bound);
- **controls** (1 exact repeat, 1 A/B inversion) check per-person stability
  and side bias only;
- every analysis rule is **preregistered before any answer exists**.

No analyzer change, no new feature, no training, no majority-vote truth.

## 2. Question IDs used

| ID | Question | Axis |
|---|---|---|
| Q-V02-SLIDER-PATH | 哪一边的滑条跟随路径更长？ | spatial path distance only |
| Q-V02-SLIDER-TIME | 哪一边需要保持跟随滑条更久？ | follow duration only |
| Q-V02-DENSE | 哪一边更常出现需要连续快速点击的密集段落？ | UNDER_REVISION phenomenon |

Answer space: `A_CLEARLY / A_SLIGHTLY / SAME / B_SLIGHTLY / B_CLEARLY /
CANNOT_JUDGE(reason)`. `SAME ≠ CANNOT_JUDGE`; the `too_close` reason is never
converted into SAME.

## 3. Slider core probes (4)

| Probe | Type | Role | Path p90 | Follow-duration p90 | Expected PATH | Expected TIME |
|---|---|---|---|---|---|---|
| S-T1-CORE-A | Type 1 | core | 110.662 = 110.662 | 321.4 vs 659.3 ms (2.05×) | SAME/null | B |
| S-T1-STRESS | Type 1 | stress | 74.6621 ≈ 74.6625 | 375 vs 2153.8 ms (5.74×) | SAME/null | B |
| S-T2-CORE-A | Type 2 | core | 290.5 vs 60.7 (4.79×) | 1440.0 = 1440.0 ms | A | SAME/null |
| S-T2-CORE-B | Type 2 | core | 282.8 vs 60.3 (4.69×) | 666.7 = 666.7 ms | A | SAME/null |

- **S-T1-CORE-A** is the non-pathological Type 1: both duration p90s sit at
  corpus p35/p75, path p90 at p84, BPM p28/p69. Its p90-duration direction
  (B) opposes its duration-median direction (A) — a bonus test of which
  duration aggregate players use.
- **S-T1-STRESS** is kept, per P1.5, as `STRESS_PROBE`: side B's 2153.8 ms
  slider is a p98.5 duration outlier and the pair is deliberately
  pathological in time. It is never the only Type 1 evidence and its results
  are reported separately (rule G5). It is the sharpest discriminator
  (every distance metric equal or opposite to the 5.74× duration signal).
- **S-T2-CORE-A / B** pin the duration equality exactly (1440/1440 and
  666.7/666.7 ms) while path p90 differs ~4.8×. If humans still answer the
  TIME question directionally on these pairs, H_duration is contradicted; if
  they answer the PATH question directionally, H_distance is supported.

Reserves (only if a core probe fails presentation checks):
- S-RES-1 (Type 1: p90 exactly equal, duration 5.03×; duration side is p97.5
  — upper tail but not the stress outlier);
- S-RES-2 (Type 2: durations equal 652.17/652.17 ms, p90 4.72×).

Full side data (checksums, segment bounds, seg_max, medians, spans, repeats,
raw max-trail, BPM/SV/CS, percentiles, confounders) is in
`docs/HUMAN_TARGETED_RETEST_V01.json`. Population for percentiles: 31,821
slider_tracking segments.

## 4. Dense probes (2 core + 2 reserve, prepare only)

| Probe | Type | What is held | What differs | Predictions |
|---|---|---|---|---|
| D-D1-CORE | D1 | density equal (223.747 vs 223.749/min) | beat-runs 78 vs 36 (2.17×); CS 4.0/4.0; BPM 208/202 | H1→A; H2→SAME |
| D-D3-CORE | D3 | density ≈ (98.7 vs 99.6/min); runs equal (12 vs 12); CS 3.0/3.0 | morphology proxy (isolated-tap share) 0.076 vs 0.801 | H3→B; H1/H2→SAME |
| D-D1-RES | D1 | density equal (209.491 = 209.491) | runs 23 vs 64 (2.78×) | reserve; AR null on side A |
| D-D2-RES | D2 | runs equal (29 vs 29) | density 41.4 vs 447.3/min (10.8×) | reserve; morphology confounded |

- D1 decouples H1 from H2; D3 decouples H3 from both, using the isolated-tap
  share as a structural proxy. H3 is therefore
  `H3_PARTIALLY_STRUCTURALLY_OBSERVABLE` — observable as sequence morphology
  in map data, NOT as player input; alternation and press/release remain
  `UNOBSERVABLE_WITH_CURRENT_DATA`.
- No expected direction is set on Q-V02-DENSE (UNDER_REVISION); the
  hypotheses predictions above are analysis-time comparisons only.
- D-D2-RES is the mirror direction of D1 and stays a reserve.

## 5. Controls

- `CONTROL-R1` — exact repeat of Q-V02-SLIDER-TIME on S-T2-CORE-A (same
  person, never adjacent to the source).
- `CONTROL-I1` — A/B inversion of Q-V02-SLIDER-PATH on S-T1-CORE-A (side
  swap; responses canonicalised before comparison).
- Controls are reported alone: per-person direction stability and side-bias
  rate. Never merged into probe agreement.

## 6. Presentation audit (offline, from renderer code + corpus)

- Both canvases 768×576 with identical 512×384→748×556 mapping; no zoom;
  1.0× playback; per-side audio verified present for **all** 12 slider sides
  and all 8 dense sides; no unsafe BPM/SV anywhere.
- Window-end cuts: **none on core probes** except one slider on
  S-T1-STRESS side B overflowing the window by ~74 ms (minor; stress is
  reported separately anyway). Reserves have 1 cut each (acceptable for
  reserves).
- AR missing ("AR 未提供") on S-T2-CORE-B side A and D-D1-RES side A —
  recorded, not blocking (AR is not a slider-judgement cue).
- Slider duration is perceivable via ball motion + audio, but there is **no
  timer overlay**: if a participant selects `presentation_unclear` on the
  TIME question, the reason is preserved and is never attributed to the
  feature. **Verdict: no PRESENTATION_BLOCKER on core probes.**
- Required UI adaptations before launch (tool code only — analyzer and raw
  data untouched): render V02 question texts, SAME label, CANNOT_JUDGE with
  4 reasons, two independent questions per slider pair, and explicit
  repeat/inversion items.

## 7. Preregistered analysis rules

- **G1** alignment is computed only for the four single-axis V02 questions
  (Q-V02-DENSE excluded). Directional answer matching the mapped observable
  direction = aligned; SAME against a null expectation = aligned; mismatch =
  misaligned; CANNOT_JUDGE never counts either way.
- **G2** null expectations (Type 1 PATH, Type 2 TIME) are their own bucket,
  never errors.
- **G3** SAME / CANNOT_JUDGE / each reason reported separately; `too_close`
  is preserved raw, never auto-converted to SAME.
- **G4** controls reported alone.
- **G5** S-T1-STRESS reported separately; no stress+core mixed agreement.
- **G6** persistent splits on a single-axis question = genuine human
  disagreement / perceptual boundary; no majority truth, no relabelling, no
  participant ranking.

## 8. Expected scale

- 3–5 players; per person: 8 slider judgments (4 pairs × 2 questions) +
  2 dense (D1-CORE, D3-CORE) + 2 controls = **12 judgments**. Total ≤ 60
  human judgments across 5 players — far below any 40-task collection.
- No LLM substitutes for human answers; no new data beyond these items.

## 9. Launch gating

Launch requires: explicit authorisation; the UI adaptations in §6 (tool code
only); a fixed participant-count decision (3–5); no analyzer or feature
changes; no reuse of collection_001 infra (new, separate response storage).

## Working-tree impact

New files: `docs/HUMAN_QUESTION_DEFINITIONS_V02.md`,
`docs/HUMAN_QUESTION_DEFINITIONS_V02.json`,
`docs/HUMAN_TARGETED_RETEST_V01.md`, `docs/HUMAN_TARGETED_RETEST_V01.json`;
ignored `tmp/gap_audit/` additions (`find_dense_probes_v01.py`,
`probe_percentiles_v01.py`, `presentation_check_v01.py` + intermediate
JSON). No analyzer, snapshot, evidence or historical document modified.
