# Human Targeted Retest v0.2 — Semantic Lock + Retest Harness (P2B)

**Version: 0.2.1 (launch-blocker fixes applied 2026-08-14).** The 0.2.0 text
below is preserved; §9 records the 0.2.1 amendments (both launch blockers).
Machine-readable package: `docs/HUMAN_TARGETED_RETEST_V02.json`
(`package_version: 0.2.1`); old wording and the demoted probe are preserved
inside the amendment records, never silently dropped. V01 documents remain
untouched.

Date: 2026-08-14 (package); 2026-08-15 (open-call launch)
Repository: `osu-skill-profiler`
Status: **LAUNCHED_OPEN_CALL (2026-08-15).** At package-preparation time no
human had seen the V02 UI; no human data was collected; no LLM was
substituted for humans. The public open-call URL is recorded in §7.

This document revises `docs/archive/HUMAN_TARGETED_RETEST_V01.md` (archived
2026-08-16) by adding the semantic
lock and the retest harness. **V01 documents are preserved unchanged as
historical records**; all changes here are versioned as v0.2 and listed in
`HUMAN_TARGETED_RETEST_V02.json` under `amendments_vs_v01`.

## 1. Slider aggregation semantic lock (the last trap)

The axis split (PATH vs TIME) was not enough: within a segment, "更久/更长"
could still mean max / typical / total / p90 / the most salient slider.
S-T1-CORE-A made the trap concrete:

| S-T1-CORE-A | duration max | duration p90 | duration median | duration total |
|---|---|---|---|---|
| direction | **B** | **B** | **A** | **A** |

So the human construct and its computational proxy were locked **before any
human viewing**:

- **Q-V02-SLIDER-PATH human construct:** upper tail of single-slider follow
  path length inside the segment — "较长的那批滑条", repeats counted as full
  traversal. **Proxy (locked):** `ls.lazy_travel_distance_cs_normalised`
  segment p90 (the unchanged rule input, zero-inclusive rows), with
  `segment_max` as secondary diagnostic.
- **Q-V02-SLIDER-TIME human construct:** upper tail of single-slider follow
  duration — the longer-lasting batch of sliders, full traversal incl.
  spans. **Proxy (locked):** p90 of per-slider `slider_total_duration_ms`
  over sliders starting inside the canonical segment (Local v0.3 values,
  offline-computed; no new feature).

Players are **not** asked to estimate p90/max/median/total — those are
computational proxies of the construct; the frozen wording anchors players to
"较长的那批滑条" in natural language. The construct/proxy distinction and the
anti post-hoc selection clause are recorded in
`HUMAN_TARGETED_RETEST_V02.json` (`semantic_lock`): after human results
exist, **no re-selection of max/median/p90/total is permitted**; disagreements
are attributed through the frozen matrix, never by switching metrics.

## 2. Aggregation-direction matrix (frozen)

> **v0.2.1 note:** the matrix below is the 0.2.0 record (kept as history).
> The 0.2.1 matrix for the re-screened probes is in §9 and in the machine
> package (`aggregation_direction_matrix`).

Computed from Local v0.3 per-slider values (curve path via
`ls.lazy_travel_distance_cs_normalised`, time via `slider_total_duration_ms`),
stream-extracted from the 5k Local QA artifact for the 8 probe sides:

| Probe | TIME max / p90 / med / tot | rule path p90 / seg_max |
|---|---|---|
| S-T1-CORE-A | B / B / A / A | EQUAL / A |
| S-T1-STRESS | B / B / A / B | EQUAL / A |
| S-T2-CORE-A | EQUAL / EQUAL / EQUAL / A | A / A |
| S-T2-CORE-B | EQUAL / EQUAL / A / EQUAL | A / A |

Notes: TIME total is confounded with slider count; slider-row curve medians
include zero-valued lazy rows and are not the human-visible "typical slider";
on S-T1-CORE-A the slider-row curve p90 points B while the zero-inclusive
rule p90 is EQUAL — if humans answer B on the PATH question there, it is
attributed to the slider-row upper-tail reading, per the matrix, not by
re-selecting the metric. This matrix makes every future human/code
disagreement attributable to a specific aggregation.

## 3. Frozen slider question wording

> **v0.2.1 note:** the wording below is the 0.2.0 record (kept as history).
> The current frozen wording (launch-blocker fix, pure-time TIME) is in §9
> and in the machine package (`frozen_questions` / `old_wording_record`).

- **Q-V02-SLIDER-PATH:** 哪一边较长的那批滑条，单根跟随路径更长？
  - 提示：先看每一边片段里路径较长的几根滑条，再比较两边这些滑条各自单根的
    跟随路径长度；折返滑条按来回全程计算。
  - 不是：滑条数量 / 跟随时间长短 / 所有滑条路径相加。
