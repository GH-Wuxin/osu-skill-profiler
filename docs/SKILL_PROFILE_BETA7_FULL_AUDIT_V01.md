# Skill Profile beta.7 全九维独立审计与修复报告 V01

审计日期：2026-09-02<br>
审计分支/基线：`main@ab394b269530174b021d76d0dcee6c1fef667429`<br>
候选实现：`0.10.0-beta.7`，仅 opt-in；默认 runtime 仍为 `0.10.0-beta.5`

## 结论

本轮不是按人工标签调参，也没有把大于 10 的结果统一裁掉。审计从 `.osu` 原始物件、
slider-aware 几何、物件间隔、局部窗口和当前代码出发，确认并修复了可泛化的计算/输出
合同问题；人工 BID 评价只在修复之后作为次级 sanity panel。

目标 BID 2719427 +HDHR 的空间结论已由旧版 `Jump 7.5708 / Flow 4.7980`
纠正为 `Jump 4.9319 / Flow 6.5765`。Flow 是四条空间轴中最高的一条。Raw Speed
仍为 `7.7881`，但证据是一个真实、很短的 63/64 ms 六边 burst；Stamina 只有
`3.2236`，因此输出已明确区分“短峰很快”和“长时间持续”。

最终冻结语料共 1,567 个任务：1,567 成功、0 failure、0 non-finite、0 provenance
违规。970 张常规队列全部九轴发出，任何轴都没有超过 10。合法极端、非 Aspire
病理图和 Aspire 对抗图分别单列；高尾只在有原始局部证据时保留。没有证据支持全局
clipping、统一压尾或按 `Aspire` 名称写特判。

## 边界与保全

- 没有修改、移动或重写原始 `.osu`、`osu!.db`、standard manifest、人工评价或既有
  calibration artifact。
- 没有部署、提交、push，也没有处理 WuxinBot 或 yumu-image。
- `main` 与 HEAD 保持不变；既有 modified/untracked 文件均保留。
- beta.1–beta.6 保持历史回放；beta.7 通过新 wrapper 接入。
- `release.DEFAULT_ALGORITHM`、CLI 默认值和 restart script 默认值仍是 beta.5。

## 冻结证据与资料地图

### 输入快照

| 输入 | SHA256 / 状态 |
|---|---|
| BID 2719427 `.osu` | `93A0C6533F58D4C64A8DC29FDE572D2B2D9082C20CEDE58EEEA7F3895E4E9F07`，64,470 bytes |
| `training/datasets/std_manifest.json` | `F3BD3FFD2CA05787ED5F5D6DEA2C5DDAEF254EB6D5BC3FA372D7CE1D0A733247` |
| `training/datasets/map_demand_bid_review_v01/human_responses.jsonl` | `03A6DEF67800B4833C5CDB9F5406D7B5B55ED76ED24BB01B662D274D7FD2E157` |
| 冻结任务文件 | file SHA256 `8D8C1033DAECBB90C4315F90010CBAA51FCF9D0E9E99906F885958E26B60786D`；canonical task content SHA256 `29ca2d9a6b59f3e316aacaed03cc9143192164af44ce851ec8c9d88e20abb28d` |
| `osu!.db` | 审计期间持续变化；最终一次只读观察为 `B110FFDF0144B98CE650668B6A347AFC0D6E7F59F3FDBDA8F96810515526816B` |

`osu!.db` 在同一审计期间曾出现多个不同摘要，因此最终全量复跑没有重新抽样，而是只用
已经冻结的 1,567 个绝对 path + mods 任务。数据库只用于冻结前的样本/诊断星数来源，
不进入 beta.7 九轴公式。

### 实际资料流

```text
.osu bytes
  -> parser/osu_parser.py
  -> parser/normalized.py（历史 Feature 兼容视图）
  -> signals/extractor.py + signals/slider.py + signals/path.py
       Local Signal 0.4，slider path / lazy travel / minimum jump / timing
  -> model_v010_beta7.extract_from_path
       AR 缺失时局部 materialize AR=OD；应用 mods；补齐物件头坐标；绑定 rows digest
  -> paired_transition_geometry_v01
       head/full、minimum/minimum、lazy/full、full-path/full-time 四个明确阶段
  -> spatial_axes_v02 + tapping_axes_v02 + reading_order_v02
  -> profile_semantics_v01
       九轴状态、单位、置信度、同单位 summaries、peak-axis descriptor
  -> beta.7 public envelope
```

