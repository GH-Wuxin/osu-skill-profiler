# Segment Signal QA v0.1 - Local vs Official Reference

Status: **PASS** (2026-08-11)

Artifacts:

```text
training/datasets/reference_signal_qa/reference_qa_5k.jsonl    (exact objects, 5,000 maps)
training/datasets/reference_signal_qa/reference_qa_20k.jsonl   (exact objects, 20,000 maps)
training/datasets/reference_signal_qa/reference_qa_full.jsonl  (per-map summaries, 126,509 maps)
training/datasets/reference_signal_qa/reference_qa_stats.json  (combined stats, all gates)
training/datasets/reference_signal_qa/segment_stats.json       (segment QA)
training/datasets/reference_signal_qa/reference_disagreement_candidates.jsonl
training/datasets/reference_signal_qa/REFERENCE_QA_REPORT.md
```

Pipeline per map:

```text
parse -> normalise -> v0.1 features (frozen) -> ls.* v0.2 -> ref.ppy.* v0.1
      -> object alignment -> fixed 5 s reference segment summaries -> QA
```

## 1. Dataset gates

| Gate | Records | OK | Failures | NaN/Inf maps | Geometry-blocked maps/objects | Unavailable rows | Core records |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5k | 5,000 | 5,000 | 0 | 0 | 18 / 637 | 233,625 | 4,672 |
| 20k | 20,000 | 20,000 | 0 | 0 | 22 / 642 | 579,739 | 19,672 |
| full | 126,509 | 126,509 | 0 | 0 | 53 / 819 | 2,924,914 | 126,181 |

Ordering failures: 0 in every phase. Object alignment failures: 0. Segment
coverage failures: 0. Serialization failures: 0. Aggregate non-finite: 0.
Extreme finite reference rows: 19 (provenance-tagged, never clipped).

Geometry-blocked counts match the existing Local Signal v0.2 baseline exactly
(18/637, 22/642, 53/819), which is expected because both layers share the same
audited slider guards.

## 2. Per-signal distributions (full corpus, streaming/online)

Units are policy-scaled and dimensionless; see
`docs/PPY_REFERENCE_SIGNAL_CONTRACT_V01.md` for exact semantics.

| Signal | Count | Missing | Min | Max | Mean | p50 | p95 | p99 | Zero rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `snap_include_sliders` | 56,419,385 | 127,699 | 0.0 | 2.49e11 | 3.36e4 | 0.909 | 3.170 | 4.795 | 0.0295 |
| `snap_exclude_sliders` | 56,420,575 | 126,509 | 0.0 | 232.9 | 1.308 | 0.794 | 3.030 | 4.370 | 0.0366 |
| `agility` | 56,419,769 | 127,315 | 0.0 | 1068.4 | 15.65 | 7.015 | 37.93 | 65.20 | 0.0993 |
| `flow_include_sliders` | 56,419,385 | 127,699 | 0.0 | 1.61e17 | 8.20e9 | 0.781 | 5.944 | 10.56 | 0.1032 |
| `flow_exclude_sliders` | 56,420,575 | 126,509 | 0.0 | 448.6 | 1.761 | 0.651 | 5.659 | 9.613 | 0.1047 |
| `speed` | 56,267,710 | 279,374 | 0.0 | 2571.8 | 37.41 | 10.99 | 120.9 | 163.1 | 0.0038 |
| `rhythm` | 56,331,399 | 215,685 | 0.0 | 3.407 | 1.165 | 1.150 | 1.328 | 1.503 | 0.0038 |
| `speed_with_rhythm` | 56,178,727 | 368,357 | 0.0 | 4445.4 | 44.23 | 13.12 | 142.6 | 194.5 | 0.0038 |
| `reading` | 53,700,708 | 2,846,376 | 0.0 | 2.37e7 | 19.57 | 0.0 | 86.86 | 153.9 | 0.7176 |

