# osu-skill-profiler

[简体中文](#简体中文) · [English](#english)

## 简体中文

**osu!standard 谱面技能画像基础设施**——一个确定性、零运行时依赖的基础项目，
用于将 `.osu` 文件转换为稳定、带版本且机器可读的技能画像。

> 本项目目前**不是**一个经过训练的高精度技能分类器。它不会凭空生成技能分数；
> 在经过真人数据验证之前，仓库中的所有技能定义均为**暂定（PROVISIONAL）**。

### 项目定位

本项目为后续数据科学流程提供独立、通用的基础设施：

```text
.osu
  -> 解析器
  -> 规范化表示
  -> 确定性特征提取
  -> 分段表示
  -> 弱监督 / 未来模型接口
  -> 带版本的技能画像 JSON
```

它有意与具体机器人、网站和分析工具解耦。下游应用只需消费带版本的 JSON，
无需了解其内部生成过程。

### 当前不是什么

- 不是已训练的技能分类器——`DeterministicBaselineProfiler` 会将所有技能报告为
  `status: "not_inferred"`，绝不伪造分数。
- 不是最终分类体系——当前分类体系（`v0.0.1`）只是等待数据验证的暂定假设。
- 不是标注网站或云服务。
- 不是爬虫——公开仓库仅包含小型合成测试样本，不包含训练素材。

### 路线图

```text
确定性基础设施              <- 当前阶段
  -> 弱监督
  -> 真人金标准 / 成对比较数据
  -> 基线机器学习模型
  -> 神经网络模型
  -> 分段级技能画像
```

各阶段都会保持公开 JSON Schema 和 `SkillProfiler` 接口稳定，使模型内部实现可以
持续演进而不破坏下游调用方。

### 环境要求

- Python >= 3.10
- 无运行时依赖
- 测试仅使用 Python 标准库 `unittest`

### 快速开始

运行零依赖测试套件：

```powershell
python run_tests.py
```

分析一张谱面并写出带版本的 JSON：

```powershell
python -m osu_skill_profiler.cli.main profile-map path/to/map.osu --out profile.json
```

或者先执行 `pip install -e .`，再使用命令行入口：

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

### CLI 命令

| 命令 | 用途 |
| --- | --- |
| `profile-map MAP.OSU` | 输出带版本的技能画像 JSON（特征、分段和弱标签证据） |
| `extract-features MAP.OSU` | 提取整张谱面的确定性特征 |
| `extract-local-signals MAP.OSU` | 输出逐物件 Local Signal Layer v0.3（可观测 `ls.*` 信号及 5 秒分段摘要） |
| `extract-reference-signals MAP.OSU` | 输出逐物件 Official Reference Signal（`ref.ppy.*`，仅供参考，绝非真值） |
| `inspect-segments MAP.OSU` | 输出分段表示与聚合特征 |
| `validate-dataset MANIFEST` | 校验数据清单，可选校验文件哈希 |
| `validate-profile PROFILE` | 根据公开 Schema 校验技能画像 |
| `taxonomy` | 输出暂定技能分类体系 |

### 项目结构

```text
src/osu_skill_profiler/
  parser/            .osu 解析器与规范化表示
  features/          确定性特征提取器与 Schema
  signals/           Local Signal Layer v0.3（逐物件可观测 `ls.*` 信号）
  reference/         Official Reference Layer v0.2（`ref.ppy.*`，仅供参考）
  segments/          固定时间 / 固定物件数分段与聚合
  taxonomy/          机器可读的暂定分类体系（v0）
  dataset/           数据清单与防泄漏拆分（以 split_v01 为准）
  weak_supervision/  弱标签原型与 Weak Evidence Infrastructure v0.1
  active_learning/   带版本的成对标注与 HUMAN evidence contract v0.1
  schema/            公开输出 / 标注 Schema 与校验器
  models/            模型接口与确定性基线画像器
  evaluation/        未来评估指标（目前仅有契约）
  cli/               命令行接口
training/            为未来数据集、拆分和弱标签预留的目录（训练数据不发布）
tests/               单元测试与合成样本
docs/                设计、算法与契约文档
```

### 保证

- **确定性**：相同输入在每次运行中生成逐字节相同的输出。
- **不伪造分数**：没有训练模型时，所有技能均为 `not_inferred`，且 `score: null`。
- **不冒充真值**：弱标签明确标注为 `WEAK LABEL != GROUND TRUTH`，携带来源信息，
  且不会被伪装成人工标签输出。
- **不耦合 WuxinBot**：不包含机器人专用逻辑、配置或依赖。

### 文档

- [暂定技能维度](docs/TAXONOMY_V0.md)
- [架构与模块设计](docs/ARCHITECTURE.md)
- [特征目录与单位](docs/FEATURES.md)
- [数据清单与拆分契约](docs/DATASET.md)
- [人工标注契约](docs/HUMAN_ANNOTATION_CONTRACT_V01.md)
- [谱面需求原子维度 V0.91](docs/MAP_DEMAND_ATOMIC_V091.md)
- [谱面需求原子维度 V0.9（冻结回放）](docs/MAP_DEMAND_ATOMIC_V07.md)
- [本地 BID/Mod 评审工具](docs/MAP_DEMAND_BID_REVIEW_UI_V01.md)
- [弱证据契约](docs/WEAK_EVIDENCE_CONTRACT_V01.md)

### 许可证

MIT（见 `pyproject.toml`）。本项目与 osu! 或 osu! 开发团队没有隶属关系。

## English

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
- [docs/MAP_DEMAND_ATOMIC_V091.md](docs/MAP_DEMAND_ATOMIC_V091.md) - V0.91 de-duplicated mechanics, visible overlap, and soft SR anchor
- [docs/MAP_DEMAND_ATOMIC_V07.md](docs/MAP_DEMAND_ATOMIC_V07.md) - V0.9 frozen replay
- [docs/MAP_DEMAND_BID_REVIEW_UI_V01.md](docs/MAP_DEMAND_BID_REVIEW_UI_V01.md) - local BID/mod review workbench (V0.91 default)

## License

MIT (see `pyproject.toml`). This project is not affiliated with osu! or osu!
developers.
