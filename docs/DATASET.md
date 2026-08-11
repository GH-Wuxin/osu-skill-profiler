# Dataset Manifest & Splits

The repository does **not** store large numbers of `.osu` files. Instead,
datasets are described by JSON manifests that reference local files and pin
their content with SHA-256 checksums.

## Manifest format

```json
{
  "schema_version": "0.1.0",
  "parser_version": "0.1.0",
  "feature_version": "0.1.0",
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

### Default: beatmapset-disjoint

All difficulties of the same `beatmapset_id` stay in the same fold. This
prevents near-duplicate maps (same patterns at different difficulty settings)
from leaking between train and test.

### Reserved: mapper-disjoint

Grouping by `mapper` is provided for future mapper-leakage checks, where the
same mapper must not appear in both folds.

### Leakage prevention details

- Groups are shuffled with a fixed `random.Random(seed)`, so splits are
  reproducible.
- Samples without a group id (`beatmapset_id` or `mapper`) fall back to their
  unique `sample_id` as their own group. This guarantees they can never appear
  in both folds.
- `validate_disjoint_split()` returns a list of overlap violations.
- Splits never stratify randomly by difficulty.

## Versioning

Manifests carry `parser_version` and `feature_version`, so a dataset can be
rebuilt reproducibly when the parser or feature extractor changes.

## Reserved training layout

See `training/README.md`: generated datasets, splits, and weak-label outputs
go under `training/datasets/`, `training/splits/`, `training/weak_labels/`
and are gitignored.
