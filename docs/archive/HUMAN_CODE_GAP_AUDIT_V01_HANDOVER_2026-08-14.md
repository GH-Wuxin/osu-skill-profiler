# Human-Code Gap Audit v0.1 — Handover 2026-08-14

Repository: `osu-skill-profiler`
Prepared by: execution agent (wuxin), after Codex handoff
Scope: P0 (preserve + close out) and P1 (nine-task Human–Code Gap Audit) only.
**No training, no commit, no push, no ML, no new questions, no analyzer edits.**

## 1. Current snapshot (evidence baseline)

```text
training/datasets/active_learning_v01/human_pilot_v02/
collections/collection_001/analysis/snapshot-a33e951ca690cf1904b0d244/
```

Re-verified 2026-08-14: all four artifact SHA-256 match `manifest.json` exactly
(REPORT.md `315c7d8b…`, analysis.json `69a529f4…`,
human_evidence.jsonl `f309c0b7…`, responses.jsonl `a02e9d48…`;
manifest itself `b5efbc4c…`). Snapshot is intact and is the sole evidence
baseline for this round. It was not overwritten, rebuilt or replaced.
Earlier snapshots (`dcb68f7c…`, `5801b880…`) remain untouched as history.

## 2. Working tree state (as of handoff)

Tracked, modified (preserved, not committed):

| File | Nature |
|---|---|
| `docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md` | legitimate update: PENDING sections filled with 20k + full-corpus (126,509 maps) gate results (+218/−33) |
| `src/osu_skill_profiler/weak_supervision/__init__.py` | exports for the v0.1 weak-supervision modules |

Untracked but valid experiment assets (do not delete, do not commit):

- `docs/` — 22 documents: active-learning design/dry-run/handover,
  human-annotation contract/pilot/collection analyses (interim + final) and
  dispositions, weak-supervision contract/infra/pilot/provenance/handover,
  red-team recheck, transcription errata. The collection results
  (`HUMAN_ANNOTATION_COLLECTION_001_FINAL_*`) are the authoritative pilot
  conclusions.
- `src/osu_skill_profiler/active_learning/` — the whole v0.1 module
  (batch, collection analysis, contracts, selection, human pilots v01/v02,
  presentation v02, metrics, training guard).
- `src/osu_skill_profiler/weak_supervision/` — audit/contracts/leakage/
  pilot/registry/runtime/v01 modules.
- `tests/` — 7 test files (`test_active_learning_v01`, annotation runner
  multi v02, collection analysis, human pilot, remediation, weak evidence,
  weak supervision pilot).
- `tools/` — 12 tools incl. annotation runners v01/v02/multi_v02,
  `annotation_ui_v01.html`, conflict-review server, collection analyzer,
  pilot preparers, weak-supervision pilot, performance probe.

Git-ignored data that must be preserved on disk (never commit):

- `training/datasets/**` — corpus QA artifacts (feature/local/reference 5k
  and full), splits, the weak-supervision pilot (evidence.jsonl 37 MB),
  and the entire active-learning dataset tree including
  `collection_001/analysis/snapshot-a33e951…` (the evidence baseline),
  `pilot_tasks.jsonl`, `blind_pilot.jsonl`, `human_propositions.json`,
  and the 15 annotator response files.
- `tmp/**` — red-team/QA scratch and the new `tmp/gap_audit/` working dir
  (read-only extraction scripts + intermediate JSON for this audit).

Data-loss risk assessment: the only large derived artifacts (corpus QA,
weak-supervision evidence, snapshot) are git-ignored; they exist on disk and
are reproducible via the recorded tools/seeds, but the collection responses
are raw HUMAN evidence — they must be copied off-machine before any cleanup.

## 3. Services closed this round

| Port/PID | Identity (confirmed before action) | Action |
|---|---|---|
| 8771/8772/8773 | `tools/review_annotation_conflicts_v01.py` conflict-review pages | already closed on arrival (no listeners) — verified |
| 8767 / PID 39392 | `tools/annotation_runner_multi_v02.py` — collection_001 annotation UI ("osu! 谱面对比小测试") | terminated together with parent python PID 43656 via a single UAC-elevated `Stop-Process` (processes ran at High integrity; unprivileged kill returned Access denied) |
| PID 41092 | powershell launcher shell of the above tree | left untouched (sandbox shell) |

Post-action verification: no listeners on 8767/8771/8772/8773; no `python.exe`
processes remain from this project. (Ports 8388/8389/8787/8800/9001/9012–9014/
9210/9410 belong to the WuxinBot project and were not touched.)

## 4. P1 audit — entry point and outcome

Entry point (already executed, see deliverables):