- **Q-V02-SLIDER-TIME:** 哪一边较长的那批滑条，单根需要保持跟随更久？
  - 提示：先看每一边片段里跟随较久的几根滑条，再比较两边这些滑条各自单根的
    持续跟随时间。
  - 不是：路径长短 / 滑条数量 / 整段跟随时间相加。

Answer space (all questions): A 明显更高 / A 略高 / 差不多 / B 略高 /
B 明显更高 / 无法直接比较（原因必选：两边各有侧重 / 差距太小，无法可靠
判断 / 播放或画面看不清 / 问题含义不明确）。`SAME != CANNOT_JUDGE`;
`too_close` is never auto-converted to SAME.

Q-V02-DENSE stays `UNDER_REVISION` (phenomenon-level, no algorithm bound,
no expected ground truth); `isolated-tap share` remains an H3 proxy only —
not complete morphology, not alternation, not press/release.

## 4. Assignment generation (deterministic, persisted)

`tools/retest_v01/retest_package_v01.py` builds
`training/datasets/retest_v01/package/retest_package_v01.json`
(+ SHA-256 manifest) from the locked V02 doc:

- 5 participant slots (`retest_p_01..05`), **12 items each**: 8 slider
  (4 pairs × PATH/TIME), 2 dense (D-D1-CORE, D-D3-CORE), 2 controls.
- Seeded per slot (sha256 of nonce+package+slot); different orders across
  slots; per-item orientation AB/BA recorded.
- Constraints (enforced + tested): same-pair PATH/TIME never adjacent;
  controls ≥ 4 items after their source; `EXACT_REPEAT` keeps the source
  orientation; `AB_INVERSION` physically swaps the sides (flipped
  orientation, not a label change).
- Stress probe is backend-labelled only — nothing is shown to players.
- Clip-safe windows: each slider pair gets one equal-length 8.5 s window
  for both sides; the S-T1-STRESS 74 ms overflow is **fixed at the harness
  level** by extending the pair window end (+100 ms padding) and shifting
  the start — the defect is removed, the probe is NOT demoted.

## 5. UI / storage schema

- UI: `tools/retest_v01/retest_ui_v01.html` — one question per page, six
  answers, CANNOT_JUDGE reason dropdown, identical playback machinery to the
  existing runner (same viewport/scale/rate, audio sync, no numeric overlays,
  no timer). Blinding verified: state payload contains only item_id,
  question_id, frozen question text, attend_to, not_asking, scope tag,
  orientation, side display ids and neutral metadata (BID/CS/AR/objects/BPM);
  **no** probe type, role, expected direction, feature values, hypotheses or
  stress/control labels.
- Runner: `tools/retest_v01/retest_runner_v01.py` — `--launch` is required
  for FORMAL storage; without it every write goes to
  `training/datasets/retest_v01/smoke/TEST_ONLY/…` with a `TEST_ONLY`
  marker. Formal responses are append-only per participant
  (`responses/<participant>/session_001.jsonl`) and are **physically and
  logically isolated from `collection_001`** (new directory, new schema,
  new package id).
- Response record fields: participant_id, assignment_id/version,
  question_definitions_version, package_id, item_id/index/kind, question_id,
  probe_id, control_type, orientation, raw_answer, canonical_answer,
  cannot_judge_reason, latency_ms, response_timestamp_utc, provenance
  (explicit_human_submission + storage marker). Playback telemetry is not
  fabricated (none exists in the player; recorded as unavailable).

## 6. Smoke-test results

Automated (`tests/test_retest_harness_v01.py`, **8/8 PASS**):

1. package/assignment constraints (12 items, spacing, orientation rules,
   unique ids) — PASS
2. clip-safe windows (equal 8.5 s length, no slider clipped on any side) —
   PASS
3. blinding + answer/reason schema — PASS
4. submit validation + canonicalization (BA flip; CANNOT_JUDGE reason
   required; reason rejected with non-CANNOT_JUDGE answers) — PASS
5. persistence append-only + restart/resume — PASS
6. full 12-item synthetic flow + COMPLETE + double-submit rejection +
   formal dir untouched — PASS
7. inversion real side swap (payload A/B actually exchanged) — PASS
8. dense question payload (UNDER_REVISION text, no algorithm binding) — PASS

