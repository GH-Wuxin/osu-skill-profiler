# Tournament Data Architecture V0

Status: design proposal only. No implementation.

---

## 1. Design Principles

1. Core profiler stays `.osu → signals → representation`. No dependency on QQ/WuxinBot/tournament service/replay service/tosu.
2. All external sources are optional adapters behind data-source-independent interfaces.
3. RAW SOURCE DATA and NORMALISED ANALYTIC DATA are separate layers, never mixed in one table/object.
4. Provenance and confidence are first-class fields on every record.
5. Nothing derived from match-name heuristics may be labelled VERIFIED.

---

## 2. Canonical Schemas (V0)

### 2.1 TournamentRecord

| Field | Type | Notes |
|---|---|---|
| tournament_id | string | Stable id from index source (e.g. `owc-2025`) |
| name | string | Display name |
| source | enum | `manual`, `community_index`, `organizer_export`, `heuristic` |
| source_url | string | Where this record came from |
| stage | string | e.g. Qualifiers / Group Stage / RO16 / Finals |
| round | string | e.g. Week 1 / Losers Round 2 |
| provenance | object | fetch/entry provenance |
| confidence | float 0..1 | 1.0 only for verified entries |
| verification_status | enum | `VERIFIED` / `HEURISTIC` / `UNVERIFIED` |

### 2.2 MatchRecord

| Field | Type | Notes |
|---|---|---|
| match_id | int | osu! match id (v2 `Match.id`) |
| tournament_id | string | FK to TournamentRecord |
| name | string | Lobby name (informational only) |
| start_time / end_time | datetime / nullable | null end = unfinished at fetch time |
| teams | list | User/team snapshot, source-specific |
| source | enum | adapter that produced it |
| warmup_count | int / null | Only from verified index or explicit metadata; never inferred by default |
| provenance / confidence | as above | |

### 2.3 GameRecord

| Field | Type | Notes |
|---|---|---|
| game_id | int | v2 `MatchGame.id` |
| match_id | int | FK |
| beatmap_id | int | survives deleted beatmaps |
| beatmapset_id | int / null | from local manifest join when available |
| scoring_type | enum | score / accuracy / combo / scorev2 |
| team_type | enum | head-to-head / tag-coop / team-vs / tag-team-vs |
| mods | list | typed where available; legacy bitmask otherwise |
| pool_slot | string / null | from verified tournament index only |
| warmup | bool / null | null = unknown; never heuristic-guess as fact |
| aborted | bool / null | heuristic candidate only; see validation |
| valid_for_analysis | bool | computed gate |
| invalid_reason | list | e.g. no end_time, zero scores, no players, aborted |
| start_time / end_time | datetime / nullable | |
| provenance | object | endpoint, raw ref, parser version |

### 2.4 TournamentScoreRecord

| Field | Type | Notes |
|---|---|---|
| score_id | string / null | v2 score id when available |
| game_id | int | FK |
| user_id | int | |
| score | int | RAW ScoreV2 when scoring_type=scorev2; otherwise source score |
| classic_total_score | int / null | v2 classic field |
| accuracy | float | 0..100 (rosu-v2 convention) or 0..1 (v2 payload) — store canonical 0..1 with note |
| max_combo | int | |
| hit_statistics | object | 300/100/50/geki/katu/miss |
| mods | list | per-score mods |
| team | enum / null | blue/red/none; null when not applicable |
| slot | int | |
| passed | bool | |
| score_version | enum | `scorev2` / `scorev1` / `accuracy` / `combo` / `unknown` |
| provenance | object | endpoint, raw JSON ref, fetch time |

Layer separation:

- RAW SOURCE DATA = exactly what the adapter returned (kept immutable, ref-addressable).
- NORMALISED ANALYTIC DATA = canonical records above after validation; all derived/relative metrics (percentiles, z-scores) live in a separate analytic table and never overwrite raw values.

---

## 3. Adapter Boundaries

Each adapter exposes only the canonical records; internal source shapes stay private.

```text
data_sources/
  osu_api/        → MatchRecord, GameRecord, TournamentScoreRecord (raw)
  tournament/     → TournamentRecord + Tournament Match Index entries
  replay/         → ReplayEventTimeline (see player evidence doc)
  live/           → LiveMatchState (tosu adapter boundary only)
```

Interfaces (conceptual, not code):

- `fetch_match(match_id) -> RawMatch` — paging over events, 401/404/transient handling.
- `resolve_tournament(match_id) -> TournamentRef | None` — via index only.
- `fetch_beatmap_join(game) -> LocalMapRef | None` — join via local manifest by beatmap_id.
- `fetch_replay(score_id) -> Replay | None` — availability limited; never assume.
- `subscribe_live(instance) -> LiveStateStream` — optional; no core coupling.

Retry/robustness rules: transient API errors must not delete persisted listeners/index entries; only definitive 404/401 should mark absence.

---

## 4. Tournament Match Index

Purpose: the missing middle layer between "user id" and "tournament ScoreV2 history".

Entry schema:

| Field | Type | Notes |
|---|---|---|
| tournament_id | string | |
| stage / round | string | |
| match_id | int | |
| teams / users | list | |
| source | enum | `manual`, `community_index`, `organizer_export`, `heuristic` |
| source_url | string | |
| confidence | float 0..1 | |
| verification_status | enum | `VERIFIED` / `HEURISTIC` / `UNVERIFIED` |
| verified_by | string / null | person/process |
| warmup_known | bool | whether warmup metadata exists for this match |

Sources ranked by trust:

1. Tournament organizer export (VERIFIED when signed/curated).
2. Community-maintained JSON in a Git repository (VERIFIED after review; PR-based).
3. Manual curation (VERIFIED per-entry by maintainer).
4. Automatic heuristic discovery (always HEURISTIC; never promoted silently).

Rules:

- A match name pattern is never ground truth.
- Heuristic entries must store the heuristic rule + matched name + match id.
- Any downstream analysis consuming the index must filter by verification_status and confidence thresholds.

---

## 5. ScoreV2 Performance Normalisation Candidates

All candidates are REFERENCE CANDIDATES, not a frozen rating.

| Candidate | Definition | Strengths | Weaknesses |
|---|---|---|---|
| Same-game percentile | rank of player score within that game | lobby-context free; robust to map/mods | coarse; ties; small lobbies |
| Score / lobby median | ratio to median score | simple, interpretable | median unstable in tiny lobbies; ignores difficulty |
| z-score within game | (score - mean)/std | standardised | breaks on near-constant scores; sensitive to failed players |
| Ratio to best | score / game best | intuitive | over-penalises everyone when one outlier exists |
| Team-relative | score vs teammate(s)/opponents in team games | captures role in team-vs | depends on team formation quality |
| Expected-vs-observed | observed ScoreV2 vs model-predicted score for that beatmap+mods+player | most skill-informative | requires a prediction model (future; not now) |
| Accuracy-normalised | combine accuracy & hit distribution with score | reduces score-only noise | still map-dependent |
| Pass/fail survival | survived vs failed at given difficulty | strong signal for pressure/fail behaviour | sample-dependent; fails are rare in top lobbies |

Why raw ScoreV2 cannot be averaged across maps:

- Map difficulty: same absolute score ceiling and strain distribution differ per beatmap.
- Skill composition: a map may demand aim, speed, or reading differently.
- Mods: score is mod-adjusted; HR/HD/NM cannot be compared directly.
- Lobby strength: score relative to lobby is a property of the lobby, not only the player.
- Team size/type: team-vs vs head-to-head vs tag modes change scoring semantics.
- Score ceiling: object count, slider count, spinner length bound achievable score.
- Fail behaviour: failed players' scores are truncated or absent, biasing aggregates.
- Warmups and abnormal games: non-competitive or aborted games distort any mean.

Recommended V0 stance: primary analytic metric = within-game normalisation (percentile or z-score) gated by `valid_for_analysis`, with expected-vs-observed deferred until a local-signal-based score model exists. Never use cross-game raw averages as a player rating.

---

## 6. Provenance Model

Every record carries:

- `source` (adapter/endpoint id)
- `source_type` (official_api_v2, official_api_v1, webpage_json, community_index, live_ws, replay_file)
- `fetched_at` / `recorded_at`
- `endpoint` / `file_path`
- `raw_ref` (immutable raw payload reference)
- `parser_version`
- `verification` (VERIFIED / HEURISTIC / UNVERIFIED)
- `confidence` (0..1)

Raw payloads are stored once, content-addressed; canonical records reference them rather than duplicating mutable fields.

---

## 7. Validation Model

Schema-level:
- Enums validated (scoring_type, team_type, event types).
- `end_time` required for final games; null allowed only for in-progress.
- At least one score per completed game (else `valid_for_analysis=false`).

Semantic invariants:
- Team consistency within a game where team_type is team-vs.
- Duplicate score detection per (game_id, user_id).
- Aborted-game heuristic (no end_time + zero/partial scores + subsequent disband) → `aborted=HEURISTIC`, never `VERIFIED`.
- Warmup values only from verified index metadata; otherwise `null`.

Cross-source checks:
- Same match from two sources must produce identical game/score sets; mismatches are validation errors, not "merges".

---

## 8. Data Integrity / Leakage Grouping Keys

For future ML, group by:

| Risk | Grouping key |
|---|---|
| Same match leakage | `match_id` |
| Same tournament leakage | `tournament_id` |
| Same beatmapset leakage | `beatmapset_id` (fallback: local_set_group from manifest) |
| Player identity leakage | stable `user_id`; never username string |
| Tournament era leakage | `tournament_id` + season/year from index |
| Repeated map across tournaments | `beatmap_id` × (tournament, date) |
| Warmup leakage | `warmup=true` → exclude from training candidates |
| Rematch / aborted duplication | game status + dedupe key `(match_id, game_id, user_id)`; aborted games excluded |

Rule: any training split must be on the highest group (tournament) when tournament identity exists; otherwise match-level split with explicit caveat.

---

## 9. Module Boundaries (future, not implemented)

```text
osu_skill_profiler/
  core/            # .osu → signals → representation (no external deps)
  data_sources/    # optional adapters: osu_api, tournament, replay, live
  evidence/        # normalisation + evidence fusion (future)
```

The core package must build and test without any adapter installed.