`LOCAL_SIGNAL_CONTRACT_V03` 修正了 slider span/repeat、总持续时间和 nested timing；当前
Local Signal 0.4 再由 V04 修正 compound Bezier 重复 red-anchor 的分段展开。V03 仍可回放，
beta.7 明确要求自身提取的 Local 0.4 rows，不能把历史 rows 静默当成当前输入。

ppy 本地参考用于核对语义边界，而不是直接复制总难度公式：

- `OsuDifficultyHitObject` 把 adjusted delta 下限设为 25 ms，并明确区分
  `LazyJumpDistance`、`MinimumJumpDistance`、`MinimumJumpTime`、slider travel；
- Flow evaluator 使用角度、速度、slider travel 和完整路径关系；
- Speed evaluator 用 `1 - doubleTapFeasibility` 降低可 double-tap 证据。

## 真实继承链

```text
model_decoupled_v01
  -> model_v010_beta1   仅发布身份/阶段提升，数值基底仍是 decoupled
  -> model_v010_beta2   替换 Stamina / Precision / Finger 局部 measure
  -> model_v010_beta3   再替换 Precision
  -> model_v010_beta4   在 beta2 current-basis 上替换 Control
  -> model_v010_beta5   替换 Reading
  -> model_v010_beta6   用 Local 0.4 aim routing 替换 Jump / Flow，其他轴继承 beta5
  -> model_v010_beta7   继承 beta6 输出 envelope，但九轴全部由独立 beta7 measure 替换
```

这条链不是“每版全部重算”。尤其 beta.5 的 Jump/Flow 仍来自 decoupled 证据门和全图总星
anchor；beta.6 只改 Jump/Flow 路由；beta.7 才真正让九轴都不再以总星作为数值输入。

另一个历史风险是 beta.2 `_events` 先读取 `ls.adjusted_delta_time_ms`，随后又用 raw
`ls.delta_time_ms` 覆盖 cadence。历史模块保持不动；beta.7 tapping timeline 重新定义了
adjusted execution time、真实 wall time和结构分隔。

## BID 2719427 +HDHR 的原始证据

### 谱面事实

- manifest：BPM 158，AR 9.5，OD 9，CS 4；1,202 个物件、390 sliders。
- 唯一红 timing point 为 `-2418,379.746835443038,...`，即约 158 BPM。
- Raw winner 的源文件行：

```text
1162: 166,47,133531,53,8,0:3:0:0:
1163: 156,61,133594,1,8,0:3:0:0:
1164: 142,71,133657,1,8,0:3:0:0:
1165: 126,76,133721,1,4,0:3:0:0:
1166: 109,75,133784,1,4,0:3:0:0:
1167: 93,68,133847,1,4,0:3:0:0:
1168: 80,56,133911,2,0,B|45:25|45:25|79:106,1,120.000001001358,...
```

相邻时间差是 `63/63/64/63/63/64 ms`，对应 158 BPM 的约 1/6 拍。七个头沿连续
坐标方向移动，最后一个是 slider head；这里没有 spinner、同刻物件、slider tail 伪装
点击或跨 section 拼接。

### 旧值为什么会是 Jump 7.6 / Flow 4.8

beta.5 对 HDHR 使用的 NM 星 anchor 为 `7.380159378051758`，结构 mod transform 后为
`7.8229689407348655`。它的旧 Jump support 为 `0.8813218`，主要来自全图独立 p99：

- distance p99 `399.4596 px`；
- velocity p99 `2.4596 px/ms`；
- `kinematic_peak = 0.8813218`。

旧实现把这些全图分位门送入 `_axis_value`，并对 Jump/Flow 使用
`mechanic_scale = anchor`。距离与速度并不要求来自同一 transition，局部几何也没有以
一致 phase 闭合，所以高总星 + 宽松的全图 p99 support 被直接解释成 Jump `7.5708`。

旧 Flow support 只有 `0.5978670`：严格 chain p90 长度 4、chain share 0.1108，随后又受
wide-jump morphology 影响。它同样再乘总星 anchor，得到 `4.7980`。这不是从实际连续
slider-aware 路径直接计算的 Flow 物理量，因此同一张低 BPM 高难 Flow 图会呈现
“Jump 高、Flow 低”的倒置。

### 修复后结果

