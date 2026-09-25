# osu-skill-profiler — Formal Map Demand v0.40

[简体中文](#简体中文) · [English](#english)

## 简体中文

当前 GitHub 发布线是 **Formal Map Demand v0.40.0**。仓库默认算法、BID 评审台和
`/w skill` 使用的本地 HTTP 服务都指向同一个发布身份：

```text
algorithm_id:       FORMAL_MAP_DEMAND_V040
map_demand_version: 0.40.0
release_id:         formal-map-demand-v0.40.0
```

v0.40 输出九个谱面需求维度：`Jump Aim`、`Flow Aim`、`Aim Control`、
`Micro Precision`（键 `spatial_precision`）、`Raw Speed`、`Finger Control`、
`Reading`、`Stamina` 和 `Endurance`。前七个维度使用星级等价值尺度，
`Stamina` 与 `Endurance` 使用 `0–10` 有界尺度。它们描述谱面需求，不是玩家能力，
也不替代 osu! 官方总星数、pp 或实际游玩体验。

### v0.40 的 Slider pressure

v0.40 在 ppy Slider 几何与时序信号上运行有边界的全图扫描，并保留可审计的向量：

- `mandatory_cursor_travel_norm_px`：强制光标移动量；
- `active_follow_fraction`、`longest_active_episode_ball_path_norm_px`：连续跟随支撑；
- `required_cursor_velocity_norm_px_per_ms`：所需光标速度；
- `mean_tracking_slack_fraction`、`residual_steering_25px_rad`、
  `residual_steering_50px_rad`：余量与转向证据；
- `lazy_negative_controls`：球速高但光标需求低的负对照。

公开的 `slider_pressure.scalar` 只定义为：

```text
support-gated sustained candidates 中的最大 required cursor velocity
```

它不是加权星数，也不是玩家分数。候选需要通过至少 `50` normalized px 的强制移动量
和至少 `100` normalized px 的连续跟随路径门槛。没有足够证据时，结果会保留为未通过发布门，
不会补造数值。

### 发布边界

- 这是**谱面侧**发布；玩家能力分数明确不进入输出；
- Classic replay 校验继续作为独立的玩家 Slider 判断边界，不会被地图分数冒充；
- 默认扫描是有边界的，不要求扫描整个 Songs 库；
- 不要求用户亲自游玩，不播放音频；
- 只有本地 `.osu`、打包校准和版本化发布清单同时存在时，九维与 Slider pressure 才会进入正式发布结果；
- `training/formal_slider_release_v040/verification_v040.json` 保存了五个固定 fixture、输出契约和校验结果；
- `training/ppy_slider_replay_validation_v035/` 保存独立 Classic trace 审计，不能把 mismatch 或 timeout 当作精确通过。

### 快速开始

要求 Python 3.10 或更高版本：

```powershell
git clone https://github.com/GH-Wuxin/osu-skill-profiler.git
cd osu-skill-profiler
python -m pip install -e .
```

对单张 `.osu` 生成基础画像：

```powershell
osu-skill-profiler profile-map "path\to\map.osu" --no-weak-labels --out profile.json
```

用 v0.40 生成正式九维与 Slider pressure：

```powershell
python tools/map_demand_v01/cli.py analyze `
  --map "path\to\map.osu" `
  --calibration-dir "training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k" `
  --mods HD DT `
  --algorithm v040-formal `
  --out demand.json
```

不传 `--algorithm` 时，CLI 使用本地运行选择；新安装默认是 `v040-formal`。
旧版本仍可显式回放，但不会改变 v0.40 的默认身份。

### 启动 `/w skill` 使用的本地服务

服务固定监听 `127.0.0.1:8767`。准备好标准 manifest、osu! Songs 目录和打包校准后，运行：

```powershell
$env:OSU_SONGS_ROOT = "G:\osu! 20210821\Songs"
powershell -ExecutionPolicy Bypass -File tools/restart-skill-profiler.ps1 -Algorithm v040-formal
```

启动脚本会检查 `/api/state`，确认 `FORMAL_MAP_DEMAND_V040` 与 `0.40.0` 后才写入运行选择。
WuxinBot 的 `/w skill` 客户端读取同一个状态，并把九维、`SliderPressure`、谱面身份和发布边界
转发给群聊。服务没有成功通过状态检查时，脚本不会把旧进程伪装成 v0.40。

### 九维含义

| 维度 | 含义 | 量尺 |
| --- | --- | --- |
| Jump Aim | 距离、时间与空间移动构成的跳跃瞄准需求 | 星级等价值 |
| Flow Aim | 连续方向与速度链的瞄准需求 | 星级等价值 |
| Aim Control | 变距、变向、速度调整和滑条衔接的控制需求 | 星级等价值 |
| Micro Precision | 小目标容错、落点稳定与微修正需求 | 星级等价值 |
| Raw Speed | 快速点击与交互所需的基础速度 | 星级等价值 |
| Finger Control | 节奏切换与手指协调需求 | 星级等价值 |
| Reading | 顺序冲突、信息率、低 AR 保留和快速解码压力 | 星级等价值 |
| Stamina | 高强度局部段的持续执行需求 | `0–10` |
| Endurance | 全图时长、物量与密集覆盖下的持续需求 | `0–10` |

### 目录与证据

- [v0.40 正式发布说明](docs/FORMAL_MAP_DEMAND_RELEASE_V040.md)
- [v0.40 发布清单](training/formal_slider_release_v040/manifest.json)
- [v0.40 固定 fixture 校验](training/formal_slider_release_v040/verification_v040.json)
- [Slider pressure v0.36 扫描器](tools/ppy_v01/slider_pressure_v036.py)
- [Classic trace 独立校验器](tools/ppy_v01/verify_classic_trace_v040.py)
- [BID 评审台说明](docs/MAP_DEMAND_BID_REVIEW_UI_V01.md)

历史 beta、v0.96 和 v1.0.0 文件保留在仓库中，供可重复审计使用；它们不是当前默认发布线。

MIT。项目与 osu!、ppy Pty Ltd 或 osu! 开发团队没有隶属关系。

---

## English

The current GitHub release line is **Formal Map Demand v0.40.0**. The default algorithm, the
BID review workbench, and the local HTTP service used by `/w skill` share one release identity:

```text
algorithm_id:       FORMAL_MAP_DEMAND_V040
map_demand_version: 0.40.0
release_id:         formal-map-demand-v0.40.0
```

v0.40 emits nine map-demand axes: `Jump Aim`, `Flow Aim`, `Aim Control`, `Micro Precision`
(`spatial_precision`), `Raw Speed`, `Finger Control`, `Reading`, `Stamina`, and `Endurance`.
The first seven use osu!-familiar star-equivalent units; `Stamina` and `Endurance` use bounded
`0–10` units. These are map-demand values, not player-ability scores, official osu! star ratings,
pp, or a replacement for actually playing the map.

### Slider pressure

The release runs a bounded full-map scan over ppy Slider geometry and timing signals and keeps an
auditable vector: mandatory cursor travel, active-follow fraction and longest active episode,
required cursor velocity, tracking slack, residual steering at 25/50 px, and lazy negative controls
where ball speed is high while cursor demand is low.

The public `slider_pressure.scalar` is defined as the maximum `required_cursor_velocity` among
support-gated sustained candidates. It is not a weighted star sum and it is not a player score.
Candidates must pass the 50 normalized-pixel mandatory-travel gate and the 100 normalized-pixel
continuous-follow path gate. If the evidence is insufficient, the release gate stays closed instead
of manufacturing a value.

### Release boundary

- This is a map-side release; player-ability scoring is excluded from the output.
- Classic replay checking remains an independent boundary for player Slider judgement.
- The default scan is bounded and does not require scanning an entire Songs library.
- No user play and no audio playback are required.
- Formal values require a local `.osu`, the packaged calibration, and the versioned release manifest.
- `training/formal_slider_release_v040/verification_v040.json` records five fixed fixtures and the output contract.
- `training/ppy_slider_replay_validation_v035/` records independent Classic-trace audits; mismatch or timeout rows are not treated as exact passes.

### Quick start

Python 3.10 or newer is required:

```powershell
git clone https://github.com/GH-Wuxin/osu-skill-profiler.git
cd osu-skill-profiler
python -m pip install -e .
osu-skill-profiler profile-map "path\to\map.osu" --no-weak-labels --out profile.json
```

Generate the formal v0.40 nine-axis and Slider-pressure payload:

```powershell
python tools/map_demand_v01/cli.py analyze `
  --map "path\to\map.osu" `
  --calibration-dir "training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k" `
  --mods HD DT `
  --algorithm v040-formal `
  --out demand.json
```

When `--algorithm` is omitted, the CLI follows the local runtime selection; a fresh installation
defaults to `v040-formal`. Older releases remain explicitly replayable and do not change the v0.40 default.

### Starting the service used by `/w skill`

The service listens on `127.0.0.1:8767`. After preparing the standard manifest, an osu! Songs directory,
and the packaged calibration, run:

```powershell
$env:OSU_SONGS_ROOT = "G:\osu! 20210821\Songs"
powershell -ExecutionPolicy Bypass -File tools/restart-skill-profiler.ps1 -Algorithm v040-formal
```

The launcher checks `/api/state` and writes the runtime selection only after it sees
`FORMAL_MAP_DEMAND_V040` with version `0.40.0`. The WuxinBot `/w skill` client reads the same state and
forwards the nine axes, `SliderPressure`, beatmap identity, and release boundary to chat. If the state
check fails, the launcher does not present an older process as v0.40.

### Evidence and history

- [Formal v0.40 release note](docs/FORMAL_MAP_DEMAND_RELEASE_V040.md)
- [v0.40 release manifest](training/formal_slider_release_v040/manifest.json)
- [v0.40 fixture verification](training/formal_slider_release_v040/verification_v040.json)
- [Slider pressure v0.36 scanner](tools/ppy_v01/slider_pressure_v036.py)
- [Independent Classic-trace verifier](tools/ppy_v01/verify_classic_trace_v040.py)
- [BID review workbench](docs/MAP_DEMAND_BID_REVIEW_UI_V01.md)

Historical beta, v0.96, and v1.0.0 files remain for reproducible audits; they are not the current default release line.

MIT licensed. Not affiliated with osu!, ppy Pty Ltd, or the osu! development team.
