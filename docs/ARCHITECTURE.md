# Architecture

## Pipeline

```text
.osu text
  -> parser/            Beatmap (deterministic, validated)
  -> parser/normalized  NormalizedBeatmap (object-level numeric view)
  -> features/          FeatureExtractor (map-level and segment-level measurements)
  -> signals/           LocalSignalExtractor (per-object v0.3 observable `ls.*` signals)
  -> reference/         Official Reference layer v0.2 (`ref.ppy.*`, REFERENCE_ONLY)
  -> segments/          fixed-time or fixed-count segmentation
  -> dataset/           manifest + leakage-safe splits (data science layer)
  -> weak_supervision/  weak-label prototype + Weak Evidence Infrastructure v0.1
  -> active_learning/   pairwise annotation / HUMAN evidence contracts v0.1
  -> models/            SkillProfiler interface + deterministic baseline
  -> schema/            public output + annotation contracts
  -> cli/               user-facing commands
  -> evaluation/        future evaluation metrics (contract only)
```

## Responsibility separation

- **inference** (`models/`, `features/`, `segments/`) is the only thing a
  plain consumer needs; it has no dependency on `dataset/`, `training/`, or
  `evaluation/`.
- **dataset** (`dataset/`, `training/`) is for building and splitting data.
- **evaluation** (`evaluation/`) is for future label/model comparison.

This separation means a user who only wants a `.osu -> JSON` profile never
needs the training stack installed.

## Module responsibilities

### parser

- `osu_parser.py`: reads the `.osu` text format (metadata, difficulty,
  timing points, hit objects). Strict about malformed input; raises
  `OsuParseError`. Supports CRLF/LF, UTF-8 BOM, slider curves/repeats/pixel
  length, spinners, red (BPM) and green (SV) timing points.
- `normalized.py`: converts parsed objects into `NormalizedObject` with
  normalized coordinates (512x384), delta times, distances, movement velocity,
  angles, local BPM/SV, local density, and slider duration/velocity. The raw
  `.osu` text is never used as model tokens.

### features

- `extractor.py`: deterministic measurements only — temporal, spatial,
  slider, section, and difficulty-context groups. No ML, no skill judgement.
- `schema.py`: stable machine-readable feature catalog with units.
- `stats.py`: dependency-free descriptive statistics (mean/std/percentiles,
  Shannon entropy).

### signals

- `contract.py`: machine-readable current v0.3 `ls.*` schema (38 entries, 31
  numeric model-input signals), the frozen v0.2 schema (35 entries, 28 numeric
  model-input signals) for explicit replay, pinned upstream revision, and the
  v0.1 -> v0.2 migration table (`migration_table()`).
- `extractor.py`: per-object observable signal extraction in `.osu` file order
  with `time_sorted_index` preserved, plus fixed-time 5s segment summaries
  (mean/p90/max per numeric signal). Never emits official difficulty finals or
  skill scores.
- `path.py`: slider path geometry (linear / bezier / perfect / catmull) with
  bounded flattening guards (`MAX_PATH_CONTROL_POINTS`,
  `MAX_PATH_FLATTEN_WORK`); blocked paths stay missing with provenance.
- `slider.py`: slider velocity/duration, nested tick/repeat/tail events, and
  the follow-circle lazy cursor simulation (lazy end position, lazy travel
  distance/time), with span/tick guards for pathological sliders.

### reference

- `ppy/contract.py`: machine-readable Official Reference contract v0.2
  (`ref.ppy.*`; v0.1 replayable). Every value is `OFFICIAL_REFERENCE`,
  `reference_only`, `never_ground_truth`, `model_input_safe=false`.
- `ppy/preprocess.py` / `ppy/evaluators.py` / `ppy/diff_utils.py`:
  independent reimplementation of the pinned ppy/osu per-object evaluators
  (commit `b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`, difficulty version
  `20260706`). No final difficulty, strain, star rating or PP is computed.

### segments

- `fixed_time.py`: non-overlapping fixed-duration windows aligned to the
  first object; empty windows omitted.
