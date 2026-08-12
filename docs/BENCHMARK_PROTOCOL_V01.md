# Benchmark Protocol v0.1

Status: **FINAL** (2026-08-11)

Dataset version: `v0.1`
Split version: `0.1.0`

## 1. Purpose

The protocol defines how future model reports must present generalisation.
No single "accuracy" is acceptable. Every report must identify which
evaluation boundary produced a score, and every boundary must be verifiable
against the v0.1 split manifests.

## 2. Required reporting framework

Future model reports must report at least these benchmark regimes:

| Regime | Constraint | Manifest |
| --- | --- | --- |
| `SET_DISJOINT` | no set group crosses splits | `set_disjoint.jsonl` |
| `MAPPER_DISJOINT` | no known mapper crosses splits | `mapper_disjoint.jsonl` |
| `STRICT_SET_AND_MAPPER_DISJOINT` | no set and no known mapper crosses splits | `strict_disjoint.jsonl` |
| `LEGACY_FORMAT_OOD` | robustness on old format generations | `legacy_format_ood.jsonl` |
| `PATHOLOGICAL_CHALLENGE` | robustness on provenance-flagged extremes | `pathological_challenge.jsonl` |
| `REFERENCE_DISAGREEMENT_CHALLENGE` | robustness on observable/reference disagreement maps | `reference_disagreement_challenge.jsonl` |

`MAPPER_DISJOINT` is provisional because mapper identity is `NAME_ONLY`
(no `creator_id` in the current corpus). `STRICT_DISJOINT` inherits the same
provisionality. `UNKNOWN` mapper maps are excluded from formal
`MAPPER_DISJOINT` scoring and must not be silently merged back into the
known-mapper score; in v0.1 the corpus contains `0` unknown-mapper rows.

## 3. Required report fields (once labels/models exist)

Every model report must carry:

- `model_version`
- `dataset_version` (`v0.1`)
- `split_version` (`0.1.0`)
- `taxonomy_version` (when a taxonomy is frozen)
- sample count per benchmark and per split
- per-axis metrics (no axis may be hidden)
- confidence intervals where appropriate
- calibration curves where applicable
- abstention/coverage where applicable
- manifest checksum of the exact split files used
- seed and generator version
- leakage verification output hash

## 4. Evaluation rules

1. A benchmark claim is only valid for the manifest named in the report.
2. Training must never touch `val` or `test` maps, including
   corpus-statistic computation (fit-on-train-only).
3. `UNKNOWN` mapper maps are excluded from formal mapper-disjoint scores and
   reported separately.
4. Challenge subsets are robustness probes, not representative accuracy
   estimates; reports must say so.
5. `TEMPORAL_OOD` is `BLOCKED`; no report may claim chronological
   generalisation from v0.1 data.
6. No target may be constructed from `ref.ppy.*` while the same value (or a
   deterministic transform of it) is a model input for that prediction.

## 5. Verification before every run

Before reporting, rerun:

```text
python tools/dataset_split_audit.py verify \
  --manifest training/datasets/std_manifest.json \
  --feature-qa training/datasets/feature_qa/feature_qa_full.jsonl \
  --ref-qa training/datasets/reference_signal_qa/reference_qa_full.jsonl \
  --disagreement training/datasets/reference_signal_qa/reference_disagreement_candidates.jsonl \
  --out training/datasets/splits/v01
```

`VERIFY OK` is a precondition for any score claim. A failed verification
invalidates every score reported against that manifest version.

## 6. Reproducibility

Membership is regenerable with:

```text
python tools/dataset_split_audit.py regenerate-check \
  --manifest training/datasets/std_manifest.json \
  --feature-qa training/datasets/feature_qa/feature_qa_full.jsonl \
  --ref-qa training/datasets/reference_signal_qa/reference_qa_full.jsonl \
  --disagreement training/datasets/reference_signal_qa/reference_disagreement_candidates.jsonl \
  --out training/datasets/splits/v01
```

Passing means same-order and shuffled-order regeneration are byte-identical
for all content files.

## 7. No-score rules

This phase performs no training, no taxonomy metric implementation, no
pairwise annotation and no weak-label model. The protocol only defines how
scores will be reported later.