Live HTTP smoke (server on 127.0.0.1:8790, TEST_ONLY mode): UI HTML 200 with
correct title; `/api/state` returned the frozen TIME wording with no leaked
keys; a `CANNOT_JUDGE + too_close` submission was accepted and stored in the
TEST_ONLY directory with marker; `CANNOT_JUDGE` without reason returned 400;
formal response directory was never created. Server stopped, port verified
closed. All synthetic data carries the `TEST_ONLY` marker and sits outside
the formal tree.

## 7. Launch checklist (all gated on authorisation)

- [x] V02 single-axis definitions + frozen slider wording (this package)
- [x] aggregation semantic lock + direction matrix + anti post-hoc clause
- [x] deterministic assignments (10 planned + 5 reserve × 6 items;
  `retest_package_10x6_v01.json`) persisted with SHA-256
- [x] clip-safe equal-length windows (stress overflow fixed, not tolerated)
- [x] blinded UI (no probe/expected/hypothesis leakage)
- [x] isolated append-only storage (FORMAL gated behind `--launch`)
- [x] automated + live smoke tests green (8/8)
- [x] launch package decision: **10x6 core package** (2026-08-15)
- [x] participant plan decision: **full 10 planned + 5 reserve slots**
  (2026-08-15; reserves open only for dropouts)
- [x] open-call overflow policy (2026-08-15): after P01-P15 are allocated,
  while any allocated participant is incomplete, deterministic P16+ slots are
  generated with `role=open_overflow`; P01-P15 remain the pre-registered main
  analysis, P16+ are reported separately
- [x] public URL method (2026-08-15): **Cloudflare quick tunnel**
  (`trycloudflare.com`; URL changes when the tunnel process restarts)
- [x] **authorisation to launch (2026-08-15, open-call mode)**
- [x] FORMAL server running with `--launch` on 127.0.0.1:8790 and Cloudflare
  quick tunnel live at
  `https://brochure-recording-conferences-yoga.trycloudflare.com/` (URL
  changes if the tunnel process restarts; the first tunnel URL was replaced
  after the audio-endpoint fix)
- [x] P01 disclosure (2026-08-15): `retest_p6_01` is the repository
  operator/author of this retest and is a **known, non-naive participant**.
  Raw responses are append-only and unchanged; analysis must disclose this
  role and may report P01 separately if desired. P01 response timestamps are
  09:57:48–09:59:42Z, i.e. after the per-side-window/Range presentation fix
  (≈09:51Z) and before the repeated-wording UI hint, so P01 saw the corrected
  presentation without the hint.
- [x] Contamination disposition (2026-08-15, user decision "1 B"): P01 kept
  as the operator's formal sample. P04 (`same_human_duplicate_of` P01) has
  its raw responses preserved but is excluded from independent sample
  counts. P02/P03/P06-P08 are `pre_start_withdrawn` (operator mis-clicked
  with zero responses), preserved in `participant_meta`, and may be reissued
  once to different humans; reissues are recorded in `history`. P05 was
  reclassified as `external_participant_partial`: its single response is
  attributed by the operator to a different real visitor and P05 now counts
  as an independent partial participant.

## Working-tree impact

New/modified tool code (allowed this round, analyzer untouched):
`tools/retest_v01/retest_package_v01.py`,
`tools/retest_v01/retest_runner_v01.py`,
`tools/retest_v01/retest_ui_v01.html`,
`tests/test_retest_harness_v01.py`. New docs:
`docs/HUMAN_TARGETED_RETEST_V02.md` + `.json`; amendments (marked P2B) to
`docs/HUMAN_QUESTION_DEFINITIONS_V02.md`/`.json`. V01 documents unchanged.
Ignored working files under `tmp/gap_audit/` and the retest package/responses
under `training/datasets/retest_v01/` (gitignored). Zero commits.

## 9. v0.2.1 amendments (launch-blocker fixes)

### Blocker 1 — three-layer split + construct-level re-screen

- **Three layers, never conflated** (recorded per question in the machine
  package under `semantic_lock.three_layers`):
  - `human_construct` — what the player is asked to compare (upper-tail
    single-slider path / duration);
  - `construct_aligned_measure` — slider-only upper-tail statistic (p90 over
    slider rows only; max secondary);
  - `current_rule_proxy` — for PATH: the zero-inclusive segment p90 the
    current rule consumes; for TIME: none (no rule consumes duration).