Missingness is dominated by documented semantics: the first raw object of
every map has no difficulty row (126,509 rows), legacy maps without AR/OD
contribute the bulk of `reading`/`speed`/`rhythm` missingness, and
geometry-blocked sliders contribute the small include-variant surplus.
`reading` has a 71.8% zero rate because the upstream evaluator legitimately
returns 0 for most non-reading-intensive objects; this is not missingness.

The `include_sliders` variants carry pathological finite maxima (2.49e11 and
1.61e17) from extreme slider/BPM inputs. They are provenance-tagged, never
clipped, and should be handled as policy blow-up indicators, not ordinary
difficulty values.

## 3. Correlations (ref vs ls)

### 3.1 Map-level (signal means, exact 5k)

28 pairs with |Pearson| > 0.5. Strongest:

| ref signal | ls signal | Pearson | Spearman |
| --- | --- | ---: | ---: |
| `snap_include_sliders` | `lazy_jump_distance_cs_normalised` | 1.000 | 0.481 |
| `snap_include_sliders` | `minimum_jump_distance_cs_normalised` | 1.000 | 0.562 |
| `flow_include_sliders` | `lazy_jump_distance_cs_normalised` | 1.000 | 0.595 |
| `reading` | `lazy_jump_distance_cs_normalised` | 0.99999 | 0.402 |
| `snap_exclude_sliders` | `hit_window_great_ms` | -0.818 | -0.907 |
| `snap_exclude_sliders` | `preempt_ms` | -0.805 | -0.937 |
| `agility` | `hit_window_great_ms` | -0.741 | -0.894 |

Pearson = 1.0 on map means is driven by the handful of extreme finite rows;
the much lower Spearman values (0.4-0.6) are the more honest rank-level
relationship. Negative correlations with `hit_window_great_ms` / `preempt_ms`
reflect that harder maps (small hit windows / shorter preempt) carry higher
snap/agility reference means.

### 3.2 Object-level natural partners (bounded 300k sample, 5k maps)

| ref signal | ls partner | n | Pearson | Spearman |
| --- | --- | ---: | ---: | ---: |
| `snap_include_sliders` | `lazy_jump_distance_cs_normalised` | 297,946 | 0.811 | 0.364 |
| `snap_exclude_sliders` | `jump_distance_cs_normalised` | 298,026 | 0.317 | 0.337 |
| `agility` | `lazy_jump_distance_cs_normalised` | 297,973 | 0.005 | 0.126 |
| `flow_include_sliders` | `lazy_jump_distance_cs_normalised` | 297,946 | 0.938 | 0.656 |
| `flow_exclude_sliders` | `jump_distance_cs_normalised` | 298,026 | 0.508 | 0.625 |
| `speed` | `adjusted_delta_time_ms` | 296,607 | -0.242 | -0.987 |
| `rhythm` | `delta_time_ms` | 297,497 | -0.182 | -0.366 |
| `reading` | `preempt_ms` | 242,701 | -0.003 | -0.112 |

Findings:

- `flow_include_sliders` is the most linearly coupled to its natural observable
  (lazy jump, Pearson 0.94), while `snap_include_sliders` has strong linear
  coupling but weak rank coupling (0.36), i.e., the policy scaling changes
  ordering.
- `speed` vs `adjusted_delta_time` is strongly rank-monotone but inverse
  (Spearman -0.99): smaller adjusted delta -> higher speed reference. This is
  the expected direction; upper-tail overlap in section 4 must be read with
  that direction in mind.
- `reading` is essentially uncorrelated with preempt at object level: the
  reading evaluator is density/angle driven, not a preempt proxy.
- `agility` at object level is nearly uncorrelated with lazy jump in Pearson
  terms (0.005) and only weakly rank-correlated (0.13): the evaluator's
  movement/time interaction and bonuses dominate.

## 4. Upper-tail overlap (object-level natural partners)

For each pair, thresholds are each signal's own empirical 95th/99th
percentile over the bounded sample; overlap is descriptive only, never
semantic equivalence.

