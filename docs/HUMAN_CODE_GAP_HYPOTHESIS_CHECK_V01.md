# Human–Code Gap P1.5 — Hypothesis Falsification / Evidence Closure v0.1

Date: 2026-08-14
Repository: `osu-skill-profiler`
Phase: P1.5 (read-only; no training, no commit, no analyzer change, no new
human data). Follows P1 `HUMAN_CODE_GAP_AUDIT_V01.md` and the
`snapshot-a33e951ca690cf1904b0d244` evidence baseline.

## 1. P1 wording review (task A)

Two P1 statements were over-strong and were amended minimally, each marked
`AMENDMENT (P1.5)` in the source documents:

- **A1 (B2 reversal).** P1 listed "slider-repeat click pressure" as a B2
  candidate. Reversal/repeat structure is a salient-difference candidate, but
  reversal is NOT equivalent to extra clicks, and no replay/input data exists
  to establish additional clicks. The term "折返点击压力" is withdrawn as a
  finding; the candidate is now worded "slider reversal / repeat structure —
  a structural candidate only". Amended in `HUMAN_CODE_GAP_AUDIT_V01.md`
  (B2 section, wording check, §6, §7) and `HUMAN_CODE_GAP_DISPOSITION_V01.json`
  (B2 notes). The handover's top-finding wording was aligned as well.
- **A2 (B4/B5/B6 follow duration).** "Follow duration is the strongest
  candidate" is retained, but is now explicitly marked as **correlational
  evidence, not causal identification**: within the three pairs, distance and
  duration did not vary independently, so which observable the players used
  is not uniquely identified. Amended in the cross-case pattern §5.3, §6 and
  the "still undetermined" list, plus B4/B5/B6 notes in the disposition JSON.
  The `MISSING_OBSERVABLE` dispositions are unchanged.

Two additional internal corrections surfaced during P1.5 (no P1 doc change
needed, recorded here for provenance):

- **Dense-task canonical directions.** Four dense tasks
  (`task-2bd327c3…`, `task-a933aa2d…`, `task-d545e72e…`,
  `task-4319b133…`) were presented in BA order; their canonical directions
  are A, A, A, B respectively. The P1.5 dense statistics use these verified
  canonical ordinals (checked against `human_evidence.jsonl`).
- The B2 "Visual" description ("tap–tap rhythm") was softened to
  "back-and-forth slider-repeat rhythm" for consistency with A1.

## 2. Slider competing hypotheses (task B intro)

- **H_distance:** players judge "更远的持续跟随" mainly by slider
  path/follow DISTANCE (what the current rule measures: CS-normalised lazy
  travel p90; related distance readings: `segment_max`, raw rendered max
  trail).
- **H_duration:** players judge mainly by per-slider follow DURATION / the
  time tail (what the rule does not consume, although the pipeline computes
  it — see §4).

## 3. Existing counterbalanced probes (task B)

Search: all 31,821 slider_tracking SEGMENT rows in the weak-supervision pilot
evidence, joined to the `.osu` corpus via the Feature QA 5k index; per-segment
per-slider follow durations computed offline with the unchanged project
parser. 9,355 segments passed the judgeability filters. Result:

```text
Type 1 (p90 equal, duration clearly different): 1,295,027 pairs
Type 2 (duration equal, p90 clearly different): 2,000,694 pairs
parse failures: 0; missing assets: 0
```

**Verdict: counterbalanced pairs EXIST in the current corpus; no fabrication
needed.** Four probes were curated (machine-readable details in
`docs/HUMAN_CODE_GAP_PROBES_V01.json`):