| 轴 | beta.5 | beta.6 | beta.7 |
|---|---:|---:|---:|
| Jump Aim | 7.570849 | 5.735739 | 4.931940 |
| Flow Aim | 4.798019 | 7.818549 | 6.576521 |
| Aim Control | 4.748814 | 4.748814 | 5.205040 |
| Spatial Precision | 6.359273 | 6.359273 | 3.218745 |
| Raw Speed | 4.206704 | 4.206704 | 7.788072 |
| Stamina | 3.136401 | 3.136401 | 3.223619 |
| Endurance | 5.233363 | 5.233212 | 6.250383 |
| Finger Control | 5.825372 | 5.825372 | 5.836413 |
| Reading | 6.075398 | 6.075398 | 4.745921 |

beta.7 Flow winner 为 48-event、4,037–10,493 ms 的完整路径窗口：linked pair mass
`6.2236`、effective pairs `17.7816`、coherence `0.5062`、persistence 约 1。Jump 则由
同一 transition 内联合距离/时间的 8-event 窗口计算，不再允许独立 distance p99 与
velocity p99 拼接。空间四轴顺序为 Flow 6.5765 > Control 5.2050 > Jump 4.9319 >
Precision 3.2187。

Raw 7.7881 的 winner 正是 133,531–133,911 ms 六边，15.789/s、effective pairs 6、
double-tap feasibility 0。它是合法短峰，不应为了让最终类型写成 Flow 而人为压低。
新的 archetype 因而仍显示 `RAW_SPEED_DOMINANT / LOW`，但 descriptor 明确为
`PEAK_LOCAL_DEMAND_AXIS_DESCRIPTOR_NOT_PREDOMINANT_MAP_STYLE`；它不是“谱面主体类型”真值。

## 确认的通用根因与修复

### 四个空间轴

- Jump：必须在同一 transition 内联合距离与时间；移除 distance-only floor；连续
  persistence 只累计有效强度，零强度 filler 不再冒充重复证据。
- Flow：使用 full-path/full-time slider-aware 几何和连续 angle/spacing/time 权重；
  availability 与 coherence 分离。后续 corpus P1 还确认旧候选会把大量彼此不连续的弱
  转向逐点累加，现改为同 section 相邻有效权重乘积 `w[i-1] * w[i]`。
- Control：只用 minimum-distance / minimum-jump-time 的同阶段配对，不再混接 head
  distance 与 minimum time。
- Precision：只接受小目标 tolerance loss 或同一 minimum/minimum phase 的大移动后
  微修正；普通 CS4 高速流不再仅因 acquisition speed 被抬成 Precision。

### Tapping、持续和 Reading

- Raw：exact-simultaneous group 与两侧边界被隔离，不能利用官方 25 ms adjusted floor
  伪装成有序点击；实际正间隔小于 25 ms 仍是合法 adjusted-time 证据。
- Raw：原 extractor 已提供 `ls.double_tap_feasibility`，旧链没有消费；现在按 ppy 语义
  只在 Raw winner 内施加 `1 - feasibility`。missing 不能冒充 feasibility=0。
- Stamina：速率、notes、wall duration、repetition 必须来自同一 run，保持 bounded 0–10。
- Finger：cadence transition 与 local baseline 必须来自同一窗口，连续 cadence 权重替代
  脆弱硬边界。
- Endurance：真实 wall time、局部压力、恢复和 full-path movement 联合；极短样本不能
  仅凭 coverage 获得持续性地板，保持 bounded 0–10。
- Reading：一个同刻组不再令整图 abstain。该组及两侧边界仍隔离；剩余 decision coverage
  ≥0.80 时可以 `DEGRADED` 发布，无剩余合法 decision 才 abstain。

### 输出与缓存语义

- missing 与真实观察零严格分开：前者为 `INSUFFICIENT_EVIDENCE + null`。
- `score = value / 10` 明确只是显示比值，不是概率；unbounded star-equivalent 轴可以
  合法大于 1。
- summary 公开 source-axis confidences，confidence 取参与轴最弱值；缺轴为 `NONE`。
- star summaries 是独立局部峰值轴的描述性均值，不是 osu 总星或 overall difficulty。
- Stamina/Endurance 与 star-equivalent 单位不同，九轴 mixed scalar 明确拒绝发布。
- archetype confidence 受参与轴最低 confidence 封顶。旧冻结结果有 227 张被错误标成
  `HIGH`；当前 beta.7 轴级均为 LOW，descriptor 最高只能 LOW。
