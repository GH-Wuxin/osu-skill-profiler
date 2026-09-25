# Measurement Contract: Unified Star Scale and Player Skill Rating v0.1

**Status:** CONTRACT BEFORE IMPLEMENTATION
**Version:** `measurement-contract-unified-star-player-v0.1`
**Scope:** Skill Profiler only. The v0.40 release remains frozen.

This document defines what the two measurements are allowed to mean. It does
not choose formulas, fit weights, or admit a production algorithm.

## 1. Measurement objects

The system keeps three different objects separate:

| Object | Unit of observation | Meaning |
|---|---|---|
| Map Demand | one beatmap, one ruleset/mod context, one axis | The demand evidenced by the map for that axis. It is map-side and contains no player input. |
| Player Skill Rating | one player, one axis, one declared time/source window | The player's estimated ability on the same axis demand scale, inferred from multiple performances. It is not one score or one replay result. |
| ppy total SR | one beatmap's external aggregate | A ppy reference signal for population context and sanity checks. It is not a per-axis label and not a player ability rating. |

## 2. Meaning of `X★`

`X★` is a value on a **versioned, ppy-referenced demand-equivalence scale**
for one osu!standard mod context.

It means:

- the axis-specific demand or player capability has been placed on the same
  declared reference ruler as the other admitted axes;
- the value is comparable only within the same scale version, ruleset, mod
  context, and provenance contract;
- equal numbers across axes mean equal calibrated positions on the reference
  demand ruler, not equal cursor distance, tapping rate, cognitive load, or
  physical workload.

It does **not** mean:

- the official osu! star rating;
- ppy total SR;
- pp, score, accuracy, pass probability, or a probability of success;
- a weighted sum of the nine axes;
- evidence that one map or one player is globally harder or better in every
  skill dimension.

The raw physical/local value remains in every result. The common-star value is
an additional calibrated representation and must never erase the raw signal.

## 3. When axes may share the ruler

Different axes may use the same star unit only when each axis has:

1. a declared raw demand signal and unit;
2. a broad, versioned calibration corpus rather than a single fixture;
3. an axis-specific monotone mapping into the common reference ruler;
4. held-out evidence that the mapping preserves within-axis ordering;
5. coverage across the relevant demand range and map families;
6. provenance showing the corpus, ppy reference population for that exact mod
   context, ruleset, mods, and calibration version.

The shared unit does not authorize a shared formula. Each axis keeps its own
mechanism and evidence. If an axis lacks the required evidence, its common-star
representation is not admitted and its raw value remains available separately.

## 4. Relationship between Map Demand and Player Skill Rating

Map Demand describes the demand presented by a map. Player Skill Rating
describes a player's demonstrated capacity relative to that demand. They may be
compared because they use the same admitted axis ruler, but they are never added,
averaged, or substituted for one another.

The player layer must be based on multiple maps, multiple performances, and a
declared time/source window. A single high score, a single replay, or a single
fixture can be evidence, but cannot establish a player's Skill Rating.

The primary player output is an axis vector with evidence metadata. A scalar
overall player rating is a separate measurement and is not emitted until a
cross-axis aggregation contract has independent evidence.

## 5. Role of ppy total SR

ppy total SR may be used for:

- defining and stratifying the reference population;
- providing context-specific ppy reference star distributions for each non-FL
  mod context;
- checking whether a map corpus spans a useful range;
- reporting external context beside the profiler result;
- testing broad monotonic sanity where the comparison is appropriate.

ppy total SR may not be used as:

- ground truth for every axis;
- a direct target for each axis;
- a replacement for axis-specific evidence;
- a hidden additive or multiplicative weight;
- proof that a single-axis specialist must have the same total SR.

The contract explicitly permits a map or player to be extremely strong in one
axis while having a lower total SR or weaker evidence in other axes.

## 6. Player Skill Rating evidence

The player layer stores raw evidence before interpretation. Each evidence item
must identify the player, map, mode, mods, timestamp, source, score/replay
identity, and the map-demand version used for the join.

Source distributions stay separate until their own normalization is complete.
BP/top-play, recent plays, tournament results, and replay traces must not be
concatenated as if they were one sampling distribution.

Player Skill Rating requires evidence from multiple maps and multiple time
points. A multi-player corpus is required before claiming population-level
calibration. A score's accuracy, combo, misses, and pp are performance evidence;
they are not themselves the player's Skill Rating.

## 7. `UNKNOWN` versus low ability

`UNKNOWN` means the evidence cannot distinguish the player's ability from the
possible alternatives. It is used for missing, too sparse, incompatible,
unmatched, or contradictory evidence.

`LOW` is allowed only when there is enough valid evidence on the declared scale
to support a low-ability conclusion. Missing data must never be converted to a
low rating, zero, or a penalty.

The same distinction applies to a map axis: absent evidence is not a zero-demand
map.

## 8. Required output envelope

Every future admitted player-axis result must expose at least:

```json
{
  "rating": 0.0,
  "uncertainty": {"lower": 0.0, "upper": 0.0},
  "evidence_count": 0,
  "coverage": 0.0,
  "status": "ADMITTED | CANDIDATE | UNKNOWN",
  "scale_id": "...",
  "source_window": {"from": "...", "to": "..."},
  "evidence": []
}
```

The exact uncertainty construction is deliberately not fixed here. It must be
declared with the implementation and cannot be replaced by a confidence label
that hides sample size or coverage.

## 9. Version and freeze boundary

- `FORMAL_MAP_DEMAND_V040` and all v0.40 numeric outputs remain unchanged.
- The future common-star layer gets an independent version and calibration ID.
- Each non-FL mod context gets its own calibration artifact; contexts are never
  mixed into one ruler. FL remains score evidence but is outside the current
  nine-axis demand contract.
- The future player layer gets an independent version and evidence schema.
- No new layer may silently rewrite `demand_star_equivalent` in v0.40.
- Admission into a future formal release requires a separate report for map
  calibration and player calibration.

## 10. Required next step

The next step is an evidence audit against this contract: verify which corpus,
ppy reference fields, player evidence fields, and time/source joins already
exist. Only after that audit identifies sufficient data may the implementation
choose a mapping or estimation method.
