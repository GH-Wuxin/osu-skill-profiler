# SKILL_PROFILER_LABEL_EFFICIENCY_AUDIT_V01

Status: **AUDIT COMPLETE — NO HUMAN LABELS FABRICATED — NO FINAL MODEL TRAINING**

Repository: `osu-skill-profiler`
Date: 2026-08-15 (overnight audit)

This audit answers one question quantitatively: **how many human participants and
judgments does this project actually need before a useful, defensible Skill
Profiler is possible?** It does not train a final model and does not turn
AI-generated judgments into human labels.

---

## Phase A — Data asset inventory

64 project assets were inventoried; six requested external asset classes were
confirmed absent (not fabricated): tournament mappools, osu!collector data,
player BP data, osu_oracle outputs, external skill-category datasets, and
external classifier outputs.

| Asset | Count | Unit | Label type | Best use |
|---|---|---|---|---|
| `training/datasets/std_manifest.json` | 126,509 | beatmap samples | UNLABELED | training / stimulus mining |
| `corpus_scan.jsonl` | 134,554 | raw `.osu` scan lines | UNLABELED | corpus identity |
| `feature_qa_v02/*_5k/20k/full.jsonl` | 5,000 / 20,000 / 126,509 | map feature rows | DETERMINISTIC | training candidates / mining |
| `local_signal_qa_v03/*_5k/20k/full.jsonl` | 5,000 / 20,000 / 126,509 maps; 56,547,084 object rows full | per-object `ls.*` | DETERMINISTIC | construct computation / mining |
| slider rows with duration (full) | 23,964,086 | per-slider observations | DETERMINISTIC | PATH/TIME observables |
| `reference_signal_qa_v02/*` | 5,000 / 20,000 / 126,509 maps | per-object `ref.ppy.*` | MODEL-LIKE REFERENCE_ONLY | candidate mining only |
| `splits/v01` and `splits/v02` | 126,509 rows × 4 core files | beatmap split rows | IDENTITY/SPLIT | leakage-safe splits |
| weak-supervision pilot | 1,000 maps / 35,854 records | MAP+SEGMENT evidence | RULE_PSEUDO_LABEL | candidate mining |
| active-learning dry run | 93 tasks | pairwise tasks | NO LABEL | infrastructure |
| collection_001 snapshots | 59/59/64 responses | pairwise human answers | HUMAN_SMALL_N | construct/UI validation |
| pilot_v01 / pilot_v02 | 40 + 19 responses | pairwise human answers | HUMAN_SMALL_N | usability only |
| retest_v01 FORMAL | 13 raw responses | pairwise human answers | HUMAN_SMALL_N | FORMAL construct validation |
| gap-audit segment stats | 31,854 segments | segment-level p90/max | DETERMINISTIC | large-scale pair mining |
| gap-audit probes / rescreens | 4 + 25 + 3,498 candidates | candidate pairs/segments | DETERMINISTIC | pre-mined candidates |

Raw human response total: **136** (64 collection + 40 pilot_v01 + 19 pilot_v02
+ 13 retest). Retest independent sample count is **7** judgments (P01 6 + P05
1; P04 is a disclosed same-human duplicate and is excluded from independent
counts). No asset contains `HUMAN_GROUND_TRUTH`.

---

## Phase B — Label/evidence taxonomy

Explicit levels used by this audit:

- `HUMAN_GROUND_TRUTH`: **none found**; every human artifact declares
  `human_evidence_is_ground_truth=false`.
- `HUMAN_SMALL_N`: 136 pairwise responses; small-N, partially single-annotator.
- `DETERMINISTIC_OBSERVABLE`: Feature 0.2 / Local 0.3 / Reference 0.2 rows.
- `COMMUNITY_WEAK_LABEL`: **none found**.
- `RULE_PSEUDO_LABEL`: 35,854 weak-evidence records from 5 deterministic rules.
- `MODEL_PSEUDO_LABEL`: **none found** (no model trained).
- `UNLABELED`: corpus manifests and QA observables.

Six circular paths were flagged. The two most important:

- **CIRC-01**: `ls.lazy_travel_distance_cs_normalised` generates the
  slider-travel rule pseudo-label, drives active-learning selection, and is
  simultaneously locked as the PATH construct proxy. A future model validated
  on the same feature would be circular.
- **CIRC-02**: `spatial.distance_norm_p95` / `spatial.velocity_norm_per_s_p95`
  generate movement weak labels and are also the provisional mappings for
  Q-V02-SPAN / Q-V02-URGENCY.

Mechanical lineage gates exist (`dataset/leakage.py`, source registry, weak
lineage closure) and block weak-target leakage when invoked. Human-evidence
targets are **not** in the mechanical registry; that guard is currently
documentation-level only and must be added before training.

---

## Phase C — Weak-supervision source audit

Five real weak sources exist:

| Source | Family | Records | EMITTED | ABSTAINED | Disagreement | Suitability |
|---|---|---|---:|---:|---|---|
| local slider-travel segment | LOCAL_SIGNAL | 31,854 | 9,880 (31.0%) | 21,941 | single-source | mining / pseudo-labels |
| observable dense timing | OBSERVABLE | 1,000 | 450 (45.0%) | 550 | single-source | exploratory only |
| observable movement tail | OBSERVABLE | 1,000 | 194 (19.4%) | 804 | 0 vs snap tail | mining |
| observable slider control | OBSERVABLE | 1,000 | 99 (9.9%) | 900 | single-source | weak only |
| reference ppy snap tail | REFERENCE_PPY | 1,000 | 507 (50.7%) | 487 | 0 vs movement tail | reference-only |

Pilot totals: 11,130 EMITTED / 24,682 ABSTAINED / 42 UNAVAILABLE / 0 INVALID;
multi-source directional disagreement rate **0.0%** (191 agreement cases).
This means the current weak stack cannot discover disagreement; it is useful
for acquisition, not for validation.

External weak sources found: **none**. In particular mod labels are not and
must not be silently mapped to skill axes.

---

## Phase D — FORMAL pair re-audit

The three FORMAL core probes were recomputed from raw `.osu` files with the
production parser and Local Signal 0.3 extractor. Beatmap identities, segment
bounds, and slider filters all reproduce.

The package field `path_p90` is the **zero-inclusive segment p90** (the
historical rule input). The current audit definition says the PATH primary
observable is **slider-only p90**. Both were computed:

| Probe | Side | package `path_p90` | recomputed zero-inclusive p90 | recomputed slider-only p90 | slider-only max | TIME p90 (slider-only) | TIME max |
|---|---:|---:|---:|---:|---:|---:|
| S-T1-CORE-A | A | 104.867 | 104.867 | 105.054 | 105.241 | 818.18 ms | 818.18 ms |
| S-T1-CORE-A | B | 104.842 | 104.842 | 105.129 | 105.227 | 372.67 ms | 372.67 ms |
| S-T2-CORE-A | A | 290.476 | 290.476 | 323.027 | 388.128 | 1248.00 ms | 1440.00 ms |
| S-T2-CORE-A | B | 60.663 | 60.663 | 60.663 | 78.795 | 1152.00 ms | 1440.00 ms |
| S-T2-CORE-B | A | 282.806 | 282.806 | 282.806 | 282.806 | 666.67 ms | 666.67 ms |
| S-T2-CORE-B | B | 60.292 | 60.292 | 73.495 | 106.505 | 555.56 ms | 666.67 ms |

**Result: FORMAL package values REPRODUCED for the zero-inclusive rule p90;
no parser/version drift found.** The audit does **not** change FORMAL status.
It records two reproducibility boundaries:
1. The machine package stores **zero-inclusive** p90, while the current
   construct definition says **slider-only** p90. On S-T2-CORE-A side A the
   difference is 290.476 vs 323.027 (+11.2%), large enough to flip a
   borderline human/code comparison.
2. Percentile method differs: production `_percentile` uses linear
   interpolation `q*(n-1)`; the package's slider-only p90 equals the
   nearest-rank/ceil p90 (often the max for n=4–6). Analysis must use
   production linear p90 and must not silently substitute package fields.

---

## Phase E/F/G — High-information pair mining