| ref signal | both@95 (given ref) | both@99 (given ref) |
| --- | ---: | ---: |
| `snap_include_sliders` | 0.269 | 0.146 |
| `snap_exclude_sliders` | 0.191 | 0.096 |
| `agility` | 0.036 | 0.003 |
| `flow_include_sliders` | 0.380 | 0.255 |
| `flow_exclude_sliders` | 0.267 | 0.155 |
| `speed` | 0.000 | 0.000 |
| `rhythm` | 0.012 | 0.000 |
| `reading` | 0.000 | 0.000 |

Interpretation:

- Flow and snap include-variants share roughly a quarter to a third of their
  extreme tails with the raw lazy-jump observable; the rest of the extreme
  reference values are produced by timing/angle/bonus policy, not by spacing
  alone.
- Agility's extreme objects are almost never extreme in lazy jump alone
  (3.6% @95): extreme agility is a combination signal, not a spacing spike.
- `speed` shows 0% overlap because the tail directions oppose (high speed =
  low adjusted delta); the negative Spearman (-0.99) is the meaningful
  relationship. Same directional caveat applies to `rhythm` (fast rhythms
  correspond to low deltas).
- `reading` has no tail overlap with preempt; its extreme regime is not a
  reaction-time regime at object level.

## 5. Reference-disagreement candidates

Methodology (EXPLORATORY, NON-CONTRACT, NON-SKILL):

- bounded deterministic sample of 300,000 object rows from the exact 5k phase;
- tie-robust empirical tail status per signal: high tail = value strictly
  above the 99.5th percentile of that signal's own sample, low tail =
  strictly below the 0.5th percentile, ordinary = between the 5th and 95th
  percentiles;
- Type A candidate: at least one `ref.ppy.*` extreme while all finite
  selected `ls.*` values are ordinary;
- Type B candidate: at least one `ls.*` extreme while all finite
  `ref.ppy.*` values are ordinary;
- no learned composite score; candidates are ranked only by the number of
  extreme signals.

Results:

| Type | Candidates before cap | Kept | Distinct maps |
| --- | ---: | ---: | ---: |
| A (ref extreme, ls ordinary) | 0 | 0 | 0 |
| B (ls extreme, ref ordinary) | 1,496 | 50 | 41 |

Type A = 0 means: in this sample, whenever a reference evaluator is in its own
extreme tail, at least one selected observable is also outside the ordinary
band. This is consistent with the reference signals being policy transforms of
the same observables.

Type B = 1,496 objects (0.50% of the sample) where observables form an extreme
combination while all major reference values stay ordinary. The 50 strongest
cases are in `reference_disagreement_candidates.jsonl`. Representative
sanitized cases (relative paths only):

Case 1: `1214 They Might Be Giants - I'm Impressed/... [Insane].osu`
(`sha256:39e8f7db26497adda7c04449932240c6d8c45d0d79411abc6e02639fbfa89514`),
object 160 (time-sorted 160), segment 90458-95458 ms:
`travel_distance_cs_normalised = 793.6`, `travel_time_ms = 1464.1`,
`radius_px = 23.05` (high CS), `slider_nested_object_count = 11`, while all
ref values are ordinary (e.g. `snap_include = 1.87`, `speed = 11.0`,
`flow_include = 1.18`). This is a long-travel, high-repeat slider with heavy
observable loading that the reference evaluators keep ordinary.

Case 2: `46 Hinoi Team - Aishiteru/... [Sweatin].osu`
(`sha256:38ea890ea0510c32df5fdc163a766ad10233bc0ef5c0db46df26504729469db5`),
object 55, segment 37035-42035 ms:
`jump_distance_cs_normalised = 595.7`, `radius_px = 27.53`, with ref values
ordinary (`snap_include = 2.07`, `agility = 4.02`, `rhythm = 1.08`). A large
CS-normalised jump that the reference policy does not flag as extreme.

