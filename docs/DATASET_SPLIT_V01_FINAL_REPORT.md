# Dataset Split & Leakage Audit v0.1 - Final Report

Status: **PASS** (2026-08-11)

Dataset version: `v0.1`
Split version: `0.1.0`

## 1. Authoritative corpus count

`126,509` valid Standard maps (from `training/datasets/std_manifest.json`;
manifest total `126,533`, `24` parse failures excluded). The count is taken
from the authoritative manifest at generation time, not hardcoded.

Source manifest checksum:
`sha256:f3bd3ffd2ca05787ed5f5d6dea2c5ddaef254eb6d5bc3fa372d7ce1d0a733247`

## 2. Map identity results

`map_key = map_checksum = sha256:<hex>`. Checksum classes:

| Class | Count |
| --- | ---: |
| UNIQUE | 125,467 |
| KNOWN_DUPLICATE | 510 |
| CONFLICT | 11 |

11 conflicts are identical bytes stored under different set/mapper grouping
(e.g. `[no video]` folder copies). They are reported in
`identity_audit.json`, never repaired, and hard-constrained to the same
assignment component.

## 3. BeatmapSet / local-set grouping results

Policy: `b:<beatmapset_id>` when present, else `l:<local_set_group>`.

- `105,153` rows carry `BeatmapSetID`; the rest use the local fallback.
- `111` beatmapset ids appear in more than one local folder (folder renames /
  `[no video]` variants) - reported, not repaired.
- `0` local folders containing maps with missing set ids contain multiple
  distinct set ids - the fallback does not merge unrelated maps in v0.1.

## 4. Mapper identity coverage and quality

- Mapper groups: `4,512`.
- Known (NAME_ONLY): `126,509`; UNKNOWN: `0`.
- Raw-name variant groups (same normalised name, different raw spelling):
  `58`.
- Quality is always `NAME_ONLY`; `creator_id` is absent from the manifest, so
  `VERIFIED_ID` is unavailable. Mapper-disjoint results are provisional.

## 5. Duplicate / near-duplicate findings

- Identical checksums: `510` KNOWN_DUPLICATE + `11` CONFLICT (hard
  constraints).
- `2,296` beatmap-id conflicts (same `BeatmapID`, different checksums) -
  metadata anomalies, reported only.
- Bounded near-duplicate diagnostics (same artist/title/mapper buckets,
  duration within 5%, equal object count): `271,501` pairs scanned,
  `200` examples kept. No hard constraint is derived from these in v0.1.

## 6. SET_DISJOINT counts

| Split | Maps | Sets | Known mappers |
| --- | ---: | ---: | ---: |
| train | 101,216 | 25,956 | 4,184 |
| val | 12,658 | 3,199 | 1,585 |
| test | 12,635 | 3,258 | 1,590 |

Proportions: `80.01% / 10.01% / 9.99%`.

## 7. MAPPER_DISJOINT counts

| Split | Maps |
| --- | ---: |
| train | 101,195 |
| val | 12,721 |
| test | 12,593 |

UNKNOWN mapper subset: `0` maps (empty file emitted for schema stability).

## 8. STRICT_SET_AND_MAPPER_DISJOINT counts/status

Constructed via deterministic connected components over set + known mapper
groups:

| Split | Maps |
| --- | ---: |
| train | 101,190 |
| val | 12,678 |
| test | 12,641 |

Status: **PASS** (provisional mapper identity).

## 9. LEGACY_FORMAT_OOD count/definition

Definition: `format_version <= 5` (defensible old format generations; v3/v4/v5).

Count: `5,113` maps. This is a `FORMAT_GENERATION_PROXY`, not temporal OOD.

## 10. PATHOLOGICAL_CHALLENGE count/definition

Definition: any established QA provenance flag (`bpm_extreme_high`,
`timing_extreme_high`, `green_extreme_high`, `repeats_extreme`,
`object_count_extreme_*`, `duration_extreme_*`, `all_slider`, `aspire_like`,
`format_v128`), geometry-blocked reference rows, or manifest-derived extreme
finite values / short maps.

