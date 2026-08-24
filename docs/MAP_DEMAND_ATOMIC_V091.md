# Map Demand Atomic V0.91 — 机制去重与统一标尺

V0.91 是当前默认模型。V0.9 保持冻结、可重放，不会被原地改写。

- algorithm: `MAP_DEMAND_ATOMIC_V091`
- output schema: `map_demand_v0.9.1`
- calibration identity: `mdoverlay_v091:*`
- axis taxonomy: 继续使用九维 `atomic_v0.8.0`

## 机制变化

### Finger Control

V0.9 会叠加 Raw Speed floor、pattern extension 与 coordination bonus，导致普通快速谱也频繁得到 7～10 星 Finger Control。V0.91 只在 220 ms 内的局部快速段检查非平凡节奏变化；普通 1:1、1:√2、1:2 间隔本身不再构成额外证据。旧排序只保留去重后的主体，并受 Raw Speed 相对上限约束。

### Jump Aim 与 Spatial Precision

Jump Aim 仍以跳跃距离和可用移动时间为主体，只保留很弱的 CS 影响。DT/加速谱进入校准极端尾部时，会依据原始 P90 跳距与移动速度恢复 percentile 饱和后丢失的强度；NM 与 HT 不触发这项恢复。NM 星数转换为 DT 软锚点时也使用同一结构强度调整 rate exponent，避免把 Jump-heavy DT 谱的总尺度严重低估。

Spatial Precision 使用三个可审计成分：目标直径相对跳距（容错）、落点速度下的 settling pressure，以及大位移后急停或反向短修正的 micro-correction pressure。缩小圆圈会强烈提高 Precision，但不会同幅度抬高 Jump Aim。

### Flow Aim

Flow 只保留 300 ms 内、夹角至少 135°、曲率变化不超过 45°且持续成链的移动。最终强度由链占比、P90 链长、链速度和曲率稳定性共同重加权，不再用宽松连续条件给离散跳跃发 Flow 分。

### Reading

V0.91 在模型私有提取层读取原始物件坐标，不改写冻结的 Local Signal 0.3 合同。它在 approach window 内计算实际几何重叠、近邻簇、overlap pair share 与 stack object share，再和相对 AR、HD 联合。相同密度但分散摆放的谱面不会再被当作堆叠读图。

## SR 软锚定

- 本地 `osu!.db` 有 NM 星数时，以它为尺度锚点，并对 HR/EZ/DT/HT 做保守变换。
- 没有本地星数时，使用物理轴的稳健第三高值，并在 diagnostics 中明确标注。
- 低于锚点的维度保持原值，不会被强行拉向总星数。
- 高于锚点的偏科维度仍可上升，但使用 `tanh` 平滑饱和，避免极端校准尾部产生 18～21 星的无意义膨胀。
- Stamina 与 Endurance 保持独立的 0～10 人类量表，不参与星级软锚定。

## 回放

```powershell
# V0.91 默认
python -m tools.map_demand_v01.cli analyze --map "map.osu"

# CLI 无法自动读取 osu!.db 时，可显式提供 NM 星数锚点
python -m tools.map_demand_v01.cli analyze --map "map.osu" --star-anchor 7.18

# 冻结回放 V0.9
python -m tools.map_demand_v01.cli analyze --map "map.osu" --algorithm v09
```

V0.91 仍是启发式模型。人工评价用于发现机制偏差和后续校准，不会被默认为无条件 ground truth。