Base pool: 31,854 weak-supervision pilot segments; after human-judgeable
filters (`n_sliders 4..30`, `path_p90 20..400`, `path_max ≤600`,
`time_p90 80..2500`, `time_max ≤3000`) the pool is **19,594 segments**.
A deterministic sampler mined **200 primary pairs (20 per class P1–P10)**
plus **1,000 reserve pairs** (100 per class). All primary classes are filled.

Class definitions:

- P1 PATH separated / TIME matched
- P2 TIME separated / PATH matched
- P3 PATH/TIME same direction
- P4 PATH/TIME inversion
- P5 both close
- P6 large-effect sanity control
- P7 near perceptual threshold
- P8 repeat-heavy
- P9 slider-density confound
- P10 structural anomaly / stress

Matching frontier (robust z, human-judgeable pool):

- Random pairs: mean covariate distance 4.85 z (PATH) / 4.83 z (TIME) at
  target separation 1.31 z / 1.24 z.
- Constrained search at covariate radius 0.25 z finds 1,219 PATH / 701 TIME
  pairs at mean distance 0.14 z / 0.13 z and separation 1.15 z / 1.47 z;
  radius 1.0 z finds 1,991 PATH / 1,953 TIME pairs at distance 0.71 z / 0.68 z
  and separation 3.15 z / 2.79 z. Strong separation and tight covariate
  matching are a genuine trade-off; radius 0.5–1.0 z is the practical
  frontier.

Ranked queues: TOP_25 / TOP_50 / TOP_100 / TOP_200 are persisted in
`docs/SKILL_PROFILER_HIGH_INFORMATION_PAIRS_V01.json`. Every entry carries a
`why` reason restricted to construct isolation, inversion, threshold
calibration, density confound, or sanity control.

Best confound-controlled pairs found (see JSON for full records):

- PATH: `5401d71cfe43::3` vs `b2e64a8505d0::3` — PATH 21.3 vs 105.2,
  TIME 408 vs 435 ms, 0 confound flags, covariate distance 4.48 z.
- TIME: `a1fe127b6ee9::23` vs `92f9fc221f3e::1` — TIME 632 vs 380 ms,
  PATH 79 vs 83, 1 confound flag, covariate distance 2.33 z.

These are internal audit artifacts; target metrics are never participant-
facing.

---

## Phase H — Active-learning simulation

Offline surrogate-oracle simulation (logistic regression, budgets
25/50/100/200/300/500/1000, 5 deterministic seeds, 20% held-out). The oracle
is derived from deterministic rule/feature decisions; **AUC is relative
label-efficiency signal, not human accuracy**.

- PATH surrogate task: random sampling reaches mean AUC 0.794 at budget 25
  and 0.856 at budget 1000. Uncertainty+diversity reaches 0.791 / 0.855.
- TIME surrogate task: random reaches 0.645 / 0.786; uncertainty+diversity
  reaches 0.667 / 0.788.
- Median budget to target AUC: PATH random **25**, disagreement 50,
  diversity 100, uncertainty 200, U+D 200, construct-targeted 500.
  TIME random **100**, uncertainty 100, diversity 150, U+D 200,
  disagreement 300, construct-targeted 750.

**Conclusion: with the current surrogate oracle, intelligent acquisition does
NOT materially beat random sampling, and random is often cheapest.** This is
expected: the surrogate target is already a smooth function of the pair
features used by the selector. It does not mean active learning is useless;
it means the current weak labels are too circular/too easy to replace with
the target metric to demonstrate label-efficiency gains. A valid efficiency
test needs an oracle that is not derivable from the acquisition features.

---

## Phase I/J — Small-N protocols and participant-vs-judgment efficiency

Full protocols are in
[`docs/SKILL_PROFILER_SMALL_N_PROTOCOL_V01.md`](SKILL_PROFILER_SMALL_N_PROTOCOL_V01.md).

Headline designs:

| Protocol | Participants | Unique pairs | Judgments | Burden/person | Defensible claim |
|---|---|---|---:|---:|---|---|
| N=1 | 1 (disclosed author) | 27 | 72 | ≈1 h | within-person reliability; construct introspection |
| N=3 | 3 | 30 | 264 | ≈1.5 h | + between-person agreement |
| N=5 | 5 | 40 | 570 | ≈2 h | + threshold location |
| N=10 | 10 | 50 | 1,400 | ≈2.5–3 h | + simple calibration models |