Count: `11,527` maps. Reasons are preserved per row; nothing is clipped or
dropped.

## 11. REFERENCE_DISAGREEMENT_CHALLENGE count/definition

Definition: retained Type-B candidates from
`reference_disagreement_candidates.jsonl` (observable extreme combination
while all official reference values are ordinary), mapped to map-level
challenge entries with neutral reasons.

Counts: `50` candidate objects across `41` maps.

## 12. TEMPORAL_OOD status

```text
TEMPORAL_OOD: BLOCKED
Reason: no trustworthy ranked/submitted dates in current corpus metadata
```

`mtime_year` is forbidden as ranked/creation year. `format_version` is only a
format generation proxy.

## 13. Leakage verification results

`tools/dataset_split_audit.py verify` on the generated v0.1 manifests:

```text
VERIFY OK: all constraints hold
```

Verified: full coverage (`126,509` rows), no duplicate rows, no
checksum/set/mapper cross-split leakage for every claimed benchmark,
challenge subset integrity, canonical ordering, schema validity, missing
grouping identifiers, manifest checksums.

## 14. Distribution drift findings

Per-split distributions are in `distribution_audit.json`. Summary:

- object count: p50 337-342, p95 1,090-1,132 across splits - close.
- duration: p50 ~123.7-126.1 s - close.
- AR/OD/CS/HP p50s identical (8 / 7 / 4 / 5); p95s close.
- format_version: v14 dominates (~75-79%); v3-v5 (legacy) are slightly
  under-represented in test (`3.47%` vs `4.10%` train / `4.11%` val).
- pathological rate: 9.13% train / 8.45% val / 9.63% test.
- geometry-blocked rate: 0.037% / 0.040% / 0.087% (53 maps total).
- reference-disagreement rate: 0.033% / 0.032% / 0.032% (41 maps total).
- extreme finite BPM maps landed only in train/test; val max BPM is 1,940
  while train/test means are distorted by values up to `6e302`. This is
  reported as drift, not rebalanced.

## 15. Target-leakage contract

Defined in `docs/DATASET_SPLIT_CONTRACT_V01.md` section 11:
`ref.ppy.*` is `OFFICIAL_REFERENCE_ONLY`, never a model input for a
prediction whose target derives from it; weak labels are train-only; future
preprocessing statistics are fit-on-train-only.

## 16. Reproducibility results

```text
REGEN OK: byte-identical regeneration in same order and shuffled order
```

Passing `regenerate-check` proves membership and content checksums are
unchanged under identical input and under shuffled input enumeration.

## 17. Split/manifest checksums

From `summary.json`:

| File | SHA-256 |
| --- | --- |
| set_disjoint.jsonl | `0a60fec8fbe3d6a311c97a84c33f1c60a57924d4fda1dae65b8525fd943a4e1b` |
| mapper_disjoint.jsonl | `9b7d9b6d6c089d1774e84119fd54784b59c363151d55313e2767e80552e8ae63` |
| mapper_disjoint_unknown.jsonl | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| strict_disjoint.jsonl | `ff3afe2ff145f28fc437e2f4703cbc98a62a4f5963538468c45141559767d6ea` |
| legacy_format_ood.jsonl | `a722372b9878fa71b5bd7cc8353ec60a575439dee218d09091638dec2958bbc7` |
| pathological_challenge.jsonl | `6fdab5adaf328ae6144d7b268234ce9ed0a135f9fd2ad4613db78220806b49c0` |
| reference_disagreement_challenge.jsonl | `735971d9e617cd5d91d3830ddd3e2c85067f2264e4b185187f70c326dc5d90c0` |
| distribution_audit.json | `4a655db19518c18cff773f38d24551fc90e6dab8fe6cf1b07ae0362a2c81532d` |
| identity_audit.json | `88f7df3bcd745de082262ab9884c9dee8100c4ffd9ddc763970fb8654296fe5b` |
| near_duplicate_diagnostics.jsonl | `8a3c0ae0fa8405a2d5d158f65ab03ea4f6ecde52f9b449f8bd5111ab07960af8` |

