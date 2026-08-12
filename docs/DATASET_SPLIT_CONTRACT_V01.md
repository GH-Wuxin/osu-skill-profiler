# Dataset Split Contract v0.1

Status: **FINAL** (2026-08-11)

Dataset version: `v0.1`
Split version: `0.1.0`
Generator version: `0.1.0`

This contract is taxonomy-independent. It defines map, set and mapper
identities, the split algorithm, challenge subsets, temporal OOD status,
reproducibility requirements, public artifact policy and the target leakage
contract.

## 1. Map identity

- `map_key = map_checksum = sha256:<hex>` of the `.osu` file bytes.
- Every valid map has exactly one `map_key`.
- Identity never contains an absolute path, hostname, process id or
  timestamp.
- Duplicate classification:
  - `UNIQUE`: one manifest row.
  - `KNOWN_DUPLICATE`: more than one row with the same checksum and
    compatible set/mapper grouping.
  - `CONFLICT`: more than one row with the same checksum but different set or
    mapper grouping. v0.1 reports 11 conflicts; they remain hard-constrained
    to the same assignment component.

## 2. Set identity

```text
if beatmapset_id is a positive int:
    set_group_key = "b:<beatmapset_id>"
    policy = "beatmapset_id"
else:
    set_group_key = "l:<local_set_group>"
    policy = "local_set_group"
```

Audited invariants (v0.1):

- every map has exactly one `set_group_key`;
- one `BeatmapSetID` never maps to multiple incompatible group keys;
- fallback grouping does not merge unrelated maps: 0 local folders that
  contain maps missing set ids contain multiple distinct set ids;
- duplicate checksums cannot cross incompatible groups silently (11
  conflicts are reported, never repaired).

## 3. Mapper identity

```text
if normalised creator name exists:
    mapper_group_key = "n:<normalised name>"
    quality = "NAME_ONLY"
else:
    mapper_group_key = "u:unknown"
    quality = "UNKNOWN"
```

- Normalisation is exact: `casefold` + whitespace collapse. No fuzzy
  matching, no LLM resolution.
- `VERIFIED_ID` is never emitted because `creator_id` is absent from the
  corpus manifest. All mapper constraints in v0.1 are provisional.
- v0.1 has 4,512 mapper groups, 0 unknown rows, 58 raw-name variant groups.

## 4. Split algorithm

1. Build hard assignment components with union-find. Records sharing a
   `set_group_key`, a `mapper_group_key` (where claimed), or an identical
   `map_checksum` are in one component.
2. Component rank:

```text
rank = int(SHA-256(split_version + "\\n" + seed + "\\n" + component_id)[:8])
```

3. Sort components by `(rank, component_id)`; place cumulative map-count
   boundaries at 80% / 10% / 10% of total maps.

Inputs never include timestamps, paths, enumeration order, process id or
hostname.

## 5. Seed and versioning

- `seed = "osu-skill-profiler-dataset-split-v01"`
- `split_version = "0.1.0"`
- Same source manifest + config must yield byte-identical membership.

## 6. Benchmark manifests

`training/datasets/splits/v01/`:

- `set_disjoint.jsonl` - all rows, set-disjoint.
- `mapper_disjoint.jsonl` - known-mapper rows, mapper-disjoint.
- `mapper_disjoint_unknown.jsonl` - `UNKNOWN` mapper rows (empty in v0.1).
- `strict_disjoint.jsonl` - all rows, set + known-mapper disjoint via
  connected components.
- `legacy_format_ood.jsonl`
- `pathological_challenge.jsonl`
- `reference_disagreement_challenge.jsonl`
- `distribution_audit.json`
- `identity_audit.json`
- `near_duplicate_diagnostics.jsonl`
- `summary.json`
- `manifest.json`

Split records contain no absolute paths and no local Songs paths. `sample_id`
is included for local join convenience; public redistribution must drop it.

## 7. Challenge subsets

- `LEGACY_FORMAT_OOD`: `format_version <= 5` only. This is a
  `FORMAT_GENERATION_PROXY`, never temporal OOD.
- `PATHOLOGICAL_CHALLENGE`: maps with established provenance flags
  (`bpm_extreme_high`, `timing_extreme_high`, `green_extreme_high`,
  `repeats_extreme`, `object_count_extreme_*`, `duration_extreme_*`,
  `all_slider`, `aspire_like`, `format_v128`), geometry-blocked reference
  rows, or manifest-derived extreme finite values. Reasons are preserved per
  row; nothing is silently clipped or dropped.
- `REFERENCE_DISAGREEMENT_CHALLENGE`: the retained Type-B candidates
  (observable extreme while reference ordinary). v0.1: 50 candidate objects
  across 41 maps. Wording is neutral; no "official blind spot" claim.

## 8. Temporal OOD status

```text
TEMPORAL_OOD: BLOCKED
Reason: no trustworthy ranked/submitted dates in corpus metadata
```

`mtime_year` is not ranked/creation year. `format_version` is only a format
generation proxy.

## 9. Reproducibility requirements

- Deterministic content hashing (SHA-256).
- Machine-independent ordering: components sorted by hash, rows sorted by
  `(map_checksum, sample_id)`.
- `regenerate-check` must pass with identical and shuffled input enumeration.

## 10. Public artifact policy

Public-safe: generator, schema, tests, synthetic fixtures, concise reports,
aggregate statistics, compact checksum manifests.

Local-only: full split manifests (they reference local `sample_id` values),
the `.osu` corpus, QA JSONL, absolute paths. Full manifests stay in
`training/datasets/splits/v01/` and are not committed.

## 11. Target leakage contract

Policy classes:

```text
OBSERVABLE_INPUT_CANDIDATE      ls.* numeric signals, v0.1 features
OFFICIAL_REFERENCE_ONLY         ref.ppy.*
WEAK_LABEL_SOURCE               future explicit weak labels
FUTURE_GROUND_TRUTH             future human labels
```

Rules:

1. If `ref.ppy.*` (or a deterministic transform) constructs a target, that
   exact value must not be a model input for the same prediction.
2. `ref.ppy.*` is never `model_input_safe`; exploratory use only.
3. Weak labels must carry provenance and may only be trained on train-split
   maps.
4. Corpus-level statistics used by future preprocessing must be computed on
   train only.