| Probe | Type | Discriminates | p90 path | seg_max | follow-duration p90 | Key contrast |
|---|---|---|---|---|---|---|
| S-PROBE-T1-01 | 1 | H_duration | 74.6621 vs 74.6625 | 104.7 vs 79.4 | 375 vs 2153.8 ms (5.74×) | every distance metric equal or favours A; duration favours B |
| S-PROBE-T1-02 | 1 | H_duration | 89.5523 vs 89.5523 (exact) | 139.4 vs 129.6 | 1714.3 vs 340.9 ms (5.03×) | p90 exactly equal; duration 5× (confound: raw max-trail same direction as duration) |
| S-PROBE-T2-01 | 2 | H_distance | 290.5 vs 60.7 (4.79×) | 388.1 vs 78.8 | 1440.0 vs 1440.0 ms (equal; medians equal) | durations exactly equal; p90 4.8× |
| S-PROBE-T2-02 | 2 | H_distance | 282.8 vs 60.3 (4.69×) | 282.8 vs 106.5 | 666.7 vs 666.7 ms (equal) | durations exactly equal; p90 4.7× (CS 5.0 vs 3.5 confound) |

Why each pair discriminates, plus the full confounder inventory (BPM, CS, SV,
slider counts, circles, raw max-trail, rule status, and — for T1-01 — the
observation that its duration signal is driven by one very long-held slider,
so it also separates p90/max-duration from median-duration readings), is in
the probes JSON. Prediction structure for a future bounded P2 probe run:

- Type 1 → H_duration predicts the long-duration side; H_distance(p90)
  predicts indifference; H_distance(max-tail) predicts the max side.
- Type 2 → H_distance predicts the high-p90 side; H_duration predicts
  indifference.

These are identified probes only. No human answers were or will be filled in
during P1.5, and the pairs are not added to any live collection.

## 4. Follow-duration derivability (task C)

1. **Does the parse layer store slider start/end?** Yes. `HitObject.time_ms`
   is the start; the normalized layer exposes
   `canonical_end_time_ms() = time_ms + slider_total_duration_ms`.
2. **Offline derivable without analyzer changes?** Yes.
   `parse_osu_file` + `normalize` (unchanged) yield per-slider
   `slider_total_duration_ms`; the segment aggregates used here (p90/median/
   max over sliders whose start falls in the canonical 5 s segment) were
   computed for 31,821 segments by `tmp/gap_audit/
   find_counterbalanced_probes_v01.py`. No pipeline code was modified.
3. **Repeat-slider duration semantics.** `span_count = max(1, parsed_slides)`,
   `repeat_count = span_count − 1` (canonical slider semantics v1.0.0);
   single-span duration = `pixel_length / (SliderMultiplier × 100 × SV) ×
   beat_length_ms` (osu formula; contract form `path_distance / velocity`);
   total = single-span × span_count. The renderer moves the ball across every
   span, so total duration is the visual follow time.
4. **Speed-changing mods.** Current scope is NM-only: no mods exist anywhere
   in the pipeline and the presentation always shows NM. If mods ever enter,
   effective duration = raw total ÷ speed multiplier (DT 1.5, HT 0.75), and
   which duration to present must become an explicit contract decision.
5. **Equivalent fields already in provenance?** Yes. Local signal v0.3
   already computes per-row `ls.slider_total_duration_ms` and
   `ls.lazy_travel_time_ms` (tracking time including a late tick before tail
   reordering); the `slider_control_load` proposition consumes map-level
   `slider.duration_ms_p90`. The slider_tracking rule consumes only
   `ls.lazy_travel_distance_cs_normalised` p90 — the time-domain fields exist
   in the same layer but are not rule inputs.
6. **Why does `segment_max` exist but the rule does not consume it?** It is
   carried from the Local source's segment summary via
   `context.provenance["source_segment_max"]` and echoed as a diagnostic. The
   v0.1 rule's declared discriminator consumes only p90 (≥100 positive,
   max==0 negative, else abstain). The only on-record rationale is the rule's
   own failure mode — "segment p90 can hide one extreme slider" — under the
   pilot policy "thresholds are sparse QA discriminators, not learned
   boundaries".
7. **Exact p90 failure mode for one extreme slider.** p90 is the
   90th-percentile row of per-row lazy travel (non-slider rows are zero). An
   extreme slider lies ABOVE p90, so its magnitude does not enter the p90
   value — only whether it shifts the 90% boundary. The rule cannot
   distinguish "one monster slider among short ones" from "uniformly long
   sliders": in B4 the max gap was 188.4 vs 114.2 behind p90 values of
   108.767 vs 108.768.