- beta.7 components 绑定 canonical effective mods；NM components 与 HD 分析、或相反复用
  会 fail closed；NC→DT 的合法 canonical fold 可通过。

版本身份已同步为 `spatial_axes_v0.3.0`、`tapping_axes_v0.3.0`、
`reading_order_v0.3.0`、`profile_semantics_v0.2.0`、`profile_archetype_v0.2.0`；
calibration identity 含 `spatial_3:tapping_3:reading_3:profile_semantics_2:component_context_1`，
不会复用修复前 artifact。

## 全九维冻结 corpus 审计

四个互斥队列如下：

1. 常规 only：只因 deterministic systematic sampling 入选；
2. 合法极端：源文件合法，但因旧轴高尾、总星/BPM/CS 等尾部原因入选；
3. non-Aspire pathological：格式、时间、长度、重复或其他病理标签；
4. Aspire/adversarial：单独的算法压力集，不参与普通尺度校准。

单元格为 `p99 / max / >10 数量`：

| 轴 | 常规 only (970) | 合法极端 (271) | non-Aspire pathological (312) | Aspire (14) |
|---|---:|---:|---:|---:|
| Jump | 8.1302 / 9.4089 / 0 | 11.4193 / 13.3151 / 16 | 35.3221 / 160.5754 / 10 | 28.8385 / 29.1367 / 5 |
| Flow | 7.1492 / 8.8408 / 0 | 9.3788 / 10.6606 / 1 | 10.5330 / 10.8215 / 6 | 7.2891 / 7.2927 / 0 |
| Control | 7.2256 / 7.6870 / 0 | 8.9705 / 14.4275 / 1 | 11.2706 / 17.9428 / 4 | 13.6826 / 13.9387 / 3 |
| Precision | 3.8707 / 4.7141 / 0 | 6.4127 / 9.0991 / 0 | 4.3227 / 6.9362 / 0 | 4.2501 / 4.2834 / 0 |
| Raw | 8.0029 / 9.9816 / 0 | 14.1042 / 18.0069 / 29 | 15.5942 / 22.5538 / 31 | 7.2082 / 7.2724 / 0 |
| Stamina | 4.6268 / 6.7578 / 0 | 8.1203 / 9.0757 / 0 | 7.8610 / 9.3672 / 0 | 4.7124 / 4.8065 / 0 |
| Endurance | 6.1713 / 7.3237 / 0 | 7.6754 / 8.1530 / 0 | 8.2152 / 8.4401 / 0 | 6.1005 / 6.1678 / 0 |
| Finger | 6.2823 / 8.5357 / 0 | 9.9232 / 14.7576 / 3 | 8.4567 / 10.8876 / 1 | 9.3655 / 9.8486 / 0 |
| Reading | 6.7207 / 9.3353 / 0 | 9.1823 / 9.9022 / 0 | 8.5253 / 11.0707 / 1 | 7.7548 / 7.7932 / 0 |

九轴全发出数分别是 970、269、285、14；任一轴 abstain 的谱面由 45 降为 29。Reading
旧有 32 个 abstention，修复后为 16：恢复 16、没有新增丢失。恢复的同刻图均以
`DEGRADED` 发布。剩余 Reading abstention 是 2 张无 non-spinner、14 张无有效 decision；
其他轴的 abstention 也都保留结构化 reason 和 null，而不是残留数字。

### 为什么没有统一压尾

- 常规队列九轴全部 ≤10，未发现常态尺度爆炸。
- `Xeroa [PREON]` Flow 10.6606：31-event/1.495 s winner，linked mass 13.2519、
  effective pairs 37.8627、coherence 0.7899，是集中连续链。
- `Hightechnological 1.1x` Flow 10.8215：48-event/3.477 s，linked mass 17.2614、
  effective pairs 49.3183，有明确持续路径证据。
- `GHOST [FourSeasonsHotel]` Flow 10.6574：48-event/3.749 s，linked mass 13.4116；
  高尾在修复后的相邻链定义下仍成立。
- `Scattered Faith [Taboo]` Raw 18.0069 来自 68 pairs/2.684 s、约 25.3/s；
  `Chujother` Raw 22.5538 来自 37 个有效 pair、约 31.2/s。它们不是同刻污染。
