# Map Demand 0.10.0-beta.9 — Raw Speed 与 Micro Precision 重标定

> 历史回放说明：beta.9 的 powered support 是在线性 winner 选定后进行后处理，
> 混合速率段可能错过新目标函数下的最佳阈值。该行为为精确回放而保留；修复版本为
> `0.10.0-beta.9.1`，新结果不应再标记成 beta.9。

beta.9 只改变 `raw_speed` 与 `spatial_precision`。Jump、Flow、Control、Stamina、
Endurance、Finger Control、Reading 逐项继承 beta.8；beta.8 及更早版本保持可重放。
本轮没有使用玩家名、BID 特判、人工标签或 ppy 总星作为任一轴的公式输入。

## 计算链

```text
.osu bytes
  -> parser/osu_parser.py
  -> parser/normalized.py + FeatureExtractor
  -> LocalSignalExtractor 0.4
  -> paired_transition_geometry_v01
  -> spatial_axes_v04 / tapping_axes_v04
  -> model_v010_beta9
  -> profile_semantics_v02
```

真实 wrapper 继承链仍为：

```text
model_decoupled_v01
  -> beta1 -> beta2 -> beta3 -> beta4 -> beta5
  -> beta6 -> beta7 -> beta8 -> beta9
```

## Raw Speed：速率标尺与短 burst 支撑分开

beta.8 将 200 BPM 1/4 的完整段换算为 7.681。beta.9 将独立速率标尺改为：

```text
physical_star = max(0, (tap_rate_per_s - 5.0) / 1.30)
```

因此同一完整 200 BPM 1/4 段为 6.410。物理峰不在 10★裁尾；在正常端到端
Local Signal 管线中受 25ms execution-time floor 限制，理论最高约为 26.923★。

beta.8 对不足目标支撑的前沿使用线性插值。beta.9 只在支撑不足时改为：

```text
frontier_star = threshold_star * (support / target_support)^1.5
```

达到完整支撑时结果不变。18 taps/s、仅 7 pair 的合成 burst 中，公开 Raw 从
6.420 降为 4.044，而 10.0 的 beta.9 物理峰仍保留在诊断；持续 speed 段不会受到
这一不足支撑惩罚。

## Micro Precision：普通底座、小圈与微修正分路

beta.8 的 CS4 target-tightness 恰为零，且同点重复修复所用的 displacement band
也压掉了若干真实的小幅修正。beta.9 分成三路：

1. 普通目标只有有限底座，单事件 effort 上限为 0.45；
2. 小目标使用二维命中面积损失：

   ```text
   target_area_tightness = 2 * max(0, log2(reference_radius / radius))
   ```

   CS4 在该分支仍为零；只有明确的小圈或 HR 缩圈得到增益；
3. 微修正的 displacement-presence 半径从 `0.35R` 收窄为 `0.12R`，真实数像素
   修正可以恢复，但 `distance=0` 的同点重复仍严格为零。

该设计不以总星硬抬 Micro，也不把普通高速大跳复制为 Precision。高 Micro 可以高于
ppy 总星，但必须由小圈或连续真实微修正解释。

## 关键回归

| 案例 | beta.8 | beta.9 | 结论 |
|---|---:|---:|---|
| BID 2719427 +HDHR Flow | 6.577 | 6.577 | 继承，仍为 Flow 主导 |
| BID 2719427 +HDHR Jump | 3.720 | 3.720 | 未被 Precision 修复牵动 |
| BID 2719427 +HDHR Micro | 2.934 | 6.318 | 有效 CS 5.2 的二维小圈证据 |
| BID 2719427 +HDHR Raw | 5.240 | 4.251 | 短段支撑与速率标尺同时修正 |
| 200 BPM 1/4 完整段 Raw | 7.681 | 6.410 | 总体标尺回落，完整段仍成立 |
| 18 taps/s、7 pair burst Raw | 6.420 | 4.044 | 物理峰保留，公开值不冒充手速图 |

## 1567 图全量审计

冻结任务 hash 为
`29ca2d9a6b59f3e316aacaed03cc9143192164af44ce851ec8c9d88e20abb28d`。

- 成功：1567 / 1567；九维不变量违例：0；
- 来源 checksum 漂移：2，`Couple Breaking [ktgster's SHD]` 与
  `Daidai Genome [Murderous]`，均单列为 provenance drift；
- ordinary 968 张：Micro p50 2.09、p90 3.88、p99 5.88、max 8.22；
- ordinary CS≤4：Micro p90 3.16、max 4.70；
- ordinary 4<CS<5：Micro p90 4.56、max 5.08；
- ordinary CS≥5：Micro p90 5.84、max 8.22；最高样本为 CS6–7；
- Aspire 14 张：Micro p90 5.40、max 6.75；
- ordinary Raw：p50 0.56、p90 4.08、p99 6.84、max 8.36；
- legal-extreme Raw：p90 8.97、max 15.38，合法持续极端仍保留。

完整逐图结果位于 `tmp/profile-audit-beta9-v2/results.jsonl`，汇总位于
`tmp/profile-audit-beta9-v2/summary.json`。这些文件是本地审计产物，不进入发行提交。

## 玩家 BP50 只读回归

以下只用于检查 Map Demand 经成绩质量与 `0.95^(rank-1)` 衰减、加权 P80/P50 后的
行为，不作为公式训练输入；玩家 BP 会随时间变化。

| 玩家 | Jump | Micro | Raw | 主要结论 |
|---|---:|---:|---:|---|
| `[SHK]Wuxin` | 3.8 | 6.4 | 6.1 | 20 张 HDHR 让小圈能力可见，旧图中的 Micro 2.7 被修复 |
| `mrekk` | 12.3 | 4.7 | 5.8 | 超高 Jump 展开；普通大跳没有复制为同级 Micro |
| `qiao_liang` | 6.5 | 2.9 | 1.9 | NM PP 图不再显示 8.3 Jump，也未被 Precision/Raw 顺带抬高 |
| `aetrna` | 5.9 | 5.5 | 10.6 | 反复完整 speed 证据保留世界级 Raw 高尾 |

## 边界

- Map Demand 描述谱面局部机制需求，不按玩家身份、PP 或排名加成；
- 普通 CS4 的 Micro 不应因为谱面总星或 Jump 很高而自动升高；
- 明显小圈允许 Micro 高于总星，但仍需要同一局部窗口内的 acquisition/时间证据；
- Raw 的 physical peak 是诊断，不直接作为玩家公开能力；
- Aspire、病理图和替代机制图继续单独审计，不参与 ordinary 标尺校准。