## 5. B2 dense candidate-mechanism elimination (task D)

Offline statistics were computed for both maps of all 10 dense tasks
(9 directional + 1 ambiguous control), using the project parser only:
1 s-window rate distribution, longest-burst duration and run counts at gap
windows 125/150/200/250/300/400/500/700/1000 ms, beat-relative runs
(gaps ≤ 1.5× local beat length), objects/min, slider span/repeat totals and
map-derived slider tick estimates. Every candidate was scored for directional
agreement with the verified canonical human directions. Summary table
(full data in `docs/HUMAN_CODE_GAP_PROBES_V01.json`,
`tmp/gap_audit/dense_candidates_v01.json`):

| Candidate | Code can observe? | B2 A/B delta | 4/4 B consistent? | Counterexamples | Collinearity | Verdict |
|---|---|---|---|---|---|---|
| current ≤125 ms window (existing features) | yes | rate 3/3, burst 0/0 — zero delta | no | none needed: sees nothing on B2 | — | CONTRADICTED as B2 driver; SUPPORTED as code coverage gap |
| fixed wider windows 150–300 ms | no (offline) | 0 runs both sides | no | zero signal on B2 | map BPM scale | CONTRADICTED as B2 driver |
| fixed windows 400–500 ms | no | A 0 vs B 20 runs (longest 1600 ms) | yes | 263cea7e / 8f60b830 / a933aa2d (faster side wins) | 400 ms = B's half-beat | PLAUSIBLE |
| beat-relative runs ≤1.5× beat | no | A 0 vs B 20 | yes | 8f60b830, a933aa2d (faster side wins); 891c407b (EQUAL despite 26 vs 17) | general density | PLAUSIBLE (best-specified sustained-rhythm candidate) |
| objects/min (general density) | no | 48.6 vs 75.0 → B | yes | 4319b133 (A denser 104.9 vs 72.5, human B — participant filtered single-taps); 891c407b | identical to displayed object count | PLAUSIBLE (7/9 best single fixed candidate) |
| slider repeat/reversal structure | no | repeats 5 vs 24 → B | yes | 6/9 direction-contradicted overall | spans, object frequency; reversal ≠ clicks | WEAK (structural only) |
| map-derived slider ticks (NM) | no | 36 vs 43 → B (marginal) | marginal | 7/9 direction-contradicted overall | slider duration structure | WEAK / CONTRADICTED as general mechanism |
| single-tap vs sustained-stream (perceptual) | no | B: 20 beat-runs vs A 0; A's objects are isolated holds | yes | none found; attested by the 4319b133 note ("大多是单点而非连续点击段") | beat-relative runs (its perceptual reading) | PLAUSIBLE; UNOBSERVABLE by current code |
| alternating/single-tap playstyle | no, absent from map data | n/a | n/a | n/a | n/a | UNOBSERVABLE_WITH_CURRENT_DATA |
| press/release structure | no, needs input data | n/a | n/a | n/a | n/a | UNOBSERVABLE_WITH_CURRENT_DATA (no replay/input exists) |
| visible metadata anchor (counts/BPM) | presentation-level | displayed 174 vs 94 objects; 150 vs 212 BPM | yes | 891c407b (counts favour B, human EQUAL) | = objects/min quantity | PLAUSIBLE confound, not a mechanism |

Composite observation (hypothesis over n=9, not a proof): on pairs where one
side is clearly faster AND denser (peak 1 s rate and object frequency well
separated), humans followed the faster side (263cea7e, 2bd327, 8f60b830,
a933aa2d, d545e72e — all canonical-A, all with the A side dominating the
fast axis); where both sides are slow (peak rate ≤ 4: B2 and 4319b133),
humans followed the side with more sustained beat-relative runs — consistent
with the question wording "连续快速点击" (fast AND continuous). The single
EQUAL task (891c407b) is violated by every candidate individually.

