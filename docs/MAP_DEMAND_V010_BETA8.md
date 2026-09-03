# Map Demand 0.10.0-beta.8 — 支持前沿与机制归属修正版

beta.8 是显式 opt-in 版本，默认 runtime 仍为 `v010-beta5`。本轮没有部署、
提交或推送，也没有修改 beta.7 及更早实现。它解决的不是“所有高值都压低”，而是
把瞬时物理极端、可成立的公开难度、证据可靠性和替代机制分开。

## 真实资料流与继承链

运行资料流为：

```text
.osu bytes
  -> parser/osu_parser.py
  -> parser/normalized.py + FeatureExtractor
  -> LocalSignalExtractor 0.4
  -> paired_transition_geometry_v01
  -> spatial_axes_v03 / tapping_axes_v03 / reading_order_v02
  -> model_v010_beta8
  -> profile_semantics_v02
```

代码中的真实 wrapper 链为：

```text
model_decoupled_v01
  -> model_v010_beta1
  -> beta2 -> beta3 -> beta4 -> beta5 -> beta6 -> beta7 -> beta8
```

beta.7 仍通过 beta.6 获得历史输出 envelope，同时重建九条局部证据轴；beta.8 先让
beta.7 完整分析，再只替换本版本明确声明的五轴：Jump、Precision、Raw、Stamina、
Finger。Flow、Control、Endurance、Reading 数值逐项继承 beta.7，并带显式旧合同身份。

ppy 本地实现只作为几何、时间和总星旁证，不作为任一轴的数值输入。人工 BID 评价
同样没有参与公式拟合或决定修复方向。

## Jump Aim：物理峰值与可成立值分开

每条有效 slider-aware minimum/minimum transition 的物理负担为：

```text
joint_load = sqrt(distance / (4R)) * (velocity / 1.15)
physical_star = 1.55 * joint_load^1.12
```

该变换单调、无星数上限。公开 Jump 不再等于固定八物件窗口峰值，而是显式选择：

```text
public_jump = max(establishment_frontier, recurrence_frontier)
```

`sustain`、`physical_peak` 和 `evidence_confidence` 分别保留；confidence 从不乘入
难度值。这样普通 PP 图需要连续或复现证据才能占据高标尺，而真实超高星跳仍能沿
无界物理尾部展开。

并发 active-slider transition 被排除出单光标 Jump。若排除比例达到 15%，或并发
slider 数达到 8 且排除比例达到 5%，整张图的 Jump 对该构造 abstain。超过 4096px
的 minimum-phase endpoint displacement 被视作病理 path/timing 外推并排除；这是
物理输入域检查，不是星数 cap。Black Lotus 的 74062px 异常 transition 因此不再
生成 12890 星公开 Jump，剩余有效单光标证据为 6.53。

## Raw Speed：短 burst 不再用跨段重复冒充手速图

物理峰值仍是单条 execution interval 的无界速率换算：

```text
physical_star = max(0, (1000 / execution_dt_ms - 4.5) / 1.15)
```

每条样本使用 `1 - double_tap_feasibility` 作为机制暴露权重。公开 Raw 显式选择：

```text
public_raw = max(establishment_frontier, sustain_frontier)
```

`recurrence` 只作诊断，不能把散落全图的短 burst 拼成一张持续 speed 图。短爆发仍
可有很高 physical peak，但公开值必须有同段有效 pair 数或持续时间支持。

## Precision、Stamina 与 Finger 的定向修复

beta.7 Precision 的 close-landing 项在 `distance=0` 时取最大值，会把“大跳后原地
重复”误作最强微修正。beta.8 加入零点严格为零的 displacement-presence band：

```text
(1 - exp(-(d / (0.35R))^2)) * exp(-(d / (1.60R))^2)
```

真实小幅落点仍保留，完全同坐标重复不再贡献 micro correction。CS10 Archipelago
的 9.099 几乎逐位不变，因为它由真实 target acquisition 主导。

Stamina 与 Finger 现在都使用已有 `double_tap_feasibility`：

- Stamina 的 effective pairs 以 `1 - feasibility` 加权，其他 bounded 0–10 公式不变；
- Finger 的相邻 cadence contrast 使用两端中较小的单指机制权重，即
  `1 - max(adjacent feasibility)`；
- Finger winner 同时保留未衰减 `raw_load_per_s` 与 double-tap relief 诊断；
- 没有 double-tap 信号时形成证据边界，不把 missing 冒充不可双押。

## 辅助层与对抗图路由

