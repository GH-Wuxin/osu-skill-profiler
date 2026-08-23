# Dataset Manifest & Splits

The repository does **not** store large numbers of `.osu` files. Instead,
datasets are described by JSON manifests that reference local files and pin
their content with SHA-256 checksums.

## Manifest format

```json
{
  "schema_version": "0.1.0",
  "parser_version": "0.1.0",
  "feature_version": "0.2.0",
  "samples": [
    {
      "sample_id": "unique-string",
      "source": "local | osu-collector | tournament | ...",
      "beatmap_id": 123456,
      "beatmapset_id": 123,
      "mapper": "mapper-name",
      "reference": "relative/or/absolute/path.osu",
      "checksum": "sha256:<64 hex>",
      "metadata": { "difficulty_name": "Insane" }
    }
  ]
}
```

Rules enforced by `dataset/manifest.py`:

- `sample_id` must be unique and non-empty.
- `source`, `mapper`, `reference` are required strings.
- `beatmap_id` / `beatmapset_id` must be positive ints or null.
- `checksum` must start with `sha256:`.
- `metadata` must be an object or null.

`validate-dataset manifest.json --verify-checksums` additionally checks that
every referenced file exists and matches its checksum.

## Split strategy

The canonical implementation is
`src/osu_skill_profiler/dataset/split_v01.py` (version `0.1.0`). Generated
artifacts live under `training/datasets/splits/v01` (historical QA versions)
and `training/datasets/splits/v02` (corrected Feature 0.2 / Local 0.3 /
Reference 0.2 QA versions).

### Canonical: content-addressed, deterministic assignment

- Components are built from `map_checksum`, beatmapset/local-set groups and
  normalised mapper groups; identical file checksums are always unioned.
- Assignment is `SHA-256(split_version + seed + component_id)`, components
  sorted by `(rank, component_id)`, then cut into **train/val/test
  (80/10/10)** by cumulative map count.
- This is independent of input enumeration order and of Python's `random`
  implementation.

### Set-disjoint and mapper-disjoint

- **set_disjoint** keeps every difficulty of a beatmapset (or local set
  folder) in one split, preventing near-duplicate same-set patterns from
  leaking across folds.
- **mapper_disjoint** groups by normalised exact creator name
  (`NAME_ONLY` quality; creator ids are unavailable). Unknown mappers are a
  single `UNKNOWN` group; the unknown-only variant exists separately.
- **strict_disjoint** unions both set and mapper constraints.

### Legacy compatibility module

`src/osu_skill_profiler/dataset/split.py` remains as the pre-v0.1 two-fold
(`train`/`test`) compatibility module and is **not** the generator of the
audited `v01`/`v02` split artifacts. Prefer `split_v01.py` for new work.

### Leakage prevention details

- Samples without a trustworthy set id fall back to the local set folder;
  ungrouped samples always become their own group.
- `validate_disjoint_split()` in the legacy module and the split-audit tool
  both report overlap violations.
- Splits never stratify randomly by difficulty.

## Versioning

Manifests carry `parser_version` and `feature_version`, so a dataset can be
rebuilt reproducibly when the parser or feature extractor changes.

## Reserved training layout

See `training/README.md`: generated datasets, splits, and weak-label outputs
are gitignored. Current on-disk layout uses `training/datasets/...`
(including `training/datasets/splits/v01|v02`); `training/splits/` and
`training/weak_labels/` remain reserved empty layouts.
