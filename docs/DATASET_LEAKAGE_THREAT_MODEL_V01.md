# Dataset Leakage Threat Model v0.1

Status: **FINAL** (2026-08-11)

Dataset version: `v0.1`
Split version: `0.1.0`

This document is the leakage threat model behind the v0.1 dataset evaluation
boundary. Every threat lists severity, mechanism, current mitigation,
remaining risk and future mitigation.

Severity scale:

- **CRITICAL** - silently invalidates a claimed generalisation result.
- **HIGH** - can materially inflate a claimed generalisation result under
  realistic conditions.
- **MEDIUM** - bounded or conditional leakage; must be disclosed per benchmark.
- **LOW** - diagnostic only; no hard constraint in v0.1.

---

## 1. Same-map leakage

- Severity: CRITICAL
- Mechanism: the exact same `.osu` file appearing in both a training split
  and an evaluation split.
- Current mitigation: `map_checksum` is the SHA-256 of the file. Identical
  checksums are unioned into one hard assignment component in every
  benchmark, so identical content can never cross a split. Verifier checks
  checksum disjointness for `SET_DISJOINT`, `MAPPER_DISJOINT` and
  `STRICT_DISJOINT`.
- Remaining risk: an identical map re-saved with different file bytes
  (whitespace, metadata edits, timing-point rewrites) is not caught by
  checksum equality.
- Future mitigation: content-normalised identity (parse-normalised digest)
  and near-duplicate leakage probes before any training run.

## 2. Same-beatmapset leakage

- Severity: CRITICAL
- Mechanism: multiple difficulties of one song set distributed across train
  and test.
- Current mitigation: `set_group_key = b:<beatmapset_id>` when a positive id
  is present, else `l:<local_set_group>`. All maps sharing a set key are in
  one assignment component.
- Remaining risk: 126,509 valid maps contain 126,509 rows but only
  `105,153` carry `BeatmapSetID`; the rest rely on the local folder grouping.
  `111` beatmapset ids appear in more than one local folder (renamed or
  `[no video]` copies). The fallback policy is safe for the current corpus
  because zero folders with missing set ids contain multiple distinct set
  ids, but a future corpus change must re-audit this invariant.
- Future mitigation: verified `BeatmapSetID` from the osu! API for the
  21,356 fallback-grouped maps; reject or quarantine ambiguous folders.

## 3. Local-set fallback leakage

- Severity: HIGH
- Mechanism: `local_set_group` is a folder name; two unrelated maps sharing
  a folder would be treated as one set.
- Current mitigation: the identity audit verifies no folder that contains a
  map missing `BeatmapSetID` also contains multiple distinct set ids
  (`0` violations in v0.1). Any future violation is emitted as a hard
  diagnostic, not silently repaired.
- Remaining risk: folder names are machine-local and can change; the fallback
  is not a verified web identity.
- Future mitigation: web-verified set ids; keep local folder only as a
  temporary join key.

## 4. Mapper leakage

- Severity: CRITICAL (for mapper-disjoint benchmarks)
- Mechanism: difficulties by the same mapper split across train/test.
- Current mitigation: `MAPPER_DISJOINT` and `STRICT_DISJOINT` union maps by
  `mapper_group_key`; the verifier enforces mapper disjointness for every
  claimed benchmark.
- Remaining risk: mapper identity is `NAME_ONLY` (normalised creator name).
  The current manifest contains no `creator_id`, so name collisions and
  renames can both merge and split real identities.
- Future mitigation: `creator_id` from a reliable source; re-audit before any
  training run; treat `NAME_ONLY` results as provisional.

## 5. Mapper identity uncertainty

- Severity: HIGH
- Mechanism: same name with different casing/whitespace (58 name-variant
  groups in v0.1), identical names for different people, or renamed accounts.
- Current mitigation: exact normalisation only (`casefold` + whitespace
  collapse), never fuzzy matching, never LLM resolution. Variants are
  reported in `identity_audit.json`; quality is always explicit
  (`NAME_ONLY` or `UNKNOWN`).
- Remaining risk: normalisation cannot distinguish real identity collisions.
- Future mitigation: stable `creator_id`; no training-time resolution.

## 6. Near-duplicate leakage

- Severity: MEDIUM
- Mechanism: copied/remixed/alternate-version maps with different bytes but
  near-identical gameplay.
- Current mitigation: lightweight diagnostics only - identical checksum
  (hard constraint), and same artist/title/mapper buckets with duration
  within 5% and equal object count are reported as
  `POSSIBLE_NEAR_DUPLICATE`. No hard constraint is derived from these
  diagnostics in v0.1.
- Remaining risk: 271,501 bounded same-artist/title/mapper pairs were
  scanned; near-duplicates are not excluded from any split.
- Future mitigation: deterministic gameplay fingerprint (spacing/timing
  sequence digest) and explicit near-duplicate challenge subset.

## 7. Metadata leakage

- Severity: MEDIUM
- Mechanism: model inputs derived from fields that also identify the map or
  set (beatmap id, set id, title, artist, mapper, difficulty name).
- Current mitigation: split manifests keep `beatmap_id` and group keys but
  mark them as identity, not model-input features; the split contract
  separates identity metadata from observable inputs.
- Remaining risk: future feature pipelines may accidentally include identity
  metadata as features.
- Future mitigation: feature-allowlist contract with an explicit deny-list
  for identity fields.

## 8. Difficulty-name leakage

