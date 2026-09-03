# Human–Code Gap Audit v0.1

Date: 2026-08-14
Repository: `osu-skill-profiler`
Evidence baseline: `snapshot-a33e951ca690cf1904b0d244`
Audit scope: 9 tasks (6 boundary-class + 3 conflict-class), read-only, no training, no commit.

## 1. Purpose

The 64-response pilot collection closed with a documented recommendation to
replay the three direction-conflict tasks and inspect provisional wording.
This audit extends that inspection to the nine tasks where the human–code gap
is most informative:

- 6 **boundary-class** cases: the acquisition system labelled the pair
  `BOUNDARY_ADJACENT` (near-identical code signal, `pair_proximity >= 0.85`)
  and the two human responses on the task agree directionally;
- 3 **conflict-class** cases: the two human responses on the task disagree
  directionally (the collection's audit queue).

The question under audit is not "who is right". Human answers are not ground
truth and code selections are not ground truth. The question is which layer of

```text
question definition -> player understanding -> visible observable
    -> code observable -> selection
```

shifted, for each case, using only evidence that already exists.

## 2. Data sources and evidence scope

| Source | Used for |
|---|---|
| `training/.../collection_001/analysis/snapshot-a33e951ca690cf1904b0d244/` (manifest-verified SHA-256) | human answers, canonical ordinals, response times, confidence, notes |
| `training/datasets/active_learning_v01/human_pilot_v02/pilot_tasks.jsonl` | task definitions, entity pairs, selection reason/score components, expected sign |
| `training/datasets/active_learning_v01/human_pilot_v02/collection.json` + control `source_task_id` links | control-network evidence (exact repeats used as extra judgments) |
| `training/datasets/active_learning_v01/human_pilot_v02/human_propositions.json` + `blind_pilot.jsonl` | exact player-facing wording, attend-to guidance, not-asking clauses, visible metadata |
| `training/datasets/weak_supervision_v01/pilot/evidence.jsonl` | per-entity rule outcomes, strengths, directions, diagnostics (feature values) |
| `src/osu_skill_profiler/weak_supervision/pilot_v01.py` | rule discriminators, thresholds, abstention conditions, failure modes |
| `src/osu_skill_profiler/active_learning/selection_v01.py` + `batch_v01.py` | signal-position aggregation, boundary/selection reason semantics |
| `src/osu_skill_profiler/active_learning/human_presentation_v02.py` + `tools/annotation_ui_v01.html` | presented window (segment ±2.0s/1.5s), canvas renderer, displayed per-side metadata |
| `training/datasets/feature_qa_v02/feature_qa_5k.jsonl` + local `.osu` corpus via `path_abs` | CS/AR/OD, slider inventory and follow durations in the presented window (audit-support stats computed read-only with the project's own parser; not pipeline artifacts) |

For every entity pair, the declared weak-evidence snapshot hash was recomputed
from the pilot evidence rows and matched exactly (18/18). This pins "what the
code saw" to the exact rows used by the acquisition pipeline.

**Visual observation limitation.** No replay, screenshot or render artifact was
persisted by the pilot. The agent cannot watch the canvas player. The "visual"
layer in this audit is therefore reconstructed from: (a) the renderer code
(canvas polyline slider paths, linear span-repeat ball travel, per-side
audio), (b) the exact presented window and object geometry parsed from the
corpus, and (c) the per-side metadata the UI displayed (`BID`, `CS`, `AR`,
`object_count`, `max BPM`). Where a claim depends on live viewing, it is marked
as such and left at LOW confidence instead of being asserted.

## 3. The nine tasks at a glance

| # | Task | Proposition | Class | Human (canonical) | Code implied direction (aggregated signal) | Code margin |
|---|---|---|---|---|---|---|
| B1 | `task-263cea7e…` | dense_timing | boundary | A_clear, A_slight | A | 0.000111 |
| B2 | `task-2ae01c9c…` | dense_timing | boundary | B_slight, B_clear (+repeat: B_slight, B_clear) | EQUAL | 0.0 |
| B3 | `task-bb6f8c7d…` | movement | boundary | A_clear, A_clear (+repeat: B_slight, B_slight) | A | 0.000301 |
| B4 | `task-0680617d…` | slider_tracking | boundary | A_clear, A_slight | B | 0.000001 |
| B5 | `task-14cfa82a…` | slider_tracking | boundary | B_clear, B_clear | B | 0.000012 |
| B6 | `task-f28185e6…` | slider_tracking | boundary | B_clear, B_clear | A | 0.000017 |
| C1 | `task-d4f690cb…` | slider_tracking | conflict | A_clear vs B_clear | EQUAL (both abstained) | 0.0 |
| C2 | `task-55b0b9f0…` | slider_tracking | conflict | EQUAL vs B_slight | EQUAL (both abstained) | 0.0 |
| C3 | `task-b863fbee…` | movement | conflict | A_slight vs B_slight | A | 0.000321 |

`diagnostic_expected_canonical_sign` is `null` for all nine tasks (it exists
only for `EASY_ANCHOR`/`AMBIGUOUS_CONTROL`). Per audit principle, no case below
is treated as a "code direction error": null expected sign is recorded, and the
code's implied direction is reported only as the aggregated signal position.

Canonical ordinals: `A_CLEARLY=+2, A_SLIGHTLY=+1, EQUAL=0, B_SLIGHTLY=-1,
B_CLEARLY=-2`. Response order was randomised per session (`AB`/`BA`); all
answers below are canonicalised.

## 4. Per-case evidence

### B1 — `task-263cea7e561caaa0b8295f42` (dense_timing, BOUNDARY_ADJACENT)

- **Question (verbatim):** "哪一侧更常出现需要连续快速点击的密集段落？"
  guidance: 观察高密度物件是否连续形成快速点击段，而不只看某个孤立瞬间;
  not-asking: 不是比较歌曲 BPM / 不是比较物件总数 / 不是判断串的具体指法.
- **Human:** annotator_002 `A_CLEARLY` (+2, 9,693 ms, no confidence) —
  fast but within 002's personal norm (all five answers 7.6–12.5 s);
  annotator_027 `A_SLIGHTLY` (+1, 92,985 ms). Directionally agreeing A.
- **Code (OBSERVABLE `ws01.observable.dense_timing`):**
  - A: `object_rate_max_1s=11`, `burst_longest_125ms=949` → POSITIVE, strength 0.088444
  - B: `object_rate_max_1s=10`, `burst_longest_125ms=948` → POSITIVE, strength 0.088
  - Strength is `min((rate-9)/7, (burst-750)/2250)`; both sides are capped by the
    nearly identical burst term, so the 11-vs-10 rate delta is invisible in the
    aggregated signal (A 0.772111 vs B 0.772000).
- **Feature delta:** rate A>B by 1 in the peak 1-second window; burst
  identical (949 vs 948 ms); visible metadata A=158 BPM/170 objects vs
  B=95 BPM/302 objects.
- **Visual:** A is a short 39.7 s, 158 BPM map dominated by circles (129
  circles/41 sliders); B is an 80.8 s, 95 BPM slider-heavy map (169/133).
- **Wording check:** "连续快速点击" vs the rule's fixed
  `rate>=9/s AND burst>=750ms` conjunction — the wording is broader than the
  discriminator, but here the raw rate delta actually points the same way as
  humans.
- **Disposition: `GENUINE_BOUNDARY`, MEDIUM.** The pair is genuinely close
  (rate 11 vs 10; burst 949 vs 948); the careful voter said SLIGHTLY and the
  code's raw feature direction matches the human direction. Notes: (a) the
  `min()` strength collapse hides the only differing feature; (b) the
  A_CLEARLY vote came from a uniformly fast responder (audit flag only).

### B2 — `task-2ae01c9c759740362b33f18d` (dense_timing, BOUNDARY_ADJACENT)

- **Question:** same as B1.
- **Human:** annotator_023 `B_SLIGHTLY` (−1, 76,404 ms), annotator_026
  `B_CLEARLY` (−2, 77,639 ms). Exact-repeat control `task-6de2b202…` adds
  annotator_002 `B_SLIGHTLY` (11,314 ms) and annotator_028 `B_CLEARLY`
  (107,373 ms, HIGH). **4/4 judgments: B.**
- **Code:** A and B have **identical** diagnostics: `object_rate_max_1s=3`,
  `burst_longest_125ms=0`, both NEGATIVE strength 0.25. Aggregated signal
  0.1875 vs 0.1875, margin 0.0. The code literally cannot distinguish the pair.
- **Feature delta (what the code does not see):** A = 212.5 BPM, 94 objects,
  40 sliders dominated by very long holds (564 ms typical; 2.3–4.5 s on the
  long sliders), 3 spinners. B = 150 BPM, 174 objects, 102 sliders with
  pervasive 2-span repeats (follow 400–1,600 ms), repeat_count_total 24 vs 5.
- **Visual:** B presents a continuous back-and-forth slider-repeat rhythm at
  150 BPM; A presents sparse single objects with multi-second holds. The UI also
  displays `302 个物件 vs 94 个物件` and BPM, despite not-asking clauses
  "不是比较物件总数 / 不是比较歌曲 BPM".
- **Wording check:** the machine semantics is "sustained runs of successive
  object gaps ≤125 ms" — a 240 BPM 1/4 bar. A player's "连续快速点击" plausibly
  includes slider-repeat structure and slower-but-continuous tapping. One
  participant's optional note on the sibling task
  `task-4319b133…` states exactly this: "B 完全没有连续点击段，A 虽然有高密度段
  但大多是单点而非连续点击段" (dense single-taps are not continuous clicking).
- **Disposition: `MISSING_OBSERVABLE`, HIGH** (primary); secondary
  `WORDING_DRIFT`, MEDIUM. Code has zero differentiating signal while four
  humans agree on direction. **AMENDMENT (P1.5):** slider reversal / repeat
  structure is a salient-difference candidate, but reversal itself is not
  equivalent to extra clicks; the current evidence cannot uniquely identify
  whether players rely on reversal, sustained-input structure, a wider time
  window, tap-run shape or some other observable. Candidate missing
  observables, not uniquely identifiable from data alone: slider
  reversal/repeat structure, general object-frequency/sustained-tap runs
  wider than 125 ms, and the single-tap-vs-stream distinction the participant
  named. No replay/input data exists to establish additional clicks, so the
  term "折返点击压力" (reversal click pressure) is not used as a finding.

### B3 — `task-bb6f8c7d483672b42ff45b9c` (movement_demand, BOUNDARY_ADJACENT)

- **Question (verbatim):** "哪一侧整张谱面的光标移动通常更快、跨度也更大？"
  guidance: 观察需要快速跨越较大间距的移动段落，以及这种段落是否持续出现;
  known ambiguity (in the contract): "速度和跨度可能指向不同侧".
- **Human:** annotator_003 `A_CLEARLY` (+2, 38,112 ms), annotator_010
  `A_CLEARLY` (+2, 54,539 ms, MEDIUM). **Premise correction:** the exact-repeat
  control `task-3b895e97…` (same pair, same order, other people) adds
  annotator_008 `B_SLIGHTLY` (64,731 ms) and annotator_030 `B_SLIGHTLY`
  (17,384 ms). The same pair is therefore a **2–2 directional split** across
  four humans, not a consistent A.
- **Code:** movement_tail: A ABSTAINED (dist_p95 0.609, vel_p95 2.806 — middle
  band, vel < 3.0); B EMITTED POSITIVE strength 0.0927 (dist_p95 0.720,
  vel_p95 3.556). ppy_snap: A POSITIVE 0.359 (p90 2.590), B POSITIVE 0.623
  (p90 3.171). **Every raw feature favours B.** Yet the aggregated
  signal_position is A 0.839812 vs B 0.839511 (A by 0.0003): A's
  abstained-observable + single reference (0.359) outranks B's crushed
  observable strength (0.0927, `min()`-capped by velocity) + reference (0.623).
  This is an aggregation quirk, not a code "decision".
- **Audit-support full-map stats (computed read-only):** median spacing A
  0.3168 vs B 0.3597 (B); median velocity A 1.3195 vs B 1.3030 (A, by 0.017);
  p90 velocity A 2.506 vs B 3.159 (B); max velocity A 3.838 vs B 5.711 (B).
- **Visual:** A = 186 BPM, 883 objects, CS 4.0; B = 180.5 BPM, 1,187 objects,
  CS 3.6. The UI shows both object counts and BPM.
- **Wording check:** the question is an AND-conjunction ("更快、跨度也更大")
  over two axes that the contract itself declares can point different ways.
- **Disposition: `MULTI_AXIS_TRADEOFF`, LOW.** Humans split 2–2 across
  source+repeat with opposite confidence words; median velocity and p95
  spacing pull opposite ways; the AND-wording forces one answer. No
  single observable explains both sides, and no persisted visual artifact
  exists to adjudicate. Requires live replay before stronger claims.

### B4 — `task-0680617df571e66f6face2da` (slider_tracking, BOUNDARY_ADJACENT)

- **Question (verbatim):** "哪一侧片段中较长的一批滑条，通常需要更远的持续跟随？"
  (scope tag: 这小段). Machine semantics: canonical 5 s segment p90 of
  corrected CS-normalised lazy slider follow distance.
- **Human:** annotator_010 `B_CLEARLY` (presented BA → canonical +2 = A,
  21,343 ms, MEDIUM), annotator_022 `B_SLIGHTLY` (presented BA → canonical +1
  = A, 23,922 ms). **Canonical A, agreeing.**
- **Code (LOCAL `ws01.local.slider_travel_segment`):** p90 A 108.767 vs B
  108.768 — equal to 0.001; strength 0.035 each; margin 1e-6. `segment_max`
  (available in provenance but not consumed by the rule): A 188.4 vs B 114.2.
- **Feature delta:** presented window A (246.05–254.55 s): 16 sliders —
  alternating 234/117 px paths, two tiny 4-span repeats (30/42 px), follows
  171–343 ms; B (53.21–61.71 s): 24 sliders — alternating 172.5/86.25 px
  paths, follows 133–266 ms. Long-slider batch: A's 234 px sliders are
  followed 342.9 ms vs B's 172.5 px at 265.5 ms. A also carries the larger
  single-path travel (max 188.4 vs 114.2).
- **Wording check:** "更远的持续跟随" blends distance ("远") and duration
  ("持续"). Humans' side (A) is simultaneously the longer-path AND the
  longer-duration side here, so the two readings coincide; the rule's own
  failure mode ("segment p90 can hide one extreme slider") is exactly the
  observable it discards (`segment_max`).
- **Disposition: `MISSING_OBSERVABLE`, MEDIUM** (primary); secondary
  `WORDING_DRIFT`, MEDIUM. The rule consumes only p90 path distance; upper-tail
  travel, follow duration and repeat structure are all present in the pipeline
  but unused, and the human direction follows the upper tail / duration side.

### B5 — `task-14cfa82a9bcb6409aba93ad8` (slider_tracking, BOUNDARY_ADJACENT)

- **Human:** annotator_003 `B_CLEARLY` (−2, 354,523 ms), annotator_028
  `B_CLEARLY` (−2, 44,293 ms, HIGH). Canonical B, agreeing.
- **Code:** p90 A 116.598 vs B 116.610 — equal; margin 1.2e-5.
  `segment_max`: A 348.0 vs B 224.9 (A larger — humans did NOT follow max).
- **Feature delta:** window A (128.57–137.07 s): 12 sliders (70–210 px, one
  2-span), follows 84–674 ms, 29 circles — a busy 178 BPM section; window B
  (48.95–57.45 s): only 4 sliders (210/140/140/280 px), follows 353–706 ms,
  10 circles — a sparse 85 BPM section. **Same-length comparison:** a 210 px
  slider is followed 252.8 ms on A (178 BPM) but 529.4 ms on B (85 BPM);
  B's 280 px slider follows 705.9 ms.
- **Wording check:** same distance/duration blend as B4. Here the two readings
  point in opposite directions (distance/max → A, follow duration → B) and
  both humans chose B — the duration side.
- **Disposition: `MISSING_OBSERVABLE`, MEDIUM** (primary); secondary
  `WORDING_DRIFT`, MEDIUM. The human direction is consistent with per-slider
  follow duration (2.1× on B for equal pixel length) and inconsistent with
  the distance/max reading the machine implements.

### B6 — `task-f28185e673a934a4c8d11fb9` (slider_tracking, BOUNDARY_ADJACENT)

- **Human:** annotator_026 `B_CLEARLY` (−2, 35,622 ms), annotator_027
  `B_CLEARLY` (−2, 218,138 ms). Canonical B, agreeing.
- **Code:** p90 A 116.820 vs B 116.803 — equal; aggregated direction A by
  1.7e-5 (opposite to humans). `segment_max`: A 118.6 vs B 183.8.
- **Feature delta:** window A (294.85–303.35 s): 12 sliders (173.3 px
  typical, follows 148–444 ms) at 135 BPM; window B (43.02–51.52 s): 8
  sliders (57.6×2-span, 288, 172.8 px; follows 200–1,000 ms) at 150 BPM.
  Same-length comparison: 173.3 px follows 296.3 ms on A vs 172.8 px follows
  600 ms on B (2×); B's 288 px sliders follow 1,000 ms.
- **Wording check:** same as B4/B5; duration reading explains B again (and
  B also holds the larger max here, so distance-max reading coincides).
- **Disposition: `MISSING_OBSERVABLE`, MEDIUM** (primary); secondary
  `WORDING_DRIFT`, MEDIUM.

### C1 — `task-d4f690cb01133542a5b3a3bf` (slider_tracking, CHALLENGE_AUDIT legacy+pathological)

- **Human:** annotator_011 `B_CLEARLY` (−2, 49,864 ms) vs annotator_030
  `A_CLEARLY` (+2, **6,729 ms** — the fastest response in 030's whole
  session, median 22.7 s). Maximum directional conflict.
- **Code:** both sides ABSTAINED (p90 29.7 / 44.9 < 100; segment_max ≠ 0).
  No code direction — null ≠ error. Raw p90 nonetheless favours B (44.9 vs
  29.7), as does window travel (1,450 px vs 700 px).
- **Feature delta:** A = 114 BPM legacy 2006 map (CS 5.0, **AR 未提供** shown
  in UI), window 31.5–40.0 s: 4 sliders, 210 px single-spans followed
  786.5 ms + two 70 px 2-span repeats (524.3 ms); B = 202 BPM modern marathon,
  window 964.7–973.2 s: 10 sliders, 240 px followed 346.8 ms, 13 circles +
  spinner. Distance axis → B; follow-duration axis → A (2.3× on equal-length
  sliders).
- **Wording check:** same distance/duration blend; the two CLEARLY votes sit
  exactly on the two different readings.
- **Disposition: `MULTI_AXIS_TRADEOFF`, MEDIUM** (primary); secondary
  `POSSIBLE_RUSHED_RESPONSE`, LOW (030's 6.7 s, personal outlier — audit flag
  only, answer retained). Notes: legacy-format + pathological challenge flags
  and the missing AR display mean presentation degradation cannot be excluded;
  no persisted visual artifact to verify.

### C2 — `task-55b0b9f0e001269a94698d85` (slider_tracking, CHALLENGE_AUDIT legacy)

- **Human:** annotator_006 `APPROX_EQUAL` (0, 11,108 ms — typical pace for
  006, whose median is 12.2 s) vs annotator_026 `B_SLIGHTLY` (−1, 30,750 ms).
  Ordinal distance 1 — the mildest of the three conflicts.
- **Code:** both sides ABSTAINED. Raw p90: B 80.8 vs A 7.1 (11×). Window:
  A (110.92–119.42 s) has 5 small sliders (70–140 px, one 2-span and one
  3-span; follows 166–663 ms); B (112.11–120.61 s) has 3 sliders including a
  420 px 2-span followed **2,499.6 ms**.
- **Wording/judgeability check:** the proposition's own abstention guidance is
  "有效滑条太少而无法判断'通常'" — A's window is close to slider-empty (p90
  7.1). `CANNOT_JUDGE` was selected 0/64 in the whole pilot; the EQUAL vote on
  a pair whose domain is nearly empty on one side is consistent with the
  forced-comparison middle-button behaviour the final analysis already
  suspected.
- **Disposition: `PRESENTATION_DEFECT`, MEDIUM.** A near-empty slider domain
  on one side plus an unused abstention affordance undermines reliable
  comparison, independent of the code (which correctly abstained).

### C3 — `task-b863fbee3a4211e4b959054d` (movement_demand, ABSTENTION_HEAVY)

- **Human:** annotator_023 `B_SLIGHTLY` (presented BA → canonical +1 = A,
  94,169 ms) vs annotator_026 `A_SLIGHTLY` (presented BA → canonical −1 = B,
  88,685 ms). One careful voter per side, ~90 s each.
- **Code:** movement_tail ABSTAINED on both (A: dist 0.568, vel 2.364;
  B: dist 0.592, vel 2.255 — middle band: distance ≥ 0.45 but velocity < 3.0).
  ppy_snap essentially equal: A 2.393 vs B 2.391. Aggregated signal A by
  0.0003. The rule deliberately abstains exactly in the region the humans
  argued about.
- **Feature delta:** machine p95 spacing B > A (0.592 vs 0.568); audit-support
  medians/p90 velocity and spacing favour A (median spacing 0.277 vs 0.223;
  median velocity 1.138 vs 1.069); max velocity favours B (3.917 vs 3.235).
  The velocity axis and the span axis genuinely point at different sides.
- **Wording check:** the AND-wording ("更快、跨度也更大") forces one answer
  across the two axes; the contract's known ambiguity "速度和跨度可能指向不同侧"
  is empirically confirmed here.
- **Disposition: `MULTI_AXIS_TRADEOFF`, HIGH.** Each human picked the side
  favoured by one axis; both chose SLIGHTLY after ~90 s — a genuinely hard
  pair, not a defect on either side.

## 5. Cross-case patterns

1. **"Code thinks close" is by construction.** All six boundary pairs have
   aggregated margins ≤ 0.0003; the selection ranked them BOUNDARY_ADJACENT
   precisely because their signals nearly coincide. The audit question is
   therefore: when the code sees nothing, what do humans see?
2. **Dense: when the code sees nothing, humans still agree (B2).** Four
   judgments, all B, on a pair with byte-identical code diagnostics. The
   code's two dense features (1 s peak rate, ≤125 ms burst) are far too
   narrow for what players mean by "连续快速点击".
3. **Slider: follow DURATION is the strongest candidate explanation — correlation, not causal identification.**
   In B4/B5/B6 (and C1's A vote), the side whose long sliders are followed
   longer also wins the human vote; equal-pixel sliders take ~2× longer to follow
   on the winning side (B5 529 vs 253 ms; B6 600 vs 296 ms). **AMENDMENT (P1.5):**
   this is correlational evidence only; within these three pairs distance and
   duration do not vary independently, so the data cannot uniquely separate
   which observable the players actually used. The rule consumes
   only CS-normalised path-distance p90. Follow duration exists in the
   normalized layer (`slider_total_duration_ms`) but is not an input.
4. **Movement: velocity-vs-span tension reproduces the contract's own
   ambiguity.** Both movement cases with human conflict (B3, C3) sit exactly
   on this axis split, and the AND-wording ("更快、跨度也更大") forces a single
   answer.
5. **Presentation metadata contradicts not-asking clauses.** Every panel
   displays object count and max BPM while the dense question explicitly says
   不是比较物件总数 / 不是比较歌曲 BPM — the strongest anchor candidate for B2.
6. **Abstention affordance unused.** `CANNOT_JUDGE` 0/64; the EQUAL vote in C2
   looks like the middle-button substitute for "cannot judge" on a nearly
   slider-empty side.
7. **Rush flags are audit flags only.** B1's A_CLEARLY (9.7 s, fast responder's
   norm) and C1's A_CLEARLY (6.7 s, personal outlier) are marked, not
   invalidated.

## 6. Classification summary

**Code missing observables (`MISSING_OBSERVABLE` as primary): 4 cases**
- B2 (dense): no differentiating signal at all — slider reversal/repeat
  structure, sustained-tap runs wider than 125 ms, and the
  single-tap-vs-stream distinction are absent as code inputs (reversal is a
  structural candidate only; reversal ≠ extra clicks).
- B4/B5/B6 (slider): rule uses only path-distance p90; follow duration,
  `segment_max` upper tail and batch/repeat composition are unused despite
  being present in the pipeline. Follow duration is the strongest candidate
  explanation, **correlational only**: in these three pairs distance and
  duration did not vary independently, so which observable the players used
  is not uniquely identified.

**Problem-definition / wording issues:** the movement AND-conjunction
("更快、跨度也更大") on two provably divergent axes (B3, C3, contract's own
known ambiguity); the slider question's distance/duration blend "更远的持续跟随"
(B4/B5/B6 secondary, C1); the dense question's "连续快速点击" vs the machine's
125 ms window (B2 secondary, corroborated by the participant note on
`task-4319b133…`).

**Presentation issues (`PRESENTATION_DEFECT` primary: 1 case):** C2's
nearly-empty slider domain on one side + unused CANNOT_JUDGE; supporting
factors elsewhere: visible object/BPM metadata contradicting not-asking
clauses (B2), legacy AR 未提供 (C1).

**Genuine boundary (`GENUINE_BOUNDARY` primary: 1 case):** B1 — the only case
where code raw features, code aggregation direction and human direction all
line up on a genuinely tiny difference.

**Multi-axis tradeoffs (`MULTI_AXIS_TRADEOFF` primary: 3 cases):** B3, C1, C3.

**Still undetermined (LOW confidence):** B3's mechanism (2–2 human split, no
visual artifact, code aggregation quirks on both sides); the exact per-pair
human-used slider observable — **AMENDMENT (P1.5):** follow duration remains
the strongest candidate but is correlational, not causally identified; the
three pairs do not separate distance from duration; any
presentation-degradation claim for the legacy pairs (C1/C2).