**No winner is declared.** B2 remains `MISSING_OBSERVABLE`: the code observes
none of the viable candidates for this pair; burst-family windows ≤300 ms are
now positively excluded as the B2 driver; the surviving candidates
(sustained beat-relative runs, general density, the attested
single-tap-vs-stream distinction) are correlated with each other and are not
uniquely separated by this evidence.

## 6. What was strengthened

- The slider duration hypothesis gained a falsifiable structure: the corpus
  contains 1.3 M Type-1 and 2.0 M Type-2 counterbalanced pairs, and four
  curated probes now make H_duration vs H_distance testable with bounded
  human effort (P2), including a pair (T1-01) where all distance metrics
  oppose the duration signal.
- The dense gap is no longer "some unknown": the ≤125 ms and all fixed
  ≤300 ms burst windows are excluded for B2; the surviving space is
  sustained-rhythm structure at beat-relative scales plus general density,
  with the participant's own note as direct attestation.
- Follow-duration derivability is now fully documented with field-level
  provenance (normalized layer + Local v0.3 `lazy_travel_time_ms`).

## 7. What was weakened

- "Follow duration" as a causal mechanism: it is now explicitly labelled
  correlational (three pairs, distance and duration not separated).
- "Slider reversal = click pressure": withdrawn as a finding (no input data).
- The idea that any single fixed-window dense metric could be "the" missing
  observable: every candidate has counterexamples; only a composite
  (fast-axis dominance when separated; beat-relative sustained structure when
  slow) fits 8/9 directional dense cases, and that is a hypothesis, not a
  mechanism identification.

## 8. What remains unidentifiable

- The exact per-pair human-used slider observable (needs the P2 probe votes).
- B3's mechanism (2–2 human split; aggregation quirk; no visual artifact).
- Whether the visible metadata anchor (object count/BPM) contributes to the
  dense judgments beyond general density (needs a metadata-hidden probe).
- Anything requiring replay/input data (alternation, press/release
  structure): no such data exists in the project.

## 9. Direct constraints for the P2 problem-definition revision

1. **Do not collapse the slider question onto distance or duration by fiat.**
   Run the four counterbalanced probes first (2 Type-1 + 2 Type-2, presented
   through the existing runner with confidence required). The direction of
   votes on T2-01/T2-02 (equal duration, 4.8× p90) directly decides whether
   the distance axis alone can carry the question; T1-01 decides whether
   duration survives when every distance metric opposes it.
2. **Any reworded slider question must separate distance and duration in
   wording** (e.g. "更远的跟随路径" vs "更久的持续跟随"), because the two
   can be made to oppose in real data; do not write a single question that
   silently picks one axis.
3. **Any new dense observable must be beat-relative, not fixed-millisecond**
   (fixed windows ≤300 ms are excluded for B2; 400 ms coincided with B2's
   half-beat and is BPM-confounded elsewhere). Reversal/repeat structure may
   enter only as a structural cue — never as a click count.
4. **C1/C3 get no additional ordinary A/B votes**; they remain multi-axis
   tradeoffs to be resolved by wording, not by majority. **B3 is retained as
   a GENUINE HUMAN DISAGREEMENT / unresolved boundary candidate** (2–2 across
   source + exact-repeat control); only a P4-style repeat/inversion design may
   revisit it.
5. **Follow duration is cheaply available offline** (this phase proved it for
   31,821 segments without analyzer changes). If P2 evidence supports
   H_duration, P3 may add it as a rule input with provenance — but only after
   the probe votes exist, not on the current correlation.

## Working-tree impact

New files: this report, `docs/HUMAN_CODE_GAP_PROBES_V01.json`, and ignored
`tmp/gap_audit/` additions (`find_counterbalanced_probes_v01.py`,
`dense_candidates_v01.py`, `amend_disposition_v01.py` + intermediate JSON).
P1 documents received only the marked `AMENDMENT (P1.5)` wording corrections.
No snapshot, evidence, pipeline or historical document was modified.
