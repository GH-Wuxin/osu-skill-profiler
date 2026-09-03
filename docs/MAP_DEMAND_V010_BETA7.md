# Map Demand 0.10.0-beta.7 — 九维证据闭环修正版

beta.7 是 opt-in 版本，默认 runtime 仍为 beta.5。beta.1–beta.6 的模块、
Local Signal 输入版本和既有输出保持可回放；本版本只通过新的 wrapper 接入。
当前空间组件身份为 `spatial_axes_v0.3.0`，Flow 发布方法/尺度分别为
`CONTINUOUS_DIRECTIONAL_PATH_FLOW_V03` 和
`LOCAL_DIRECTIONAL_PATH_PHYSICAL_LOG_NO_TOTAL_SR_V03`；beta.7 calibration identity
使用 `spatial_3`。tapping 组件身份为 `tapping_axes_v0.3.0`，Raw Speed 发布
方法/尺度分别为 `RUN_LOCAL_RAW_SPEED_V03` 和
`INDEPENDENT_PHYSICAL_RATE_NO_TOTAL_SR_V03`，calibration identity 使用
`tapping_3`，避免复用同刻隔离与 double-tap feasibility 修复前的 frozen artifact。

## 目的与边界

beta.7 不再用 osu!.db 总星数、另一条轴、旧 percentile 或人工类型标签决定任一
九维值。osu!.db 星数只保留为诊断输入，改变 `v091_nm_star_anchor` 或旧 calibration
分布不得改变九轴结果。

本版本不把“大数”本身当作错误，也没有统一封顶或尾部压缩。审计分为四个互斥队列：

1. 普通谱面用于检查常态尺度和系统偏差；
2. 合法极端谱面用于守住真正的高难尾部；
3. non-Aspire 病理时间线用于检查异常格式/数值下的有限性和证据归属；
4. Aspire/adversarial 单独成队，用于检查可重放性、退化状态和证据闭环。

后两队都不参与普通尺度校准；Aspire 不与其他病理图合并统计，也不会触发来源名称特判。

## 输入与成对几何

beta.7 固定使用 Local Signal 0.4，并要求由自身 extractor 返回、带内容摘要的 rows
envelope。缺少 AR 的 legacy 谱面在 beta.7 提取边界内显式 materialize `AR = OD`，
因此 HD 不再因缺 AR 而静默退化；历史 extractor 和历史 artifact 不变。

`paired_transition_geometry_v01` 明确区分四个不可混接的物理阶段：

```text
head distance / full adjusted time
minimum distance / minimum jump time
lazy distance / full adjusted time
(previous slider lazy travel + current lazy jump) / full adjusted time
```

missing 与真实零距离分开。spinner、post-spinner、长间隔分段和同刻物件组会形成
结构化边界；同刻物件不再令整张图抛异常，也不会依赖文件行顺序伪造普通点击或
空间转移。

## 四个空间轴

- **Jump Aim**：同一 transition 内联合距离和时间，没有纯距离地板；局部最多八条
  transition，persistence 由连续同轴有效强度之和计算，零强度 filler 不能冒充
  重复证据。
- **Flow Aim**：使用 slider-aware 完整路径、连续角度/间距/时间权重，以及同一
  section 内相邻有效转向的乘积链；孤立或摊薄的弱转向不能只靠窗口数量累计。
  availability 只描述数据是否可用，不再与 coherence 混成路由开关。
- **Aim Control**：只使用 minimum/minimum 同阶段的间距、速度和 cadence 状态变化；
  不再把 head distance 与 minimum time 拼接。
- **Spatial Precision**：只接受相对 CS4 参考目标的有符号 tolerance loss，或同一
  minimum/minimum 阶段的大移动后微修正；普通 CS4 高速移动本身不是 Precision。

四轴 coverage 使用同一状态合同：`>= 0.95 FULL`、`0.80–0.95 DEGRADED`、
`< 0.80 INSUFFICIENT`。这是证据可用性门，不是难度门。

## tapping、持续与 Reading

- **Raw Speed**：在同一有序点击 run 内，以 adjusted execution time 计算局部点击
  峰值；spinner、post-spinner 和 exact-simultaneous group 断开 run，长度、速率和
  repetition 不能跨段借用。短 burst 可以很高，但其 evidence count、support 和
  repetition 必须同时公开。
