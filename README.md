# osu-skill-profiler

**osu!standard beatmap skill profiling infrastructure** — a deterministic,
dependency-free foundation that turns `.osu` files into stable, versioned,
machine-readable skill profiles.

> This is **not** a trained, high-accuracy skill classifier. No skill score is
> ever fabricated, and every skill definition in this repository is
> **PROVISIONAL** until it has been validated against human data.

## What this project is

An independent, general-purpose foundation for the future data science
pipeline:

```text
.osu
  -> parser
  -> normalized representation
  -> deterministic feature extraction
  -> segment representation
  -> weak supervision / future model interface
  -> versioned skill-profile JSON
```

It is deliberately decoupled from any specific bot, website, or analysis
tool. Any downstream consumer can use the versioned JSON output without
knowing how it was produced.

## What this project is not (yet)

- Not a trained skill classifier — `DeterministicBaselineProfiler` reports
  `status: "not_inferred"` for every skill and never invents scores.
- Not a final taxonomy — the current taxonomy (`v0.0.1`) is a provisional
  hypothesis to be tested with data.
- Not an annotation website or cloud service.
- Not a crawler — the repository ships only small synthetic fixtures.

## Roadmap

```text
deterministic foundation        <- you are here
  -> weak supervision
  -> human gold/pairwise data
  -> baseline ML
  -> neural model
  -> segment-level profiling
```

Each step keeps the public JSON schema and the `SkillProfiler` interface, so
model internals can change without breaking consumers.

## Requirements

- Python >= 3.10
- No runtime dependencies
- Tests use the standard library `unittest` only

## Quickstart

Run the test suite (zero dependencies):

```powershell
python run_tests.py
```

Profile a beatmap (writes a versioned JSON document):

```powershell
python -m osu_skill_profiler.cli.main profile-map path/to/map.osu --out profile.json
```

Or, after `pip install -e .`:

```powershell
osu-skill-profiler profile-map path/to/map.osu --out profile.json
osu-skill-profiler extract-features path/to/map.osu
osu-skill-profiler extract-local-signals path/to/map.osu
osu-skill-profiler extract-reference-signals path/to/map.osu
osu-skill-profiler inspect-segments path/to/map.osu
osu-skill-profiler validate-dataset manifest.json --verify-checksums
osu-skill-profiler validate-profile profile.json
osu-skill-profiler taxonomy
```

## CLI

| Command | Purpose |
| --- | --- |
| `profile-map MAP.OSU` | versioned skill-profile JSON (features, segments, weak-label evidence) |
| `extract-features MAP.OSU` | full-map deterministic features |
| `extract-local-signals MAP.OSU` | per-object Local Signal Layer v0.3 document (observable `ls.*` signals + 5s segment summaries) |
| `extract-reference-signals MAP.OSU` | per-object Official Reference Signal document (`ref.ppy.*`, REFERENCE_ONLY, never ground truth) |
| `inspect-segments MAP.OSU` | segment representation + aggregated features |
| `validate-dataset MANIFEST` | manifest validation (optional checksum verification) |
| `validate-profile PROFILE` | validate a profile JSON against the public schema |
| `taxonomy` | print the provisional taxonomy |

## Project layout

```text
src/osu_skill_profiler/
  parser/            .osu parser + normalized representation
  features/          deterministic feature extractor + schema
  signals/           Local Signal Layer v0.3 (per-object observable `ls.*` signals)
  reference/         Official Reference layer v0.2 (`ref.ppy.*`, REFERENCE_ONLY)
  segments/          fixed-time / fixed-count segmentation + aggregation
  taxonomy/          machine-readable provisional taxonomy (v0)
  dataset/           dataset manifest + leakage-safe splits (split_v01 is canonical)
  weak_supervision/  weak-label prototype + Weak Evidence Infrastructure v0.1
  active_learning/   versioned pairwise annotation + HUMAN evidence contracts v0.1
  schema/            public output / annotation schemas + validator
  models/            model interface + deterministic baseline profiler
  evaluation/        future evaluation metrics (contract only)
  cli/               command-line interface
training/            reserved layout for future datasets / splits / weak labels
tests/               unit tests + synthetic fixtures
docs/                design and contract documentation
```

## Guarantees

- **Deterministic**: the same input produces byte-identical output on every
  run.
- **No fabricated scores**: without a trained model, every skill is
  `not_inferred` with `score: null`.
- **No hidden ground truth**: weak labels are marked `WEAK LABEL != GROUND
  TRUTH`, carry provenance, and never leave the repository as if they were
  human labels.
- **No WuxinBot coupling**: no bot-specific logic, configuration, or
  dependency.

## Documentation

- [docs/TAXONOMY_V0.md](docs/TAXONOMY_V0.md) — provisional skill axes
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — pipeline and module design
- [docs/FEATURES.md](docs/FEATURES.md) — feature catalog and units
- [docs/DATASET.md](docs/DATASET.md) — manifest and split contracts
- [docs/ANNOTATION_SCHEMA.md](docs/ANNOTATION_SCHEMA.md) — future human annotation contracts
- [docs/MODEL_INTERFACE.md](docs/MODEL_INTERFACE.md) — model/output/evaluation contracts

- [docs/LOCAL_SIGNAL_CONTRACT_V03.md](docs/LOCAL_SIGNAL_CONTRACT_V03.md) - current v0.3 per-object observable signal contract
- [docs/LOCAL_SIGNAL_CONTRACT_V02.md](docs/LOCAL_SIGNAL_CONTRACT_V02.md) - historical v0.2 contract (frozen, replayable)
- [docs/PPY_REFERENCE_SIGNAL_CONTRACT_V02.md](docs/PPY_REFERENCE_SIGNAL_CONTRACT_V02.md) - current v0.2 Official Reference contract
- [docs/PPY_PARITY_REPORT_V02.md](docs/PPY_PARITY_REPORT_V02.md) - golden parity vs pinned ppy/osu
- [docs/FEATURE_MIGRATION_V01_TO_V02.md](docs/FEATURE_MIGRATION_V01_TO_V02.md) - v0.1 -> v0.2 migration policy
- [docs/archive/LOCAL_SIGNAL_V02_FINAL_REPORT.md](docs/archive/LOCAL_SIGNAL_V02_FINAL_REPORT.md) - historical v0.2 implementation report (archived)
- [docs/HUMAN_ANNOTATION_CONTRACT_V01.md](docs/HUMAN_ANNOTATION_CONTRACT_V01.md) - current human annotation contract
- [docs/MAP_DEMAND_ATOMIC_V05.md](docs/MAP_DEMAND_ATOMIC_V05.md) - V0.7 relative-AR, HD interaction, Flow/Aim transfer, and sustained-clicking revision
- [docs/MAP_DEMAND_ATOMIC_V06.md](docs/MAP_DEMAND_ATOMIC_V06.md) - V0.8 nine-axis Stamina / Endurance split
- [docs/MAP_DEMAND_ATOMIC_V07.md](docs/MAP_DEMAND_ATOMIC_V07.md) - V0.9 local Finger Control and structural Reading/HD revision
- [docs/MAP_DEMAND_BID_REVIEW_UI_V01.md](docs/MAP_DEMAND_BID_REVIEW_UI_V01.md) - local BID/mod review workbench (V0.9 default)

## License

MIT (see `pyproject.toml`). This project is not affiliated with osu! or osu!
developers.