## 18. Runtime

- Full generation wall time: ~133-145 s per run.
- `regenerate-check`: two generations, ~275-285 s total.
- Workers: `1` (metadata-only; well under the `MAX_WORKERS = 4` hard limit).

## 19. Worker count

`1` for all runs.

## 20. Peak memory

Not measured (streaming/online processing; working set is per-map records
only, ~126k small dicts plus QA flag indexes). Recorded as not available.

## 21. Files created/changed

- `src/osu_skill_profiler/dataset/split_v01.py` (new core)
- `tools/dataset_split_audit.py` (new generate/verify/regenerate-check)
- `tests/test_dataset_split_v01.py` (14 new synthetic tests)
- `docs/DATASET_LEAKAGE_THREAT_MODEL_V01.md` (new)
- `docs/BENCHMARK_PROTOCOL_V01.md` (new)
- `docs/DATASET_SPLIT_CONTRACT_V01.md` (new)
- `docs/DATASET_SPLIT_V01_FINAL_REPORT.md` (this report)
- `.gitignore` (ignore `tmp/` agent checkpoints)
- `tmp/agent-progress/dataset-split-v01.md` (ignored checkpoint)
- `training/datasets/splits/v01/*` (local benchmark manifests)

## 22. Public vs local artifact decision

Public-safe (committable): generator, schema, tests, synthetic fixtures, the
four docs, aggregate statistics, compact checksum manifests.

Local-only (not committed): full split manifests, corpus manifest, QA JSONL,
`.osu` corpus, absolute paths, checkpoints. Full manifests remain in
`training/datasets/splits/v01/` and are excluded from git.

## 23. Known limitations

- Mapper identity is `NAME_ONLY` (no `creator_id`); name collisions/renames
  are unresolved.
- Near-duplicate detection is deliberately lightweight (metadata buckets
  only); copied maps with changed bytes are not excluded.
- `11` checksum conflicts and `2,296` beatmap-id conflicts are reported, not
  repaired.
- `111` set ids span multiple local folders; the fallback remains safe only
  while the audited `0`-violation invariant holds.
- Temporal OOD is blocked (no trustworthy dates).
- Full split manifests are local-only by policy.

## 24. Technical debt

- `tools/dataset_split_audit.py` re-reads the full QA files for flag
  extraction; a compact per-map flag index would speed regeneration.
- `identity_audit.json` grows with conflict examples; caps or separate files
  may be needed at larger corpus sizes.
- The old `dataset/split.py` (Python-random based) is superseded but kept
  untouched for compatibility.

## 25. Explicit confirmation

This phase performed:

- no training (no LightGBM/XGBoost/PyTorch/neural/regression/classification/
  ranking/embedding/clustering);
- no taxonomy generation or freeze;
- no human labels, no pairwise annotation;
- no weak-label model or pseudo-label generation;
- no tournament/player implementation;
- no replay/live implementation;
- no WuxinBot integration;
- no full-corpus signal recomputation (metadata-only processing);
- existing semantic layers unchanged (Feature v0.1, Local Signal v0.2,
  Official Reference Signal v0.1, segment semantics);
- workers `1 <= 4`;
- no git commit;
- no deployment.

## Final statuses

```text
IDENTITY:            PASS
LEAKAGE_AUDIT:       PASS
SET_DISJOINT:        PASS
MAPPER_DISJOINT:     PASS (provisional NAME_ONLY identity)
STRICT_DISJOINT:     PASS (provisional NAME_ONLY identity)
CHALLENGE_SUBSETS:   PASS
REPRODUCIBILITY:     PASS
BENCHMARK_PROTOCOL:  PASS
TEMPORAL_OOD:        BLOCKED (no trustworthy dates)
OVERALL:             PASS
```