- `fixed_count.py`: consecutive chunks of a fixed number of objects.
- `aggregator.py`: map-level features from segment features
  (mean/std/max/p90 per numeric key).
- `base.py`: the `Segment` dataclass and `SegmentStrategy` protocol, so new
  strategies can be added without touching consumers.

### taxonomy

- `v0.json`: machine-readable provisional taxonomy (see
  [TAXONOMY_V0.md](TAXONOMY_V0.md)).

### dataset

- `manifest.py`: manifest validation and optional SHA-256 checksum
  verification without embedding beatmap files in git.
- `split_v01.py`: canonical v0.1 split implementation — SHA-256-ranked
  components, train/val/test (80/10/10), set/mapper/strict disjoint variants,
  duplicate checksums always unioned. `split.py` is the legacy compatibility
  module and is not used to generate the audited v01/v02 artifacts.

### weak_supervision

- `base.py`: `WeakLabelRule` protocol, `WeakLabelResult`,
  `WeakLabelEvidence` with full provenance (legacy prototype surface).
- `rules.py`: three deliberately conservative demo rules (extreme spacing,
  long dense section, rhythm irregularity), confidence <= 0.35.
- `engine.py`: applies rules, computes an input checksum, and persists
  versioned weak-label JSON.
- `contracts_v01.py` / `registry_v01.py` / `pilot_v01.py` /
  `runtime_v01.py` / `audit_v01.py` / `leakage_v01.py` / `v01.py`: Weak
  Evidence Infrastructure v0.1 — versioned propositions/sources/rules,
  lineage DAG, first-class abstention, strict finite serialization, and the
  leakage-gate bridge. Weak evidence is never a label or ground truth.

### active_learning

- `contracts_v01.py`: versioned `AnnotationTask` / `AnnotationResponse` /
  `HumanEvidenceRecord` contracts, first-class `CANNOT_JUDGE`, orientation
  canonicalization and a fail-closed response ledger.
- `selection_v01.py` / `batch_v01.py`: deterministic acquisition scoring and
  pairwise batch construction with explicit controls.
- `presentation_v01.py` / `human_presentation_v02.py`: blind presentation
  contracts/eligibility (weak evidence, split/challenge and control metadata
  are never shown).
- `human_pilot_v01.py` / `human_pilot_v02.py` /
  `collection_analysis_v01.py`: pilot preparation, response storage and
  content-addressed collection snapshots. `human_training_guard_v01.py`
  fails closed unless an exact response artifact is explicitly training
  eligible. HUMAN evidence is never ground truth.

### schema

- `output_schema.py`: public profile JSON schema (schema/taxonomy/model
  versions, beatmap, features, skills, segments, weak labels).
- `annotation_schema.py`: future human annotation contracts.
- `validate.py`: minimal JSON-Schema subset validator (stdlib only).

### models

- `base.py`: `SkillProfiler` protocol (`analyze_map`, `analyze_segments`).
- `baseline.py`: `DeterministicBaselineProfiler` — pipeline smoke test that
  always reports `status: "not_inferred"` and `BASELINE / NOT TRAINED / NOT
  GROUND TRUTH`.

### evaluation

- `metrics.py`: pure regression/ranking/classification metrics for future
  evaluation once real labels and a trained model exist. No accuracy claims.

## Determinism

All phases are pure functions of their inputs:

- parser output depends only on the file bytes;
- features depend only on the normalized representation;
- segmentation depends only on the chosen strategy parameters;
- weak labels depend only on features, segments, and rule definitions;
- JSON output uses `sort_keys=True`, so two runs of the same command on the
  same file produce byte-identical output (covered by tests).

## Non-goals (current phase)

- No trained model, no fabricated accuracy, no human labels, no annotation
  backend, no cloud service, no crawler, no WuxinBot integration, no final
  taxonomy decision.
- No official difficulty final, no star-rating / PP clone: Local v0.3 emits
  only observable `ls.*` signals, and Reference v0.2 emits only
  `OFFICIAL_REFERENCE` `ref.ppy.*` values; reference-only official concepts
  never enter the observable feature contract.
