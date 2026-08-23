# Human Question Definitions v0.2

Date: 2026-08-14
Repository: `osu-skill-profiler`
Status: **DEFINITION ONLY — no analyzer change, no feature addition, no live
collection.** Replaces the three provisional pilot questions for future
human judging. The v0.1 provisional propositions
(`dense_timing_pressure_high`, `movement_demand_high`,
`slider_tracking_travel_high`) and the collection_001 results are preserved
unchanged as historical evidence.

## Design rules

1. One question = one observable. No AND-conjunctions, no blended
   distance/duration, no "faster AND larger span".
2. Spatial distance and temporal urgency are separate questions.
3. Slider path distance and slider follow duration are separate questions.
4. Dense timing pressure is `UNDER_REVISION`: P1.5 falsified every fixed
   millisecond window tested, so this dimension defines the PLAYER-FACING
   PHENOMENON only and is not bound to any algorithm.
5. `SAME` (差不多) is not `CANNOT_JUDGE` (无法直接比较). `CANNOT_JUDGE`
   requires a reason. A "差距太小" reason is preserved as the participant's
   original choice and is never auto-converted to SAME.

## Answer space (all questions)

```text
A_CLEARLY_HIGHER | A_SLIGHTLY_HIGHER | SAME | B_SLIGHTLY_HIGHER |
B_CLEARLY_HIGHER | CANNOT_JUDGE
```

`CANNOT_JUDGE` reasons (exactly one required):

| reason_id | label | meaning |
|---|---|---|
| `multi_axis_tradeoff` | 两边各有侧重 | the two sides win on different axes and no single axis decision is possible |
| `too_close` | 差距太小，无法可靠判断 | a genuine perceptual boundary, NOT a SAME vote |
| `presentation_unclear` | 播放/画面看不清 | playback/rendering prevented reliable comparison |
| `wording_unclear` | 问题含义不明确 | the question itself was unclear |

## Question dimensions

### Q-V02-SPAN — 光标移动跨度 (cursor movement span)

- **Question:** 哪一边需要完成更大的光标移动跨度？
- **Target observable:** spatial movement span / jump distance in the given
  scope. Distance only.
- **Attend to:** 观察光标跳跃和移动的空间距离，不评估快慢。
- **Not asking:** 不是比较移动速度；不是比较时间紧迫度；不是比较综合难度；
  不是只找全图最远的一跳。
- **Scope:** MAP_PAIR (整张图). Wording is scope-neutral; a segment variant
  may reuse the same dimension with a segment tag.
- **Analysis mapping (provisional, documented for alignment only — not a new
  feature):** `spatial.distance_norm_p95` (map-level p95 normalised spacing).
  `expected_sign == null` is allowed and reported separately.

### Q-V02-URGENCY — 光标移动紧迫度 (movement temporal urgency / velocity)

- **Question:** 哪一边需要以更快的速度完成光标移动？
- **Target observable:** how quickly similar spatial movement must be
  completed (temporal urgency / movement velocity). Time only.
- **Attend to:** 观察移动完成得快慢、时间上是否更赶；不考虑跳得多远。
- **Not asking:** 不是比较跳跃距离大小；不是比较综合难度。
- **Scope:** MAP_PAIR (整张图).
- **Analysis mapping (provisional):** `spatial.velocity_norm_per_s_p95`
  (map-level p95 normalised velocity). `expected_sign == null` allowed.

### Q-V02-SLIDER-PATH — 滑条跟随路径距离 (slider follow path distance)

**AMENDMENT (P2B / v0.2.1) — wording and aggregation semantics frozen before
any human viewing.**

- **Question (frozen, v0.2.1):** 哪一边跟随路径较长的那批滑条，单根的跟随
  路径更长？
- **Attend to (frozen, v0.2.1):** 先看每一边片段里跟随路径较长的几根滑条，
  再比较两边这些滑条各自单根的路径长度；折返滑条按来回全程计算。
- **Not asking (frozen, v0.2.1):** 不是比较滑条数量；不是比较跟随时间长短；
  不是把所有滑条路径相加。

> Withdrawn v0.2.0 wording (preserved as history, not used at launch):
> “哪一边较长的那批滑条，单根跟随路径更长？”
- **Human construct:** upper tail of single-slider follow path length within
  the segment — "较长的那批滑条" (the longer batch of sliders), repeats
  counted as full traversal. Players are NOT asked to estimate p90/max/
  median/total; those are computational proxies only.