Participant N, unique-stimulus N, and total-judgment N are reported
separately. Repeated N=1 sessions are never counted as participants.

---

## Phase K — Bootstrap / uncertainty analysis

Bootstrap over 23,015 eligible slider segments (n_sliders ≥ 4) with 300
resamples per formal side:

- Formal side percentile positions are stable to ±0.5–0.7 percentile points
  (95% bootstrap interval width), so the FORMAL pairs' corpus positions are
  not sampling accidents.
- Top-100 PATH segments retain mean rank 49.5 under full-pool resampling,
  exactly the expected mean for a top-100 set: the extreme tail ranking is
  stable but individual ranks inside the tail remain exchangeable.
- No participant bootstrap is performed or implied.

---

## Phase L — Feature redundancy / proxy audit

5,000-map Feature 0.2 matrix (106 features). Confirmed near-duplicates
(Spearman ≥ 0.99):

- `temporal.burst_count_250ms` ↔ `temporal.dense_section_count` (1.000)
- `temporal.burst_longest_duration_ms_250ms` ↔
  `temporal.longest_dense_section_ms` (1.000)
- `slider.repeat_count_max` ↔ `slider.span_count_max` (0.99998) — not a
  semantic duplicate but trivially interchangeable on this corpus
- `section.duration_weighted_density_per_s` ↔ `temporal.density_objects_per_s`
  (0.995)
- `section.velocity_norm_per_s_p90` ↔ `spatial.velocity_norm_per_s_p95`
  (0.996) — map-level and section-level velocity tail are interchangeable
- slider velocity p90 ↔ p95 (0.997) and other adjacent percentiles.

Proxy findings:

- PATH (`lazy_travel_distance` p90) is **not** dominated by any single
  Feature-0.2 map-level field; it needs per-slider rows. That is why the
  project moved to `ls.*`.
- TIME (`slider_total_duration_ms` p90) is mechanically related to
  `slider.length_px / slider.velocity`, but map-level duration aggregates are
  dominated by pathological max values and are not a substitute.
- Slider fraction and repeat/span counts are density/mapping-style confounds;
  they must be matched in pairs, never calibrated as skill dimensions alone.
- `ref.ppy.snap_include_sliders` has documented heavy tails
  (max ≈ 2.5e11) and should never be a raw model input; it is REFERENCE_ONLY.

Consequence: humans should not be asked to separately calibrate adjacent
percentiles (p90/p95) or duplicate density aliases.

---

## Phase M — Leakage-safe split recommendation

Reuse `dataset/split_v01.py` as canonical (SHA-256 component ranking,
train/val/test 80/10/10) and add future grouping keys:

1. `set_group_key` — beatmapset id, else local set folder.
2. `mapper_group_key` — normalised exact creator name.
3. `checksum_class` — identical and conflicting checksums stay in one component.
4. Future `tournament_pool_id` / `collection_id` — group whole pool/collection.
5. Future `player_bp_cluster_id` — group by player cluster if BP data ever
   enters.
6. Pseudo-label ancestry: any model target derived from a weak rule inherits
   that rule's lineage and is leakage-checked via `audit_candidate_schema`.

Near-duplicate difficulties, same-set revisions, and challenge subsets are
already covered by existing v02 artifacts. The existing `v02` split is the
recommended starting point for training data; challenge subsets stay
held-out diagnostics.

---

## Phase N — Model complexity vs label budget

| Budget (human judgments) | Maximum defensible model |
|---|---:|
| 100 | hand-tuned rules; Bradley-Terry with strong priors |
| 300 | linear / logistic / ordinal regression; simple pairwise model |
| 500 | sparse linear + shallow tree as diagnostic |
| 1,000 | small regularized GBDT |
| 2,000 | GBDT / splines |
| 5,000 | modest GBDT; neural nets remain unjustified |

Any simulation model used in this audit is disposable and marked
non-production.

---

## Phase O — Weak supervision + human calibration plans