难度名明确含 `hitsound` 的谱面标记为 `AUXILIARY_HITSOUND_LAYER`。缩写 `[hs]`
只有在“全 circle 且所有物件同一坐标”得到结构证据佐证时才采用该标记。轴值仍留作
诊断，但 `profile_routing=EXCLUDE_FROM_ORDINARY_CALIBRATION`，避免辅助音效物件层
污染普通 Reading/Finger 标尺。

Aspire、其他病理图、并发 slider/2B、辅助层各自单列。合法极端不会因为数值大而
进入这些队列，也不会触发统一裁切。

## 关键独立复核

| 案例 | beta.7 / 旧值 | beta.8 | 结论 |
|---|---:|---:|---|
| BID 2719427 +HDHR Flow | 6.577 | 6.577 | 继承，仍为主空间轴 |
| BID 2719427 +HDHR Jump | 4.932 | 3.720 | 重复前沿成立，但显著低于 Flow |
| BID 2719427 +HDHR Raw | 7.788 | 5.240 | 物理峰 14.588；公开值来自 24 pair / 2.278s 段 |
| qiao 例图 NM Jump | 8.546 | 6.411 | 普通中段回落；物理峰 7.620 |
| mrekk 例图 +HDHRDT Jump | 10.661 | 12.443 | 超高尾展开；物理峰 13.897 |
| Clear Morning Raw | 15.785 | 9.145 | 仅 6 pair / 约 0.299s，保留高峰但不等同长流 |
| Marisa YOLO Raw | 15.722 | 15.411 | 192 pair / 约 9.56s，持续 speed 保留 |
| FAKEN Stamina | 8.304 | 3.237 | stacked double-tap 不再算纯 stamina |
| FAKEN Finger | 14.758 | 5.350 | 替代机制 relief 生效；未衰减负担仍在诊断 |
| Non-breath oblige Precision | 4.714 | 3.011 | same-position micro 漏洞关闭 |
| Archipelago Precision | 9.099 | 9.099 | 真 CS10 acquisition 尾部保留 |

BID 2719427 没有路径、BID 或人工标签特判。其 +HDHR 最终九维中 Flow 6.577 高于
Raw 5.240 和 Jump 3.720，与原始物件几何和局部节奏证据一致。

## 冻结 1567 图全九维审计

任务来自 beta.7 最终冻结 `tasks.json`；canonical task hash 为
`29ca2d9a6b59f3e316aacaed03cc9143192164af44ce851ec8c9d88e20abb28d`。

- 模型成功：1567 / 1567；
- 九维合同违例：0；
- 继承轴数值漂移：0；
- 来源 checksum 漂移：1（Daidai Genome `[Murderous]`，单列 provenance warning）；
- cohort：ordinary 968、legal extreme 254、auxiliary 19、alternative 11、
  non-Aspire pathological 301、Aspire 14。

普通组 beta.8 最大值：Jump 8.20、Flow 8.84、Control 7.69、Precision 4.36、
Raw 10.15、Stamina 6.76、Endurance 7.32、Finger 8.54、Reading 7.57。

合法极端最大值：Jump 16.84、Flow 10.66、Control 9.95、Precision 9.10、
Raw 17.83、Stamina 9.06、Endurance 8.15、Finger 10.51、Reading 9.90。

这些尾部逐张检查后都有机制证据。例如 `#WE 3 YURI` 的 Jump 16.84 来自多次独立
复现的大跨度跳，PREON 的 Flow 10.66 来自连续 31-event 高速 flow，kurukuru 的
Finger 8.54 来自 5.27 秒持续节奏对比，`#WE 3 YURI` 的 Endurance 8.15 有数分钟
有效压力覆盖。它们没有因“看起来高”而被压低。

完整逐图结果位于 `tmp/profile-audit-beta8-final-v3/results.jsonl`，汇总位于
`tmp/profile-audit-beta8-final-v3/summary.json`。

## 已知边界

- Map Demand 是谱面局部机制需求，不等于玩家能力上限；player aggregation 需要
  明确选择公开前沿，不应拿 physical peak 当能力值；
- Raw recurrence 对 63/64ms 量化片段可能显得偏高，但不进入公开 Raw；
- Stamina/Endurance 仍是历史 bounded 0–10 trait，本轮没有盲目改成无界尺度；
- Hitsound 标记是下游 cohort exclusion 信号，诊断轴没有被销毁；
- beta.8 必须显式选择 `v010-beta8`，默认仍为 beta.5。