- **Computational proxy (locked):** `ls.lazy_travel_distance_cs_normalised`
  segment p90 (the current rule input, zero-inclusive row population;
  unchanged) with `segment_max` as a secondary diagnostic.
- **Attribution matrix:** the frozen aggregation-direction matrix
  (`docs/HUMAN_TARGETED_RETEST_V02.json`) records max/p90/median/total
  directions per probe so future human/code disagreements are attributed to
  a specific aggregation — never by switching metrics after the fact.
- **Scope:** SEGMENT_PAIR (片段; presented with a clip-safe, equal-length
  8.5 s context window on both sides).

### Q-V02-SLIDER-TIME — 滑条持续跟随时间 (slider follow duration)

**AMENDMENT (P2B / v0.2.1) — wording and aggregation semantics frozen before
any human viewing.**

- **Question (frozen, v0.2.1):** 哪一边持续跟随较久的那批滑条，单根需要保持
  跟随更久？
- **Attend to (frozen, v0.2.1):** 先看每一边片段里各自持续跟随较久的几根
  滑条，再比较两边这些滑条单根的持续跟随时间长短。
- **Not asking (frozen, v0.2.1):** 不是比较路径长短；不是比较滑条数量；不是
  把整段跟随时间相加。

> Withdrawn v0.2.0 wording (preserved as history, not used at launch):
> “哪一边较长的那批滑条，单根需要保持跟随更久？” — “较长” re-introduced the
> spatial-length reading and was replaced by the pure-time wording above.
- **Human construct:** upper tail of single-slider follow duration within
  the segment — the longer-lasting batch of sliders, full traversal
  including all spans. Players are NOT asked to estimate p90/max/median/
  total; those are computational proxies only.
- **Computational proxy (locked):** p90 of per-slider
  `slider_total_duration_ms` over sliders whose start falls inside the
  canonical 5 s segment (Local v0.3 values, offline-computed; no new
  feature). Per-slider duration max is the secondary diagnostic.
- **Known trap this lock removes:** on S-T1-CORE-A, duration max/p90 point
  B while median/total point A. The construct (upper tail) fixes the
  intended reading to the max/p90 family; median/total stay visible in the
  attribution matrix only.
- **Scope:** SEGMENT_PAIR (片段; clip-safe, equal-length 8.5 s context
  window on both sides).

### Q-V02-DENSE — 连续快速点击压力 (dense click pressure)

- **Status:** `UNDER_REVISION`
- **Question (player-facing phenomenon, unchanged wording):**
  哪一边更常出现需要连续快速点击的密集段落？
- **Phenomenon definition:** the player judges whether one side more often
  contains dense sections that require continuous rapid tapping. No
  algorithm is bound to this question.
- **Why under revision:** P1.5 showed the fixed ≤125 ms window and every
  fixed ≤300 ms window fail to explain the B2 case; beat-relative sustained
  runs and general density are only PLAUSIBLE; the single-tap vs sustained
  sequence distinction is attested by a participant note but not uniquely
  identified; reversal/repeat structure is structural only (reversal ≠
  clicks); press/release and alternation require input data that does not
  exist.
- **Open hypotheses (from P1.5, none declared a winner):**
  - H1 beat-relative sustained runs (gaps ≤ 1.5× local beat);
  - H2 general object density;
  - H3 single-tap vs sustained sequence morphology.
- **Alignment analysis:** excluded from observable-alignment statistics until
  the construct is revised.

## Scope and presentation

- Q-V02-SPAN / Q-V02-URGENCY: whole-map playback (FULL_MAP).
- Q-V02-SLIDER-PATH / Q-V02-SLIDER-TIME: 5 s canonical segment playback with
  2.0 s before / 1.5 s after context.
- Per-side visible metadata: BID, CS, AR, object count, max BPM (unchanged
  from the current runner).
- Presentation order randomised per participant; responses canonicalised by
  the recorder. Exact-repeat and A/B-inversion controls use the policies in
  `docs/archive/HUMAN_TARGETED_RETEST_V01.md` (archived).

## Machine-readable definition

`docs/HUMAN_QUESTION_DEFINITIONS_V02.json` carries the same dimensions with
ids, wording, answer space, reasons and provisional analysis mappings.
