# Player Evidence Model V0

Status: design proposal only. No model implementation, no training.

---

## 1. Five Evidence Sources Are Not the Same Distribution

| Source | Represents | Strengths | Biases | Granularity | Availability |
|---|---|---|---|---|---|
| BP Profile | Historical successful peak / selected-success distribution | Easy to fetch, stable, standardised by PP | Selection bias (best scores only), farm bias, PP-system bias | Map-level, best-N only | High (public API) |
| Recent Profile | Current activity / current training distribution | Current, reflects recent form | Failed plays, warmups, random play, retry behaviour | Play-level recent window | High |
| Tournament Profile | Competitive performance under a fixed map pool | Highly informative, pressure + pool context | Hard indexing, uneven sample size, opponent/pool bias | Game-level, within-match context | Low (requires Tournament Match Index) |
| Replay Profile | Fine-grained error localisation | Segment-level evidence, actual cursor/timing | Replay availability, per-mode parsing | Frame/object-level | Low |
| Live Profile | Current match state | Real-time, caster/overlay use | Local telemetry dependency, no historical value | Real-time state | Local only (tosu/gosumemory) |

Core rule: these distributions have different sampling, selection and error structure. They cannot be averaged, concatenated or unioned into a single score. Each must be normalised inside its own source context before any cross-source reasoning.

---

## 2. Evidence Layer Architecture

```text
Player Evidence Layer
        ↓
Source-specific normalization
        ↓
Skill-space evidence
        ↓
Player Skill Profile
```

### 2.1 Player Evidence Layer

Collects and stores raw evidence per source, with provenance (source, fetch time, endpoint, raw ref, parser version). No interpretation happens here.

- BP: top plays (map, mods, acc, pp, date).
- Recent: recent plays incl. failures (map, mods, acc, score, date).
- Tournament: match/game/score records gated by `valid_for_analysis` and index verification.
- Replay: parsed replay frames + judgement timeline.
- Live: streamed state snapshots (short-lived).

### 2.2 Source-Specific Normalization

Each source normalises only within itself:

- BP: selected-success distribution; farm/selection bias noted, no "correction" claimed.
- Recent: filter warmups/random/retries where identifiable; current activity window.
- Tournament: within-game normalisation (same-game percentile/z-score), pass/fail survival, lobby-strength context, mods, scoring_type gating. Verified-index matches only for formal conclusions.
- Replay: map local-signal timeline × replay event timeline → failure-by-skill evidence (miss/50/100/sliderbreak localisation, UR, cursor trajectory).
- Live: real-time state only; never persisted as historical ground truth.

### 2.3 Skill-Space Evidence

Normalised outputs are projected into a shared evidence vocabulary (e.g. "performs relative to lobby at X", "failed density at speed sections", "sustained accuracy under HD"), without collapsing distributions.

### 2.4 Player Skill Profile

Aggregation layer that combines evidence with explicit weights/uncertainty (future model). No concrete model is defined or implemented in this phase.

---

## 3. Tournament Evidence Specifics

- Only `valid_for_analysis=true` games enter evidence.
- Only VERIFIED (or explicitly confidence-gated) index entries support formal tournament claims.
- Primary metrics: same-game percentile, pass/fail survival, lobby-relative performance; never cross-map raw averages.
- Sample-size and opponent-strength context must be attached to every tournament evidence tuple.

---

## 4. Replay × Local Signal Timeline

Design direction (not implemented):

```text
Replay Event Timeline          Map Local Signal Timeline
  HitObjectJudgement      ×      per-object / per-segment features
  CheckpointJudgement     ×      slider breakpoints
  UnnecessaryClick        ×      density / patterning
  cursor trajectory       ×      spatial demand
  UR / timing             ×      rhythm complexity
        ↓
Failure-by-skill evidence
```

This is where replay data genuinely exceeds ScoreV2 aggregates: it localises *which* skill dimension failed (aim vs rhythm vs slider control vs reading), not just that a score was lower.

---

## 5. Live Evidence Boundary

Future optional adapter (tosu):

```text
tosu (localhost:24050, WS v2)
  ↓
live match state (current beatmap, time, score, leaderboard, tourney state)
  ↓
osu-skill-profiler segment timeline
  ↓
caster assistant / overlay
```

Constraints: adapter-only, no core dependency; tourney/result fields on lazer marked "not tested yet" upstream; stable/lazer parity UNKNOWN.

---

## 6. Non-Goals (this document)

- No fusion algorithm is frozen.
- No model is implemented.
- No cross-source score is defined.
- No WuxinBot / QQ integration.