- `POSSESSION` Finger 14.7576 仍成立：73 个 transition/5.684 s，真实 13/14 ms→25 ms
  adjusted cadence 与 92/197 ms 节奏切换共存。
- `Flashbacklog [V]` Jump 160.5754 来自源文件字面 `3.3e12` slider length；Reading
  11.0707 也位于同一病理图。两者保持有限并反映输入，但不代表正常难度尾。

对 BID 764517 +HDDT 的二次 P1 复核说明为什么要修通用公式而不是裁数：旧候选 Flow
3.2566 由 11.7 秒内 48 个彼此弱连接转向逐点累加而来；相邻乘积链修复后为
1.9171。变形测试中相同 individual weight 总量，集中链 Flow 6.8462，摊薄链为 0；
这保留了真正连续极端，去掉的是不连续弱证据的数量堆积。

## Aspire 单独压力集

Aspire 14 张全部计算成功、全部九轴可用、没有 non-finite。最大值：Jump 29.1367、
Flow 7.2927、Control 13.9387、Precision 4.2834、Raw 7.2724、Stamina 4.8065、
Endurance 6.1678、Finger 9.8486、Reading 7.7932。

其中 5 张 Jump >10、3 张 Control >10；这些值只说明极端 BPM、重复、几何和时间线下
公式仍能给出有限、可追溯结果。Aspire 不参与常规阈值、分位或尺度结论，也不会因名字
触发模型特判。需要注意的是，`pathological/aspire_like` 当前属于外层 audit selection
provenance；若下游展示极端输入，必须保留这一队列上下文，不能把 29 Jump 当成普通尾。

## 人工评价的角色

人工文件共 64 条 assisted response、55 个 BID、60 个唯一 path/mods；全部来自同一 reviewer，
且可见当时算法值，25 条还是旧八轴 schema。它不适合拟合公式或否决极端图，只适合在
独立修复后找反例。详细去重与约束见 `SKILL_PROFILE_BETA7_HUMAN_SECONDARY_AUDIT_V01.md`。

Flow 修复后的 30 个去重可比人工点：MAE 0.8632、median AE 0.7374、bias +0.4029、
Spearman rho 0.8320。该结果只作次级一致性描述，不改变以上原始证据结论。

## 验证与可重放产物

- 相关单元/集成/变形测试：128/128 通过；启用本地真实谱面 corpus 后仍为 128/128。
- 全仓 discovery 共发现 713 tests；其中 6 个错误全部来自既有 retest harness 尝试在
  `training/datasets/retest_v01/smoke/TEST_ONLY` 写入或删除用户数据时的 Windows
  `PermissionError`，另有 1 skip。它们不经过 beta.7 计算链；未修改或清理该目录。
- 最终冻结复跑：1,567/1,567 OK，0 failure、0 non-finite、0 provenance violation。
- `results.jsonl` SHA256：`A5357AE6FB0CFA6362FBB7252C7D83D09E0ED6A4669AA6D7E078A9C50D62D0C1`。
- `summary.json` SHA256：`0B67AD87AC8A4A44D601ECB8DE374F616A831AB1E89A5C96383A50BC924ABAD5`。
- `cohort-summary.json` SHA256：`A116FC1ECC89E3E990384BE9BBB50CD3F900C8D1D62022C6A73DAADF2AD4FCF4`。
- 目标 +HDHR 输出 SHA256：`6785F92301B9C07C5AD9C81BBCC616169526C172ED6E47DE53E57F6A7D0577B1`。

最终 artifact：本地 Codex visualization `profile-audit-beta7-final-v3`（未纳入仓库）。

## 剩余限制

- star-equivalent 绝对尺度仍为机制启发式，需要更多独立盲测；当前 LOW confidence 是有意的。
- stacking、完整玩家 cursor trajectory 和真正 2B/chord 技术仍未建模。
- Aspire/病理 provenance 目前在外层审计数据，不在单张模型输出中自动判别。
- `Flashbacklog [V]` 的 Reading 11.0707 不是同刻污染，但 winner 是同 head 坐标、路径极
  复杂的 slider 序列；slider 尾到下一 head 的 relocation 应归 Reading 多少，保留为
  non-Aspire pathological 的 P2 语义 probe，不作为普通分布 blocker。
- 本轮 corpus 是高信息/尾部加权的冻结审计样本，不是全 Songs 目录的概率抽样。
- beta.7 尚未部署或切默认；进入 runtime 前仍应进行独立 review 与显式 release 决策。