## 7. P2/P3 recommendations (recorded, not implemented)

- **P2 (evidence):** obtain a third judgment per conflict task via the existing
  review pages; require confidence and add per-task note prompts; persist
  screenshot/video capture of both sides so future audits have real visual
  evidence; run a counterbalanced probe of the follow-duration hypothesis
  (equal path p90, crossed follow durations).
- **P3 (design):** separate the movement question into speed and span
  sub-questions or explicitly instruct "先看速度再看跨度，哪个轴差异更大选哪个";
  for slider, either reword to pure distance ("更远的跟随路径") or add
  follow-duration to the rule inputs; for dense, widen the burst window and/or
  add slider repeat/reversal structure as an input (as a structural cue, not
  a click count), and validate the construct against the
  participant-reported single-tap-vs-stream distinction; consider hiding or
  neutralising object-count/BPM metadata for not-asking-controlled questions;
  require CANNOT_JUDGE before EQUAL when one side's domain is nearly empty.

## 8. Working-tree impact of this audit

Read-only analysis. New files: this report,
`docs/HUMAN_CODE_GAP_DISPOSITION_V01.json`,
`docs/archive/HUMAN_CODE_GAP_AUDIT_V01_HANDOVER_2026-08-14.md` (archived
2026-08-16), and the ignored
`tmp/gap_audit/` working directory (extraction scripts + intermediate JSON).
No snapshot, evidence, pipeline or historical document was modified.
