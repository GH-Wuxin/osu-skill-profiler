# Tournament & Player Data Ecosystem Audit

Audit date: 2026-08-11
Scope: osu! multiplayer match ingestion, ScoreV2 retrieval, tournament indexing, player normalisation, live telemetry, replay analysis, API access, overlay tooling.
Evidence standard: source-level verification (cloned repos at pinned HEAD commits), official API documentation, osu-web/DeepWiki references. Anything not source-verified is explicitly marked UNKNOWN.

---

## 1. Official API Capability Matrix

Sources: osu! API v2 documentation (osu.ppy.sh/docs), ppy/osu-web (AGPL-3.0-or-later), rosu-v2 0.9.0 source (docs.rs), ossapi v2 models (cloned HEAD), DeepWiki Multiplayer Scoring notes.

Legend: DIRECT = returned in the official payload; DERIVED = computable with additional logic/endpoints; UNAVAILABLE = not provided by any public endpoint; AMBIGUOUS = present but not semantically reliable.

| Capability | Status | Evidence / Notes |
|---|---|---|
| Match metadata (id, name, start/end) | DIRECT | `GET /matches/{id}` → `Match { id, name, start_time, end_time }`; `end_time` null while in progress (ossapi `Match` model, v2 docs). |
| Game metadata (game_id, start/end) | DIRECT | `MatchGame { id, start_time, end_time }`; `end_time` null for in-progress games. |
| BeatmapID | DIRECT | `MatchGame.beatmap_id` always present; `beatmap` object can be null for deleted beatmaps (example comment in ossapi models). |
| Scoring type | DIRECT | `MatchGame.scoring_type` (score / accuracy / combo / scorev2). |
| ScoreV2 raw score | DIRECT | `MatchScore.score` (v1) / generic `Score.total_score` + `classic_total_score` (v2); meaningful when `scoring_type == scorev2`. |
| Mods | DIRECT | v2 `MatchGame.mods` (typed mods); older matches expose legacy bitmask via v1 (`enabled_mods`). |
| Team | DIRECT | `MatchScore.team` (v2 `Team`); legacy v1 integer team; rosu-v2 `MatchTeam { Blue, Red, None }`. |
| Slot | DIRECT | `MatchScore.slot` (v1/v2). |
| Pass/fail | DIRECT | v1 `MatchScore.pass`; v2 `Score.passed`. |
| Accuracy | DIRECT | v2 `Score.accuracy` (0..100 in rosu-v2); v1 derived from hit counts. |
| Max combo | DIRECT | v1 `maxcombo`; v2 `max_combo`. |
| Hit statistics | DIRECT | v1 count300/100/50/geki/katu/miss; v2 `Score.statistics`. |
| User ID | DIRECT | `MatchScore.user_id`; match response also includes `users` map. |
| Match history (events) | DIRECT | `MatchEvent { id, timestamp, user_id, detail, game }`; events: player-joined/left/kicked, host-changed, match-created/disbanded, other(Game). |
| Aborted games | AMBIGUOUS | No official field. A game may appear with partial/zero scores and no `end_time`, but this is not an explicit abort flag; heuristic only. |
| Warmup information | UNAVAILABLE | No official field; Bathbot-style "skip first N games" is a user-supplied heuristic. |
| Match name | DIRECT | `Match.name`. |
| Tournament identity / stage / round / pool slot / referee / official-vs-casual | UNAVAILABLE | Not in any public match endpoint. Only heuristic inference from lobby name (forbidden as ground truth). |
| Ongoing match polling | DIRECT | Poll `GET /matches/{id}` with `after`/`before`; events are capped at 100 per page (rosu-v2 `get_next`/`get_previous` contract). |
| Pagination by event id | DIRECT | `after`/`before` filter match event ids; rosu-v2 documents that the boundary event value itself is excluded. |
| List current lobbies | DIRECT but limited | `GET /matches` returns current matches; known upstream issue: `cursor_string` does not work on `/matches` (ppy/osu-web #11348, 2024-07-20); `?active=` filter proposed in PR #12418 (2025-10-01, status UNKNOWN). |
| Lazer rooms (`/rooms`) | DIRECT | Rooms, playlist items, scores, leaderboard; response schema versioned (20240529 filters daily_challenge); `requires_user=true` for list. |
| Rate limit | DIRECT constraint | Client credentials: 60 requests/min (official docs). |

### A. Given a match ID, how complete is ScoreV2 data?

High completeness for completed games:

- Match + all games + per-player scores, including raw ScoreV2 (`scoring_type=scorev2`), team, slot, pass/fail, accuracy, max combo, full hit statistics, mods, user IDs, beatmap IDs, game start/end.
- Private matches return HTTP 401 (Bathbot treats this explicitly).
- Deleted beatmaps still expose `beatmap_id`; the beatmap object is null.
- Pagination: only 100 events per page; clients must page with `after`/`before` (Bathbot pages up to 5 times / 500 events for match cost).

Missing from official data: explicit warmup flags, abort flags, tournament identity, pool slot, referee metadata, and official/casual distinction. These are all heuristic or external-index territory.

### B. Given a user ID, can we get "all tournament ScoreV2 history" directly?

No. There is no public endpoint that enumerates a user's tournament matches, or that tags matches as tournament vs casual.

Missing middle layer: a **Tournament Match Index** (see architecture doc). It must be built from curated/community/organizer sources and separately marked VERIFIED vs HEURISTIC. Match-name heuristics alone must never be promoted to verified tournament ground truth.

---

## 2. Repositories Audited

| Repository | Audited commit | Audit date | Licence | Language/Runtime | Maintenance |
|---|---|---|---|---|---|
| MaxOhn/Bathbot | `1ab89046453517a8380a35953900455551b1026a` (2026-07-18, refactor: hide some stats for modes) | 2026-08-11 | ISC (LICENSE, not AGPL as some listings claim) | Rust (Discord bot; rosu-v2, sqlx, redis, axum) | Active |
| Liam-DeVoe/ossapi | `73ac46bdc003f285a54c1cd408fd7396e661bb2a` (2026-07-31, bump version) | 2026-08-11 | AGPL-3.0 (LICENSE) | Python (sync + async) | Active |
| tosuapp/tosu | `4a76b60daef9bf1d18dda20226921dbd6b80d091` (2026-08-07) | 2026-08-11 | LGPL-3.0 (LICENSE); package.json metadata says GPL-3.0 — metadata discrepancy | TypeScript (client + server) | Active |
| abstrakt8/rewind | `d9d24182c893c192aba207ce088f55b543efec9e` (2025-02-22, bump version 0.2.2) | 2026-08-11 | MIT (LICENSE.md, package.json) | TypeScript (Electron app, nx monorepo) | Low/limited (last push 2025-02) |
| kionell/osu-parsers | `4e6f37b9cf5c3d3ccfc20d1b3e0fe107ea5466a5` (2025-06-14, 4.2.0-beta.0) | 2026-08-11 | MIT (LICENSE) | TypeScript (browser + node builds) | Moderate |
| jramseygreen/osu_bot_framework-v3 | `09185a0e9e9e7155bdbb00f6dc602475a0f905fa` (2022-03-02, README update) | 2026-08-11 | MIT (LICENSE present in clone) | Python (IRC/bancho) | Dead (last commit 2022) |

Addendum (not cloned; verified via docs.rs/Cargo.toml):

| Repository | Version | Licence | Notes |
|---|---|---|---|
| MaxOhn/rosu-v2 | 0.9.0 (docs.rs; `lazer` branch newer) | MIT (Cargo.toml) | Rust wrapper used by Bathbot; exact commit of current release UNKNOWN; match semantics verified via docs.rs source pages. |

---

## 3. Per-Project Findings

### 3.1 MaxOhn/Bathbot

Relevant files:
- `bathbot/src/commands/osu/match_costs.rs` — `/matchcost` (`/mc`) pipeline and formula.
- `bathbot/src/active/impls/match_costs.rs` — paginated result presentation.
- `bathbot/src/core/context/matchlive.rs` — `/matchlive` background loop.
- `bathbot/src/matchlive/{mod,types}.rs` — live tracking types.

Match ingestion (matchcost):
- `retrieve_previous()` pages at most 5 previous-event pages (~500 events) via rosu-v2 `get_previous()`.
- `drain_games()` + filter `game.end_time.is_some()` (completed games only).
- User-specified `warmups` skips the first N games; `skip_last` truncates the tail; scores with `score == 0` are dropped; optional EZ score multiplier.
- 401 → "private match"; NotFound → "no match"; other errors surfaced.

Match cost algorithm (algorithm reference, not ground truth):
- Per game per user: `performance_cost = score / game score_avg`.
- Per user: average performance cost + `FLAT_BONUS = 0.5`.
- Participation factor: `1.5 ^ ((played/games-1) ^ 0.6)`.
- Mods bonus: `1 + 0.02 * (distinct mod combinations - 2)` when > 2 combinations.
- Tiebreaker bonus: if match finished, games > 4, team win diff == 1, and user played the last game: `min(0.5, 0.25 * last performance cost)`.
- Team wins: per game, team with higher total score wins; head-to-head with exactly 2 players is artificially re-assigned into blue/red.
- Team of a user: first team observed is stored.

Matchlive:
- Polls `get_next()` every 10 s; on request error logs and continues (does not drop tracking).
- Removes tracking once `end_time.is_some()`.
- Per channel max 3 tracked matches; reboot sends "tracking aborted" message and clears state.

Classification: ALGORITHM_REFERENCE (formula), DATA_PIPELINE_REFERENCE (paging/filtering), REUSE_CANDIDATE for the match-fetching/paging pattern only (Rust-specific, ISC licence).

### 3.2 Liam-DeVoe/ossapi

Relevant files:
- `ossapi/ossapi.py` — legacy v1 `get_match(match_id)` (`mp` param), `MatchInfo/Match/MatchGame/MatchScore` models.
- `ossapi/ossapiv2.py` / `ossapiv2_async.py` — v2 `matches()`, `match(after_id, before_id, limit)`, `multiplayer_scores()`, `room()`, `room_leaderboard()`, `rooms()`.
- `ossapi/models.py` — `MatchResponse`, `Match`, `MatchGame`, `MatchEvent`, `MultiplayerScore`, `Room`, generic `Score`.

Model highlights:
- `MatchGame.beatmap` nullable (deleted beatmaps), `MatchGame.mods` typed, `MatchGame.scores` uses generic `Score` (classic_total_score, passed, statistics, legacy_score_id, ruleset_id, has_replay...).
- `MatchEventType` matches official event types; `ScoringType`/`TeamType` enums documented against osu-web source lines.
- Sync (`Ossapi`) and async (`OssapiAsync`) clients; scope-annotated requests.

Licence analysis: AGPL-3.0. For a distributed/commercial profiler this is the critical constraint — an AGPL dependency drags network-service obligations and complicates internal API client reuse. Recommend not making it a mandatory dependency.

### 3.3 tosuapp/tosu

Relevant files:
- `packages/tosu/src/states/tourney.ts` — tournament overlay state (ipcState, left/right stars, bestOf, score visibility, team names/scores, chat, user id/name/country/pp/rank).
- `packages/tosu/src/states/resultScreen.ts` — result state (onlineId, playerName, mods, mode, maxCombo, score, accuracy, statistics, maximumStatistics, grade, date, pp, fcPP).
- `packages/server/router/{index,socket,v1,v2}.ts` — HTTP + WebSocket endpoints.
- `packages/common/utils/config.ts` — default bind `127.0.0.1:24050`.

Transport: WebSocket `/ws` (v1), `/tokens` (SC), `/websocket/v2`, `/websocket/v2/precise`, `/websocket/commands`; external requests blocked by default (isRequestAllowed). v2 payload includes gameplay, resultScreen, leaderboard (visible + local scores).

Stable vs lazer: separate memory readers (`memory/stable.ts`, `memory/lazer.ts`); tourney data documented upstream as "not tested yet".

Licence: LGPL-3.0 LICENSE file; package.json metadata says GPL-3.0 (discrepancy noted). As a live telemetry source, it is an OPTIONAL_ADAPTER / UI_REFERENCE candidate — the core profiler must not depend on it.

### 3.4 abstrakt8/rewind

Relevant files:
- `libs/osu/core/src/replays/RawReplayData.ts` — .osr fields + legacy mod bitmask.
- `libs/osu/core/src/replays/ReplayParser.ts` — `parseReplayFramesFromRaw`: frame splitting, coordinate overflow guard, stable seed frames `(256,-500)` skipped, negative-time frames skipped, same-time frames merged.
- `libs/osu/core/src/gameplay/GameplayAnalysisEvent.ts` — HitObjectJudgement / CheckpointJudgement / UnnecessaryClick events.
- `apps/desktop/frontend/src/app/services/renderers/components/hud/ForegroundHUDPreparer.ts` — UR = standard deviation of hit errors × 10.
- `libs/osu-local/gosumemory/src/gosumemory.ts` — live gosumemory adapter (unstableRate).

Replay decode uses `node-osr` (types vendored under `libs/@types/node-osr`). Lazer replay seed frame noted but not yet handled.

Classification: REFERENCE_IMPLEMENTATION / ALGORITHM_REFERENCE (MIT). Offers the clearest existing example of replay-timeline × hit-object judgement evidence.

### 3.5 kionell/osu-parsers

Relevant files:
- `src/core/Decoders/{BeatmapDecoder,ScoreDecoder,StoryboardDecoder}.ts` and `Handlers/` subdecoders.
- `src/core/Encoders/` — encode/decode round trip.
- `src/core/Utils/LZMA.ts` — replay LZMA decoding.
- Node + browser builds; four rulesets supported; documented as based on osu!lazer source.

Classification: TEST_ORACLE / REFERENCE_ONLY (MIT). Best use: independent cross-validation of our parser on shared fixtures, or future TS-side replay/beatmap decoding; not a required runtime dependency.

### 3.6 jramseygreen/osu_bot_framework-v3

Relevant files:
- `game.py` — `fetch_match_history()` GETs `https://osu.ppy.sh/community/matches/{id}` with `Accept: application/json` (legacy match JSON, not v2 API); `get_match_data()` finds the latest event with `game`; `__fetch_scores()` maps `score["match"]["slot"]` / `score["match"]["team"]`; callbacks `on_match_start/finish/abort`; `!mp` IRC room management; scoring type parsed from `!mp settings`.
- `framework.py` — room creation (`make_room`) and IRC lifecycle.

Historical ingestion assumptions: IRC-hosted lobbies with public match history; webpage JSON shape; no v2 API usage; no auth/refresh token handling. Last commit 2022; MIT licence but effectively dead.

Classification: DO_NOT_USE for new code; the only reusable idea is the legacy webpage-JSON-to-canonical-scores mapping concept, which ossapi/rosu-v2 already model better.

---

## 4. Missing Capabilities & Risks

- No official tournament identity, stage/round, pool slot, warmup, referee, or official-vs-casual metadata.
- Aborted games are not explicitly flagged; heuristic detection (no end_time, zero/partial scores, abrupt disband) is required and must be conservative.
- Historical mods on old games: legacy bitmask only (v1); typed mods only in newer v2 responses.
- `/matches` list is not a tournament discovery API (cursor issue + no filters); lazer `/rooms` covers playlists/realtime but not legacy tournaments.
- Deleted beatmaps: beatmap_id survives, but any join to map features requires the profiler's local corpus/manifest.
- Private matches: 401; cannot be recovered.
- ScoreV2 cross-map comparability is fundamentally limited (see architecture doc §5).
- Heuristic tournament detection from match names is fragile and must remain tagged HEURISTIC.

---

## 5. Decision Matrix

Decision categories: DIRECT_DEPENDENCY / OPTIONAL_DEPENDENCY / REFERENCE_IMPLEMENTATION / ALGORITHM_REFERENCE / TEST_ORACLE / UI_REFERENCE / DO_NOT_USE.

| Project | Decision | Reason | Licence impact | Maintenance impact | Integration cost | Value |
|---|---|---|---|---|---|---|
| MaxOhn/Bathbot | ALGORITHM_REFERENCE + DATA_PIPELINE_REFERENCE | Match cost formula, paging/filtering and live-polling patterns are directly useful; Rust/Discord code not portable | ISC, permissive | Active upstream, but we don't depend on it | Low (read source, port concepts) | High for ScoreV2 normalisation and polling semantics |
| Liam-DeVoe/ossapi | REFERENCE_IMPLEMENTATION (not mandatory dependency) | Excellent model/endpoint reference for a minimal internal client; AGPL complicates mandatory dependency | AGPL-3.0 — avoid linking as required dep in distributed profiler | Active, but licensing forces a fork/internals decision | Medium if vendored/reimplemented | High as contract reference; low as direct dep |
| tosuapp/tosu | OPTIONAL_ADAPTER / UI_REFERENCE (live only) | Live memory/WS telemetry source for future caster/overlay; core must not depend on it | LGPL-3.0; package.json GPL discrepancy — legal review needed before bundling | Active; adapter boundary keeps impact low | Medium (separate optional adapter service) | High for live segment timeline; none for offline corpus |
| abstrakt8/rewind | REFERENCE_IMPLEMENTATION / ALGORITHM_REFERENCE | Replay frame parsing + judgement timeline + UR formula; MIT, clean to adapt | MIT | Low/limited upstream activity | Medium (port core pieces) | High for replay evidence design |
| kionell/osu-parsers | TEST_ORACLE / REFERENCE_ONLY | Independent lazer-based parser for cross-validation; potential TS-side consumer | MIT | Moderate | Low for fixtures; medium for TS integration | High as oracle; optional as runtime dep |
| jramseygreen/osu_bot_framework-v3 | DO_NOT_USE | Dead IRC architecture, legacy webpage JSON, no v2 auth; MIT but stale | MIT | None (don't adopt) | N/A | Only conceptual |
| MaxOhn/rosu-v2 (addendum) | REFERENCE_ONLY / CONTRACT_REFERENCE | Most precise public description of match event paging and game/score semantics (used by Bathbot) | MIT | N/A (not a Python dependency) | N/A | High for API contract verification |

---

## 6. UNKNOWN / Not Verified

- rosu-v2 exact release commit and current `lazer` branch SHA (docs.rs version 0.9.0 verified; newer branch semantics UNKNOWN).
- rosu-v2 `Team` enum documentation page (values Blue/Red/None confirmed indirectly through Bathbot source usage).
- ppy/osu-web PR #12418 (`/matches?active=`) merged status.
- tosu tourney memory fields on lazer ("not tested yet" upstream); stable/lazer field parity UNKNOWN.
- Any tournament-specific official tooling beyond room APIs (none identified).