1. Nine tasks located uniquely in existing data:
   - 6 boundary-class = the double-covered `BOUNDARY_ADJACENT` tasks with
     directional human agreement: `263cea7e`, `2ae01c9c`, `bb6f8c7d`,
     `0680617d`, `14cfa82a`, `f28185e6`.
   - 3 conflict-class = the collection audit queue: `d4f690cb`,
     `55b0b9f0`, `b863fbee`.
2. Evidence joined per task: snapshot responses (answer/latency/confidence/
   presentation order) + control-network extra judgments (exact repeats) +
   weak-supervision evidence rows (all 18 entity snapshot hashes recomputed
   and matched) + rule semantics (`weak_supervision/pilot_v01.py`) + presented
   window/geometry parsed from the corpus + renderer code. No recomputation of
   expensive intermediates; no analyzer modification.
3. Deliverables produced:
   - `docs/HUMAN_CODE_GAP_AUDIT_V01.md` (full report: per-case evidence,
     feature deltas, wording analysis, cross-case patterns, P2/P3 suggestions)
   - `docs/HUMAN_CODE_GAP_DISPOSITION_V01.json` (machine-readable, 9 cases,
     disposition + confidence + evidence + flags)
   - `tmp/gap_audit/` (ignored working dir: `extract_evidence_v01.py`,
     `extract_geometry_v01.py`, `recompute_code_signal_v01.py` + intermediate
     JSON/TXT outputs).

Key results (details in the report):

- Disposition counts (primary): MISSING_OBSERVABLE 4 (B2, B4, B5, B6),
  MULTI_AXIS_TRADEOFF 3 (B3, C1, C3), GENUINE_BOUNDARY 1 (B1),
  PRESENTATION_DEFECT 1 (C2); secondary: WORDING_DRIFT ×4,
  POSSIBLE_RUSHED_RESPONSE ×1. LOW confidence: B3 (mechanism undetermined).
- Top findings: (1) dense B2 — 4/4 humans vs byte-identical code features
  (code blind to slider repeat/reversal structure — a structural candidate,
  not a click count — and to wider sustained-tap runs); **AMENDMENT (P1.5):**
  reversal is not equivalent to extra clicks; no replay/input evidence exists.
  (2) slider boundary trio — human direction is CORRELATED with per-slider
  follow DURATION (strongest candidate, not causally identified) while the
  rule consumes only path-distance p90 (equal-pixel sliders follow ~2× longer
  on the winning side); (3) movement AND-wording
  collides with the contract's own velocity-vs-span ambiguity (C3 splits
  exactly along the axes; B3's humans split 2-2 once the exact-repeat
  control is counted — premise correction recorded).
- No case was treated as "code direction error": expected_sign is null on
  all nine; code directions are reported only as aggregated signals.
- Fast answers flagged, never invalidated (B1 annotator_002; C1
  annotator_030 at 6.7 s).
- Visual-replay limitation recorded honestly: no persisted replay/render
  artifacts exist; the visual layer was reconstructed from renderer code +
  window geometry + displayed metadata.

## 5. Open issues carried forward

- 16/40 tasks remain single-covered; 3 participants have <5 responses; the
  "再来 5 题" batch requested by one participant was never answered
  (annotator_010 holds a 10-task allocation, answered 5).
- Same-annotator control evidence essentially absent (1 recognizable repeat;
  0 inversions). Intra-annotator reliability unknown.
- CANNOT_JUDGE unused (0/64) — abstention affordance unvalidated.
- C1/C2 legacy pairs: presentation degradation unverifiable without replay.
- B3: 2–2 human split with no identified mechanism — needs a third judgment.
- The follow-duration hypothesis for slider questions is corroborated but not
  proven; needs a counterbalanced probe (P2).
- 2 modified + ~40 untracked/ignored asset groups remain uncommitted by
  design (red line: no commit this round).

## 6. Standing prohibitions (unchanged, still in force)

- No training, no ML entry, no new questions, no questionnaire expansion.
- No commit/push; no rewriting old snapshots, results or historical docs.
- No analyzer edits without evidence; no bulk refactor from a single suspect.
- Missing data must be marked missing — never guessed or imputed.
- Do not overwrite `snapshot-a33e951ca690cf1904b0d244` (or any older snapshot).
- Next phase requires explicit authorization: this round stops after P0+P1.

## 7. How to resume

Re-run the read-only extraction (regenerates `tmp/gap_audit/*`):

```powershell
python tmp/gap_audit/extract_evidence_v01.py
python tmp/gap_audit/extract_geometry_v01.py
python tmp/gap_audit/recompute_code_signal_v01.py
```

All three are idempotent, write only under `tmp/gap_audit/`, and use the
project's own parsers/rule code. The audit deliverables are self-contained
under `docs/`.