- **Stamina**：速率、有效 notes、真实 wall duration 和 repetition 必须来自同一
  run；输出是 bounded 0–10 trait。
- **Finger Control**：节奏转移与 local baseline 绑定在同一时间窗口，不能从另一段
  匀速流借 baseline；cadence 权重连续，不保留旧硬边界。
- **Endurance**：真实 wall time、持续压力、恢复比例和 full-path/full-time movement
  联合；极短输入不会仅凭 coverage 获得非零地板；输出是 bounded 0–10 trait。
- **Reading**：保留 v1 的局部顺序、可见头、HD memory 与 relocation 核心，但加入
  coverage/status；缺 AR/preempt 和无有效 decision 会 abstain。exact-simultaneous group
  及其两侧因果边从核心隔离；若其余 decision coverage 仍达 0.80，Reading 最多以
  `DEGRADED / ISOLATED_SIMULTANEOUS_ORDER` 发布，否则 abstain。missing 不显示成 0。

## Profile 语义

七条 star-equivalent 轴为 Jump、Flow、Control、Precision、Raw、Finger、Reading；
Stamina 与 Endurance 是 bounded 0–10 auxiliary traits。beta.7 只发布同单位 summary：

- `aim_star_summary`；
- `tapping_star_summary`；
- `primary_star_summary`；
- `bounded_sustain_summary`。

九轴混合 scalar 明确返回 `NOT_PUBLISHED_MIXED_UNITS`，不再把两种单位直接平均。
轴级 missing 为 `INSUFFICIENT_EVIDENCE + null`，真实观察到的低需求才允许为 0。
archetype completeness 只以七条参与竞争的 star 轴为分母，Stamina/Endurance 作为
辅助 trait 单独报告。

`score` 统一定义为 `value / 10` 的显示比值，不是概率或置信度；合法极端 star 轴的
`score` 可以大于 1。同单位 summary 是独立局部 peak-axis 尺度的描述性均值，不是
osu 总星或综合难度；其 `confidence` 取全部 source axes 的最低置信度，缺轴为
`NONE`。archetype 同样不得越过参与竞争轴的最低置信度，并以
`PEAK_LOCAL_DEMAND_AXIS_DESCRIPTOR_NOT_PREDOMINANT_MAP_STYLE` 明确它不是主导谱面类型
真值。

上述 publication 语义由 `reading_order_v0.3.0`、`profile_semantics_v0.2.0`、
`profile_archetype_v0.2.0` 以及 calibration token
`reading_3:profile_semantics_2:component_context_1` 标识。beta.7 components 记录
canonical effective mods，并在 analyze 时同时核对 requested/applied mod context，
防止 NM/HD 等缓存组件静默错配。

## BID 2719427 的独立结果

目标谱没有 BID 特判。+HDHR 的最终空间结果为：

| 轴 | beta.5 | beta.6 | beta.7 |
|---|---:|---:|---:|
| Jump Aim | 7.5708 | 5.7357 | 4.9319 |
| Flow Aim | 4.7980 | 7.8185 | 6.5765 |
| Aim Control | 旧链结果 | 旧链结果 | 5.2050 |
| Spatial Precision | 旧链结果 | 旧链结果 | 3.2187 |

beta.7 中 Flow 是四个空间轴最高。Raw Speed 仍为 7.7881：它来自
133531–133911ms 的 7 个点击头、六条 `63/63/64/63/63/64ms` 合法点击边，
不是 slider 尾、spinner、同刻 floor 或跨段拼接。这个短 burst 的高峰与谱面的
主要空间机制是 Flow 并不矛盾；Stamina 3.2236 和独立的短样本 support 保留了
“快但不长”的区别。

## 已知限制

- 绝对 star-equivalent 尺度仍是机制启发式，需要更宽的独立盲测；
- stacking 和完整玩家 cursor trajectory 未模拟；
- exact-simultaneous standard 物件只做隔离/abstain，未宣称 2B/chord 模型；
- archetype 是七条 peak-demand 轴的描述，不应越过轴级证据被解释为人工谱面类型
  真值；
- 人工 BID 数据为 assisted、旧八轴且大量 skip，只能作次级 sanity panel；
- beta.7 未部署、未切默认，需显式选择 `v010-beta7`。