- **PLAN A (human-heavy):** 10 participants × 140 judgments = 1,400.
  Strongest threshold calibration and between-person variance. Weakness:
  recruitment cost and slowest to v1.
- **PLAN B (hybrid, recommended):** 5 participants × 114 judgments = 570
  targeted human judgments + deterministic pair mining + weak-source filtering.
  Human labels only calibrate; weak labels only select.
- **PLAN C (minimal-human):** 1 disclosed author, 4 repeated sessions × 18
  judgments = 72, plus hidden repeats and controls. Viable path: validate
  wording/UI, measure author repeat reliability, then use the author as an
  expert prior in a Bradley-Terry model. It cannot claim population validity.

---

## Phase P — Sequential stopping rules

Declared in `SKILL_PROFILER_SMALL_N_PROTOCOL_V01.md`; admissible quantities
are repeat consistency, pair-level agreement, construct-direction agreement,
and calibration stability. “Collect until it looks good” is forbidden.

- N=1: 4 sessions; stop if ≥5/6 hidden repeats directionally consistent;
  otherwise at most 2 extra sessions and report failure mode.
- N=3+: ≥20 double-covered pairs per construct and directional agreement
  ≥0.80, or pre-registered maximum.
- N=5+: add adjacent-block calibration-stability gate.
- N=10+: held-out weak-label agreement is secondary evidence only.

---

## Phase Q — Human label UI / manifest preparation

The participant-facing schema (no answers, no metrics) and unblinding-manifest
rules are defined in `SKILL_PROFILER_SMALL_N_PROTOCOL_V01.md` §10.

**Status:** reusable generator delivered at
`tools/skill-profiler-label-manifest.py`. A 200-trial manifest was generated
to `tmp/label_audit/manifest_v01/` from the TOP-100 candidate set:
`participant_manifest.json` (SHA-256 `7778b6ad…`, no answers, no metrics,
no pair ids, no class ids) and separate `unblinding_manifest.json`. No human
was asked to label anything during this audit.

---

## Phase R — Final "How many humans?" answer

1. **Absolute minimum useful participant count:** 1 (only for author
   introspection and within-person reliability; not population validation).
2. **Minimum useful total human judgments:** 72 (N=1 protocol with hidden
   repeats), but this only supports construct/workflow claims.
3. **Recommended realistic participant count:** 3–5 distinct participants.
4. **Recommended realistic total judgments:** 264–570.
5. **Point of diminishing returns under current scope:** ≈ 5 participants /
   570 judgments for PATH/TIME threshold calibration; additional participants
   mostly reduce agreement variance, not construct uncertainty.
6. **N=1 makes possible:** UI/wording validation, author repeat reliability,
   construct introspection, calibration of the author's own threshold.
7. **N=3 makes possible:** first between-person agreement estimate.
8. **N=5 makes possible:** stable construct direction and rough threshold.
9. **N=10 makes possible:** simple pairwise calibration model and limited
   generalization statement.
10. **Are 20–30 participants necessary?** No. For the current two-construct
   slider question, 20–30 participants are unnecessary unless the goal is a
   population-representative psychometric instrument. Three to five
   well-controlled participants with repeats provide more information per
   label than 20 untrained drop-in visitors.

---

## Final required report

1. **Total usable raw beatmaps:** 126,509 (std_manifest success records).
2. **Total usable slider observations:** 23,964,086 slider rows with duration;
   56,547,084 total object rows.
3. **Human labels currently available:** 136 raw pairwise responses;
   7 independent retest judgments for the current FORMAL constructs.
4. **Weak-label sources found:** 5 deterministic rules.
5. **Weak-label coverage:** 1,000-map pilot; 35,854 records; EMITTED 31.0%.
6. **Weak-label disagreement rates:** 0.0% directional disagreement among
   multi-source cases (191 agreement cases).
7. **FORMAL pair reproducibility result:** REPRODUCED for package
   zero-inclusive p90; slider-only PATH p90 differs and must be used per
   current construct definition.
8. **Total candidate pairs mined:** 200 primary (20 per class P1–P10) +
   1,000 reserve pairs (100 per class) = 1,200 in the persisted JSON.