These are human-inspection candidates, not labels, not "official blind
spots", and not features.

## 6. Segment information-preservation findings (exact 5k)

Segment structure:

- segments: 161,624 over 5,000 maps; segments/map mean 32.3, p50 25, max 564;
- objects/segment global mean 16.0;
- empty segments: 0; sparse segments (<= 2 objects): 3.46%;
- fixed 5 s buckets by construction; trailing bucket may extend past the last
  object (no short trailing windows are produced by the reference segmenter).

Preservation metrics:

- **Spike preservation (segment max == object max):** 3,960-4,985 maps per
  signal (reading lowest); the global object-level maximum survives into a
  segment max on ~99.5% of maps for most signals.
- **Upper-tail containment:** every object >= map p95 lies in a segment whose
  max >= map p95 (100% by construction - a consistency invariant, not a
  quality claim).
- **Segment p95 retention:** only 15.9%-43.1% of segments (per signal) have a
  segment-level p95 >= the map-level object p95 (speed 43.1%, rhythm 15.9%).
  In other words, 5 s windows dilute upper-tail concentration for most
  segments: the peak survives, but the "top 5% of the map" is usually spread
  across windows rather than concentrated in any one window.
- **Boundary sensitivity:** 10.2% of objects >= map p90 lie within 250 ms of a
  5 s boundary; spikes near boundaries are at risk of being split between two
  windows.
- **Sustained peaks:** 4,970/5,000 maps have at least one signal with >= 2
  segments whose max >= map p95 (long sustained upper-tail sections).

Conclusion: the fixed 5 s segmenter preserves global maxima well and is a
reasonable coarse "where is the map hard" index, but it materially dilutes
p95-level structure and is boundary-sensitive for short spikes. No production
segmenter change is made in this task; future candidates are overlapping
windows, adaptive sections, object-count windows and event-centered windows.

## 7. Performance

Per-map CPU latency (full corpus):

| Statistic | Value |
| --- | ---: |
| p50 | 367.6 ms |
| p95 | 1,418.0 ms |
| p99 | 2,612.1 ms |
| max | 436,867 ms (pathological finite map) |
| mean | 569.3 ms |

Wall-clock extraction: 5k 330 s (16 workers), 20k 788 s (16 workers), full
~6,355 s total (first 101,965 maps @16 workers, remaining 24,544 @4 workers;
~19.9 maps/s wall average).

Latency scaling (log-log slope): object_count 0.89-1.02, slider_count 0.93,
nested_count 0.97, segment_count 1.05-1.16 across phases. No O(n^2) hotspot.

Slowest maps (full): `1799396 False Noise - Hyperlight` (436.9 s, 567
objects), `1746664 Kotoha - God-ish` (203.8 s, 727 objects), `1235519 O2i3 -
Ping [Aspire]` (188.1 s, 428 objects, `bpm_extreme_high` + `aspire_like`).

## 8. Known limitations

- `UPSTREAM_EXECUTABLE_PARITY = BLOCKED`: values are source-audited
  reimplementations, not C# harness output.
- Stacking is not modelled; raw coordinates are used.
- Slider lazy geometry is shared with Layer A and inherits its guard
  semantics (blocked rows are provenance-tagged).
- Pearson map-level values are distorted by 19 extreme finite rows; Spearman
  is the safer ranking measure.
- Tail overlap is directional; `speed` / `rhythm` must be read with the
  inverse timing direction.
- Segment `start_idx`/`end_idx` are time-sorted positions, not file order.
- The QA tool duplicates shared selection/statistics infrastructure from
  `feature_qa.py` / `local_signal_qa.py` (`TECH_DEBT_QA_COMMON`).

## 9. No taxonomy statement

This document infers no taxonomy. No cluster, no skill axis, no "tech",
"jump", "stream", "finger control" or "reading" classification is asserted.
The only statements are source-grounded descriptive ones: high/low reference
regimes, observable/reference disagreement candidates, and segment
preservation statistics.
