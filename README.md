# osu-skill-profiler

[简体中文](#简体中文) · [English](#english)

## 简体中文

**为 osu!standard 谱面建立可解释、可回放的技能需求画像。**

项目从 `.osu` 文件提取谱面结构与逐物件信号，并通过当前默认的
**Map Demand 1.0.0（冻结 Beta 9.2 的正式版）**，把谱面描述为九个相互区分的需求维度。它既提供适合下游程序消费的
版本化 JSON，也包含本地 BID/Mod 评审台，用于让算法结果持续接受真人校验。

> [!IMPORTANT]
> 1.0.0 是确定性的**启发式模型正式版**，不是 osu! 官方难度系统，也不是真值分类器。正式版冻结行为，不表示消除了所有算法偏差。
> 分数用于表达“这张谱面在哪些方面难”，不能替代总星数、pp 或实际游玩体验。

本次正式化不改变 Beta 9.2 的任何九维数值、证据或分类：保留 Raw 的支撑阈值修复、Micro Precision 目标容差，以及 Flow 的 CS4 基准尺寸重标定。历史 beta 和 V0.96 仍可显式回放。
参见 [1.0.0 发布说明、冻结合同与回放命令](docs/MAP_DEMAND_V100.md)。

### 现在能做什么

- 解析 osu!standard `.osu`，生成规范化物件、整图特征、逐物件 Local Signal 与分段摘要；
- 输出 1.0.0 九维 Map Demand 画像，并保留算法、校准、Mod 与输入校验和身份；
- 支持 NM、EZ、HD、HR、HT、DT 及其有效组合，NC/DC 分别折叠为 DT/HT；
- 九维使用本地物件证据计算；总 SR 仅作诊断参考，不作为当前九维的输入；
- 通过本地网页按 BID 找到 `.osu`、切换 Mod、查看机器结果并追加真人评价；
- 冻结回放 V0.95.3、V0.92.2、V0.91、V0.9、V0.8、V0.7、V0.6，避免算法升级后篡改旧结果；
- 为机器人、网页或图片卡片提供结构化结果，但核心仓库不耦合任何具体 Bot。

### 九个需求维度

| 分组 | 维度 | 当前含义 | 量表 |
| --- | --- | --- | --- |
| Aim | **Aim Control** | 在实际可用时间内连续完成变距、变向、速度调整及滑条衔接的控制需求 | 星级等价值 |
| Aim | **Jump Aim** | 物理移动距离与时间构成难度，支撑前沿与瞬时峰值分开；CS 主要通过 slider 几何间接影响 | 星级等价值 |
| Aim | **Micro Precision**（键：`spatial_precision`） | 小目标容错、落点稳定与大位移后的微小修正；长跳距离本身不加分 | 星级等价值 |
| Aim | **Flow Aim** | 方向连续且能维持成链的移动，保留 CS4 基准的尺寸负荷重标定 | 星级等价值 |
| Tapping | **Raw Speed** | 快速点击/交互所需的基础速度 | 星级等价值 |
| Tapping | **Finger Control** | 快速局部段中的非平凡节奏切换与手指协调 | 星级等价值 |
| Tapping | **Stamina** | 在高强度段内维持执行质量 | `0–10` |
| Global | **Endurance** | 在整张谱的时长、物量与密集覆盖下持续执行 | `0–10` |
| Reading | **Reading** | 局部顺序冲突、信息率、低 AR 保留负担、快速解码与 HD 消失记忆带来的读图压力 | 星级等价值 |

这里的“星级等价值”是便于 osu! 玩家理解的相对量尺，不表示某个单项能独立组成同星数谱面。
Stamina 与 Endurance 是有界的人类需求量表，因此不显示为星数。

### V0.96 解决了什么

V0.96 在冻结 V0.95.3 之上引入**双向证据**。维度不仅能因机制证据增加，也会因明确反证降低；
决定性的突出机制则允许超过总星数，而不是让九维都围着总星数挤成一团：

- **Micro Precision**：有效 CS4 为中性点；小目标增加容错压力，大目标明确提供 relief，settling 与 micro-correction 独立加分；
- **Jump / Control**：广义大移动证据进入 Jump Aim，稳定大跳同时成为 Aim Control 的反证；状态变化、变距与转向仍支持 Control；
- **Raw Speed**：紧凑高速峰值必须再通过链长度/持续时间门，高 BPM 短段或大跳拍速不再自动顶高；
- **Flow / Reading / Sustain**：连续形态、可见性冲突、压力覆盖和恢复分别提供正反证，缺乏机制时允许显著低于总星数；
- **人工评价降级**：旧分只作为有限连续性参考；真人分值用于宽区间、排序和主导维度检查，不作为逐图精确标杆。

完整设计与验证规则见 [Map Demand V0.96](docs/MAP_DEMAND_ATOMIC_V096.md)。

### 两层架构

```text
公开、零运行时依赖的基础层
.osu → parser → normalized map → features / local signals / segments
                                      ↓
Map Demand 层
local calibration + Mod transform → 1.0.0 nine-axis profile → review / downstream UI
```

基础层可以在全新 clone 后直接运行。Map Demand 层需要本地校准产物；训练语料、osu! Songs、
`osu!.db` 和真人反馈均不会提交到公开仓库。

### 快速开始：公开基础层

要求 Python 3.10 或更高版本。项目核心没有第三方运行时依赖。

```powershell
git clone https://github.com/GH-Wuxin/osu-skill-profiler.git
cd osu-skill-profiler
python -m pip install -e .
python run_tests.py
```

生成带版本的基础画像 JSON：

```powershell
osu-skill-profiler profile-map "path\to\map.osu" --out profile.json
```

常用基础命令：

| 命令 | 用途 |
| --- | --- |
| `profile-map MAP.OSU` | 输出特征、分段与证据组成的版本化画像 |
| `extract-features MAP.OSU` | 提取整图确定性特征 |
| `extract-local-signals MAP.OSU` | 输出逐物件 Local Signal 0.3 与 5 秒分段摘要 |
| `extract-reference-signals MAP.OSU` | 输出 `ref.ppy.*` 参考信号；它们不是真值 |
| `inspect-segments MAP.OSU` | 检查分段表示与聚合特征 |
| `validate-dataset MANIFEST` | 校验数据清单，可选文件哈希校验 |
| `validate-profile PROFILE` | 根据公开 Schema 校验画像 JSON |
| `taxonomy` | 输出暂定技能分类体系 |

### 运行 Map Demand 1.0.0

Map Demand 需要一个本地校准目录。公开仓库故意不携带语料和派生校准文件；如果你已有校准产物，
可以直接分析：

```powershell
python -m tools.map_demand_v01.cli analyze `
  --map "path\to\map.osu" `
  --calibration-dir "path\to\calibration" `
  --mods HD DT `
  --algorithm v100 `
  --out demand.json
```

`--algorithm v100` 显式选择正式版。旧版本的 `--star-anchor` 在当前版仅作诊断上下文，不影响九维。旧版结果可明确回放：

```powershell
python -m tools.map_demand_v01.cli analyze --map "map.osu" --algorithm v09
```

如果要从自己的 QA 语料构建校准：

```powershell
python -m tools.map_demand_v01.cli build-calibration `
  --local-qa "path\to\local_signal_qa.jsonl" `
  --feature-qa "path\to\feature_qa.jsonl" `
  --osu-db "path\to\osu!.db" `
  --out-dir "path\to\new_calibration"
```

输出目录必须为空。输入语料和 `osu!.db` 只在本地读取，不应提交到仓库。

### Mod 支持边界

| 状态 | Mod | 行为 |
| --- | --- | --- |
| 已变换 | `EZ` `HD` `HR` `HT` `DT` | 重算相应难度、时序或可见性信号 |
| 等价别名 | `NC` `DC` | 分别按 `DT` `HT` 进入需求计算，同时保留请求身份 |
| 对需求中性 | `NF` `SD` `PF` | 记录请求，但沿用 NM 需求画像 |
| 延后 | `FL` | 明确拒绝；未来应作为独立的 Flashlight/记忆需求维度 |
| 不支持 | `RX` `AT` `SO` `AP` `DA` `WU` `WD` `AS` `TP` | fail closed，不会静默退化成 NM |

未知 Mod、冲突组合（如 EZ+HR、DT+HT）同样会明确失败。

### 本地 BID / Mod 评审台

准备本地标准谱面 manifest、Songs 目录、`osu!.db` 和校准目录后运行：

```powershell
python -m tools.map_demand_v01.cli bid-review-ui `
  --manifest "path\to\std_manifest.json" `
  --songs-root "path\to\osu!\Songs" `
  --osu-db "path\to\osu!\osu!.db" `
  --calibration-dir "path\to\calibration"
```

默认打开 `http://127.0.0.1:8767/`。评审台会：

1. 按 BID 唯一解析本地 `.osu`；
2. 按选定 Mod 重算九维结果；
3. 显示机器结果供真人对照；
4. 将评价以 append-only JSONL 保存，并绑定算法、校准、谱面与 Mod 身份。

详细说明见 [BID Review UI](docs/MAP_DEMAND_BID_REVIEW_UI_V01.md)。

### 下游 Bot 集成

本仓库不包含 QQ 协议、账号配置或图片消息发送逻辑。WuxinBot 等下游程序可以消费九维结果，
将其渲染成图片卡片。当前 WuxinBot 侧的交互约定示例为：

```text
/w skill <BID> +HDDT
/w cd <BID> <具体维度、预期难度和理由>
```

这些命令属于下游集成，不是本仓库安装后自动提供的 CLI。

### 可靠性与边界

- **确定性与可回放**：相同输入、算法版本、校准身份和 Mod 上下文产生相同结果；旧模型不被原地改写。
- **可审计**：输出携带输入 checksum、算法、Schema、校准与 Mod 身份。
- **不把参考当真值**：`ref.ppy.*` 只用于参考和一致性检查，不直接充当人工标签。
- **不发布私人数据**：训练语料、Songs、`osu!.db`、缓存与真人反馈默认留在本地。
- **仍需真人验证**：正式版冻结了经测试选定的 Beta 9.2 行为，但极端谱、特殊 pattern、低 AR + HD 与玩家画像聚合仍可能暴露偏差。
- **只分析谱面需求**：当前不是玩家能力画像、成绩预测器、pp 计算器或推荐系统。

### 测试

完整零依赖测试：

```powershell
python run_tests.py
```

只运行当前算法、冻结回放与 Mod 相关测试：

```powershell
python -m unittest tests.test_map_demand_v096 tests.test_map_demand_v095 tests.test_map_demand_v092 tests.test_mod_context_v01 tests.test_mod_transform_v01
```

### 项目结构

```text
src/osu_skill_profiler/     公开基础层：解析、信号、特征、分段、Schema
tools/map_demand_v01/       1.0.0、历史回放、Mod 变换与本地评审工具
tests/                      单元测试与合成样本
docs/                       算法、数据、标注与契约文档
training/                   本地数据目录骨架；实际语料与派生产物不发布
```

### 关键文档

- [Map Demand 1.0.0 正式版](docs/MAP_DEMAND_V100.md)
- [Beta 9.2 冻结数值审计](docs/MAP_DEMAND_V010_BETA92_AUDIT.json)
- [Map Demand Atomic V0.91 基线](docs/MAP_DEMAND_ATOMIC_V091.md)
- [Map Demand V0.96 设计](docs/MAP_DEMAND_ATOMIC_V096.md)
- [Map Demand V0.96 实现](tools/map_demand_v01/model_v096.py)
- [Map Demand V0.95 设计](docs/MAP_DEMAND_ATOMIC_V095.md)
- [Map Demand V0.95 实现](tools/map_demand_v01/model_v095.py)
- [Map Demand V0.92.2 冻结实现](tools/map_demand_v01/model_v092.py)
- [本地 BID/Mod 评审工具](docs/MAP_DEMAND_BID_REVIEW_UI_V01.md)
- [Local Signal 0.3 契约](docs/LOCAL_SIGNAL_CONTRACT_V03.md)
- [特征目录与单位](docs/FEATURES.md)
- [架构与模块设计](docs/ARCHITECTURE.md)
- [人工标注契约](docs/HUMAN_ANNOTATION_CONTRACT_V01.md)
- [数据清单与防泄漏拆分](docs/DATASET.md)
- [V0.9 冻结回放](docs/MAP_DEMAND_ATOMIC_V07.md)

### 版本说明

Python 基础包版本（当前 `0.1.0`）、Map Demand 算法版本（当前 `1.0.0`）和输出 Schema 版本是三个独立身份。
算法升级不会伪装成旧算法结果，也不会要求同时修改稳定的基础包接口。

### 许可证

MIT。项目与 osu!、ppy Pty Ltd 或 osu! 开发团队没有隶属关系。

---

## English

**An explainable and replayable skill-demand profiler for osu!standard beatmaps.**

The repository contains two deliberately separated layers:

1. a dependency-free public foundation for parsing `.osu` files and extracting normalized maps, features, local signals, segments, and versioned JSON;
2. the stable **Map Demand 1.0.0** heuristic, freezing Beta 9.2 computation without changing any axis values, evidence, summaries, or archetypes. It retains powered Raw support selection, Micro Precision tolerance, and the CS4-relative Flow load rebase. Historical betas remain replayable. See the [1.0.0 release contract](docs/MAP_DEMAND_V100.md).

The nine axes are Aim Control, Jump Aim, Micro Precision (`spatial_precision`), Flow Aim, Raw Speed,
Finger Control, Stamina, Endurance, and Reading. Stamina and Endurance use bounded
`0–10` scales; the other axes use osu!-familiar star-equivalent scales.

The stable release is deterministic but **not ground truth**, not an official osu! difficulty
calculator, and not a player-skill model. Human review remains part of the design.

### Quick start

```powershell
git clone https://github.com/GH-Wuxin/osu-skill-profiler.git
cd osu-skill-profiler
python -m pip install -e .
python run_tests.py
osu-skill-profiler profile-map "path\to\map.osu" --out profile.json
```

Map Demand additionally requires local calibration artifacts, which are not
published with the repository:

```powershell
python -m tools.map_demand_v01.cli analyze `
  --map "path\to\map.osu" `
  --calibration-dir "path\to\calibration" `
  --mods HD DT `
  --algorithm v100
```

Supported transforms are EZ, HD, HR, HT, and DT. NC/DC fold to DT/HT; NF/SD/PF
are recorded as demand-neutral. FL is deliberately deferred, and unsupported or
conflicting Mod states fail closed instead of silently falling back to NM.

See the [V0.96 design](docs/MAP_DEMAND_ATOMIC_V096.md),
[V0.96 implementation](tools/map_demand_v01/model_v096.py),
[BID review workbench](docs/MAP_DEMAND_BID_REVIEW_UI_V01.md), and
[architecture](docs/ARCHITECTURE.md) for details.

MIT licensed. Not affiliated with osu!, ppy Pty Ltd, or the osu! development team.