9. **High-information pair counts by class:** P1 20, P2 20, P3 20, P4 20,
   P5 20, P6 20, P7 20, P8 20, P9 20, P10 20 (primary); 100 reserves each.
10. **Best confound-controlled PATH pairs:** top recorded pair
    `5401d71cfe43::3` vs `b2e64a8505d0::3` (PATH 21.3 vs 105.2, TIME 408 vs
    435 ms, 0 confound flags); full top list in JSON.
11. **Best confound-controlled TIME pairs:** top recorded pair
    `a1fe127b6ee9::23` vs `92f9fc221f3e::1` (TIME 632 vs 380 ms, PATH 79 vs
    83, 1 confound flag); full top list in JSON.
12. **Active-learning simulation result:** surrogate logistic AUC
    PATH 0.856 full pool / TIME 0.786 full pool; learning curves and all
    strategy curves persisted in `SKILL_PROFILER_ACTIVE_LEARNING_SIM_V01.json`.
13. **Random vs active label-efficiency comparison:** random sampling matched
    or beat every active strategy on median budget to target AUC (PATH random
    25 labels vs disagreement 50, diversity 100, uncertainty/U+D 200,
    construct-targeted 500). With the current surrogate oracle, active
    selection does not materially reduce label count.
14. **Feature redundancy findings:** see Phase L (6 near-duplicate groups).
15. **Major proxy/confound findings:** zero-inclusive vs slider-only p90;
    duration vs path; slider fraction/repeat confounds; star/BPM/CS/AR
    displayed metadata.
16. **Leakage-safe split recommendation:** existing v02 SHA-256 group split
    plus future pool/collection/BP/pseudo-label lineage keys (Phase M).
17. **Model complexity vs label budget:** see Phase N.
18–21. **N=1/N=3/N=5/N=10 protocols:** see
    `SKILL_PROFILER_SMALL_N_PROTOCOL_V01.md`.
22. **Minimum useful human judgment count:** 72.
23. **Recommended realistic human judgment count:** 264–570.
24. **Recommended realistic participant count:** 3–5.
25. **20–30 participants necessary?** No.
26. **Top 50 first labels to collect:** the persisted `TOP_50` queue in
    `docs/SKILL_PROFILER_HIGH_INFORMATION_PAIRS_V01.json`; order starts with
    P6 sanity controls, then P2/P1/P3/P4 diagnostic pairs. The queue must be
    consumed through the blinded manifest generator, never with metric values
    visible to participants.
27. **Estimated participant burden:** N=1 ≈1 h; N=3 ≈1.5 h/person;
    N=5 ≈2 h/person; N=10 ≈2.5–3 h/person.
28. **Sequential stopping rules:** Phase P / protocol doc.
29. **Generated experiment-manifest status:** generator ready
    (`tools/skill-profiler-label-manifest.py`, syntax verified); no manifest
    was pre-generated with fake labels.
30. **Files added/modified:** new outputs:
    `docs/SKILL_PROFILER_LABEL_EFFICIENCY_AUDIT_V01.md`,
    `docs/SKILL_PROFILER_LABEL_BUDGET_V01.json`,
    `docs/SKILL_PROFILER_WEAK_SUPERVISION_V01.json`,
    `docs/SKILL_PROFILER_HIGH_INFORMATION_PAIRS_V01.json`,
    `docs/SKILL_PROFILER_ACTIVE_LEARNING_SIM_V01.json`,
    `docs/SKILL_PROFILER_SMALL_N_PROTOCOL_V01.md`,
    `tools/skill-profiler-pair-mine.py`,
    `tools/skill-profiler-label-manifest.py`; scratch under
    `tmp/label_audit/` only.
31. **Verification results:** all six required JSON/MD outputs parse
    (`json.loads` OK); retest harness still 10/10 PASS; full unittest suite
    305/305 PASS; no production `src/` modules were modified by this audit;
    no commit, no push.
32. **No fake human labels:** CONFIRMED.
33. **No final model training:** CONFIRMED.
34. **No commit:** CONFIRMED.
35. **No push:** CONFIRMED (no remote configured).
36. **Recommended next phase:** freeze the small-N protocol and run N=1 author
    sessions while waiting for 2–4 more distinct participants; do not start
    training.