- Severity: LOW
- Mechanism: version/difficulty names (`[Insane]`, `[Nino's Extra]`) can
  correlate with difficulty and mapper conventions.
- Current mitigation: difficulty name is not used by the split algorithm;
  manifests do not include it.
- Remaining risk: difficulty name is absent from the public split records but
  still present in the corpus; downstream feature builders could reintroduce
  it.
- Future mitigation: explicitly exclude `version` from observable feature
  schemas.

## 9. Temporal / era leakage

- Severity: HIGH (if chronology were claimed; not claimed in v0.1)
- Mechanism: old-format maps or maps from one era concentrated in one split.
- Current mitigation: `TEMPORAL_OOD = BLOCKED` because no trustworthy
  ranked/submitted dates exist in the corpus. `mtime_year` is forbidden as a
  ranked/creation year; `format_version` is only a
  `FORMAT_GENERATION_PROXY`. `LEGACY_FORMAT_OOD` is descriptive, never a
  chronological OOD claim.
- Remaining risk: era-like distribution drift (old formats are slightly
  under-represented in test) is reported but not controlled.
- Future mitigation: trustworthy ranked-date metadata from the osu! API;
  only then a real chronological OOD benchmark.

## 10. Pathological overrepresentation

- Severity: MEDIUM
- Mechanism: extreme/aspire-like/geometry-blocked maps concentrated in train
  or test can distort aggregate metrics.
- Current mitigation: all established pathological provenance flags are
  carried into `PATHOLOGICAL_CHALLENGE`; per-split pathological rates are
  reported in `distribution_audit.json`. Pathological maps are never silently
  clipped or dropped.
- Remaining risk: 11,527 challenge maps are not rebalanced; a model trained
  on the full train split sees pathological examples at the natural corpus
  rate.
- Future mitigation: optional pathological-stratified auxiliary benchmark
  with disclosed rates.

## 11. Reference-signal target leakage

- Severity: CRITICAL (whenever reference signals are used as targets)
- Mechanism: `ref.ppy.*` values (or deterministic transforms of them) used as
  pseudo-targets while the same values remain available as model inputs.
- Current mitigation: the target leakage contract (section 15 of the split
  contract) forbids this; `ref.ppy.*` is `reference_only`, never
  `model_input_safe`. Split manifests do not include reference values.
- Remaining risk: a future weak-supervision pipeline could accidentally copy
  reference values into both sides.
- Future mitigation: machine-readable target/input partition check in the
  verifier before any training run.

## 12. Weak-label leakage

- Severity: HIGH
- Mechanism: weak labels derived from the same observable signals that are
  model inputs.
- Current mitigation: no weak-label model exists; `ls.*` weak-label
  candidates are documented but no labels are generated in this phase.
- Remaining risk: the two v0.2 weak-label candidates
  (`ls.lazy_travel_distance_cs_normalised`, `ls.double_tap_feasibility`) are
  observables; any future rule using them as targets must not feed them back
  as inputs for the same prediction.
- Future mitigation: label provenance ledger and input/target separation
  checker.

## 13. Pseudo-label leakage

- Severity: CRITICAL
- Mechanism: any learned or rule-generated pseudo-label derived from
  evaluation-set maps leaking into training labels.
- Current mitigation: pseudo-label generation is forbidden this phase; the
  benchmark boundary is built before any training infrastructure.
- Remaining risk: future training loops must not fit pseudo-labels on test
  maps.
- Future mitigation: label-on-train-only policy enforced by the verifier.

## 14. Preprocessing contamination

- Severity: MEDIUM
- Mechanism: corpus-level statistics (normalisation moments, percentiles,
  dictionaries) computed over the whole corpus, including test maps, then
  applied to features.
- Current mitigation: all existing feature/signal layers are deterministic
  and corpus-statistic-free. Split manifests are metadata-only.
- Remaining risk: future normalisation layers may compute corpus statistics
  before splitting.
- Future mitigation: fit-on-train-only rule; verify by regenerating
  preprocessing from train split only.

## 15. Future player identity leakage

- Severity: HIGH
- Mechanism: player scores/performance used to construct labels while the
  same players appear in evaluation.
- Current mitigation: no player data is used in this phase.
- Remaining risk: future player-level datasets must define player-disjoint
  evaluation before use.
- Future mitigation: player identity and score provenance schema with
  player-disjoint benchmark contract.

## 16. Future tournament leakage

- Severity: HIGH
- Mechanism: tournament-picked maps in training when a downstream task
  evaluates tournament maps.
- Current mitigation: no tournament data is used; tournament/player work is
  parked.
- Remaining risk: future tournament subsets need their own leakage audit.
- Future mitigation: tournament-map registry and explicit tournament OOD
  subset.

## 17. Repeated tournament maps

- Severity: MEDIUM
- Mechanism: the same map picked in many tournaments becomes overrepresented
  in any tournament-derived label set.
- Current mitigation: none needed yet; no tournament data ingested.
- Remaining risk: future duplicate-map deduplication needed before
  tournament-derived labels.
- Future mitigation: map-checksum deduplication in tournament ingestion.

---

## Verification posture

For every benchmark that claims a constraint, the verifier
(`tools/dataset_split_audit.py verify`) fails hard on any violation; there
are no warning-only leakage guarantees. Diagnostics that are not hard
constraints (near-duplicates, metadata conflicts) are reported separately in
`identity_audit.json` and `near_duplicate_diagnostics.jsonl`.