- **Type 1 core re-screened at construct level** (3,498 qualifying pairs
  from the existing corpus): the new **S-T1-CORE-A** is
  `sha256:292a289e…` segment 36 vs `sha256:ee40583d…` segment 29 —
  slider-only path p90 105.241 vs 105.227 (rel 0.00014), rule zero-inclusive
  p90 104.867 vs 104.842 (rel 0.00024), path max equal (105.241 vs 105.227,
  no same-direction confound), time upper tail 818.2 vs 372.7 ms (2.20×,
  max and p90 agreeing; track-time p90 782.2 vs 336.7). CS 3.0/3.0, SV 1.0/
  1.0, slider counts 4/5; BPM 220 vs 161 and circles 3 vs 13 are the recorded
  confounders. Time p90s at p50/p85 of the corpus — non-pathological.
- **Old S-T1-CORE-A demoted** to `S-T1-DIAGNOSTIC`
  (role `diagnostic_proxy_mismatch`): its rule p90 is EQUAL but its
  slider-only path upper tail points B in the SAME direction as its time
  tail — it cannot adjudicate H_distance vs H_duration and is excluded from
  all assignments (test-enforced). Preserved for proxy-mismatch analysis
  only.
- **S-T1-STRESS**: kept, but its PATH expectation is now construct-aligned A
  (slider-only p90 104.7 vs 79.4, rel 0.28) while the rule p90 stays EQUAL —
  recorded; still reported separately per G5, never the only Type 1.
- **Type 2 construct re-check: both PASS.** S-T2-CORE-A time p90/max
  1440.0/1440.0 and track-time 1404.0/1404.0; S-T2-CORE-B time p90/max
  666.67/666.67 and track-time 630.67/630.67 — equal on both p90 AND max,
  not a zero/aggregation artifact.

### Blocker 2 — pure-time TIME wording

- Old (withdrawn, preserved in `old_wording_record`):
  "哪一边较长的那批滑条，单根需要保持跟随更久？" — "较长" re-introduces the
  spatial-length reading.
- New frozen wording:
  - **Q-V02-SLIDER-PATH:** 哪一边跟随路径较长的那批滑条，单根的跟随路径更长？
    (提示：先看每一边片段里跟随路径较长的几根滑条，再比较两边这些滑条各自
    单根的路径长度；折返滑条按来回全程计算。不是数量/跟随时间/相加。)
  - **Q-V02-SLIDER-TIME:** 哪一边持续跟随较久的那批滑条，单根需要保持跟随
    更久？(提示：先看每一边片段里各自持续跟随较久的几根滑条，再比较两边
    这些滑条单根的持续跟随时间长短。不是路径/数量/相加。)

### Re-verification after the fixes (all green)

1. semantic schema validation — PASS (V02 JSON + defs JSON parse and
   three-layer keys validated)
2. assignment generation — PASS (5 slots × 12 items; diagnostic probe
   excluded — new test assertion)
3. inversion correctness — PASS
4. blind payload check — PASS
5. clip-safe check — PASS (new pair windows equal-length 8.5 s, no slider
   clipped)
6. full 12-judgement TEST_ONLY flow — PASS (automated + HTTP)
7. manifest/hash consistency — PASS (package manifest SHA-256 recomputed)
8. HTTP smoke — PASS (new PATH wording rendered verbatim; BA canonical
   flip verified; TEST_ONLY marker; server stopped, port closed)
9. No FORMAL response was produced (formal directory never created).

## 10. Post-launch presentation corrections (2026-08-15)

The 10x6 package files and their SHA-256 manifests remain frozen; these are
tool-only harness/UI corrections, recorded here because they affect what
participants see.

1. **Per-side windows.** The frozen `pair_windows` entry is a diagnostic
   record computed from both sides together. For the current probe segments
   that single shared window could put one side's playable segment entirely
   outside the 8.5 s window (e.g. S-T2-CORE-A side B playable 15,575–20,575 ms
   vs window 82,326–90,826 ms), leaving that canvas empty. The runner now
   builds an equal-length 8.5 s, clip-safe window around **each side's own
   canonical segment** (2.0 s before / 1.5 s after, extended only for slider
   tails). Test-enforced for all three probes and both sides.
2. **HTTP Range support.** Audio files are now served with `Accept-Ranges:
   bytes` and 206 Partial Content responses, so browser seeking into the long
   MP3s works and the progress bar / note rendering track the presented
   window.
3. **Player parity with the working annotation UI.** Play now calls
   `ensureStart()` first, pauses the other side, and a `timeupdate` watchdog
   stops playback at the window end.
4. **Volume.** Player volume is set to 0.5 (half of browser default) by
   explicit user request.
5. **Favicon.** An inline empty favicon and a 204 `/favicon.ico` route remove
   the console 404.
6. **Repeated wording clarification.** The UI now shows `第 X / 6 题` and a
   neutral notice that the same question wording appears multiple times with
   different side segments each time and must be judged independently. The
   frozen question wording itself is unchanged.
