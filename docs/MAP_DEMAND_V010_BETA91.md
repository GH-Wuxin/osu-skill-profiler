# Map Demand 0.10.0-beta.9.1 — Raw powered frontier 阈值选择修复

beta.9.1 是 beta.9 的单轴补丁，只改变 `raw_speed`。Micro Precision 以及其余八轴
完整继承 beta.9；默认运行版本仍保持 `v010-beta5`，beta.9.1 必须显式选择。

## 修复目标

beta.9 将 1.5 次幂施加在线性 frontier 已选出的 winner 上。在混合速率段中，线性
目标与 powered 目标可能选择不同阈值，因此后处理结果不一定是：

```text
max_threshold(
  threshold_star * (support / target_support)^1.5
)
```

beta.9.1 使用 `axis_support_frontier_v02`，在每个观察到的阈值上先计算 powered
frontier，再分别选择 establishment、sustain、recurrence 和 combined winner。

## 计算链

```text
.osu bytes
  -> Local Signal 0.4（未改变）
  -> tapping_axes_v05
  -> axis_support_frontier_v02（候选阶段应用 exponent=1.5）
  -> model_v010_beta91
  -> profile_semantics_v02
```

显式身份：

```text
runtime key       v010-beta9.1
map demand        0.10.0-beta.9.1
algorithm id      MAP_DEMAND_RAW_POWERED_FRONTIER_V010_BETA91
changed axes      raw_speed
```

## 确定性回归

同一 episode 内构造：

- 15.0★ Raw × 5 pair；
- 6.6★ Raw × 6 pair；
- 所有 pair 的机制权重为 1。

beta.9 先按线性目标选择 15.0★ establishment，再对 winner 施加 1.5 次幂；其公开值
最终由 sustain 提供，约为 4.038。beta.9.1 在候选扫描阶段重新比较，选择 6.6★、
11 pair 的 establishment，公开 Raw 约为 5.258。

恒定速率不发生 winner 次序变化：

- 200 BPM 1/4、完整 40 pair：保持 6.410；
- 18 taps/s、7 pair burst：继续受到 sub-linear support 衰减；
- 25ms、完整 80 pair：保留约 26.923，不裁在 10★。

这里的 physical peak 不是数学无界：正常端到端输入的 execution interval 最低为
25ms，因此 beta.9/9.1 Raw physical peak 理论最高约为 `(40-5)/1.3 = 26.923`。

## 版本回放合同

beta.9.1 将 beta.9 的参数化 Raw 代码从 beta.8 冻结模块中隔离。合成全管线输出使用
canonical JSON（UTF-8、排序 key、无空白）锁定：

```text
beta.8 @ 9a1d104
3ac89bb4edb1ea096f808eae0425ca85a8c6c7403db752adae8ad065226924b6

beta.9 @ 5dcaf40
bcce2f7320e6aa345f043524de1eefed715e7d3c4294c1254c4723e947d9675c
```

beta.8 恢复其原始完整 payload；beta.9 的历史错误行为仍由独立兼容路径精确回放，
不会用修复后的结果冒充同一版本。

## 明确边界

- 本补丁不修改 Micro Precision；
- 不处理 `CS > 12` 对抗输入；
- 不修改 Jump、Flow、Control、Stamina、Endurance、Finger Control、Reading；
- terminal double-tap 的未知值语义涉及 Local Signal 版本迁移，不在本补丁中偷改；
- Aspire 继续独立审计，不参与 ordinary 标尺校准；
- beta.9.1 不自动切换默认运行版本。

## 冻结任务全量审计

使用 beta.9 的同一份 1567 图任务清单比较 beta.9→beta.9.1：

- 1567/1567 成功，失败 0；
- 九维合同违例 0；
- 除 Raw 外八轴完整 payload 漂移 0；
- 105 张图 Raw 上升，0 张下降；普通图 968 张中有 77 张受影响；
- ordinary Raw p90、p99、max 均不变，分别为 4.084、6.838、8.364；
- ordinary Raw 平均只上升 0.0153，最大上升 0.6755；
- 全 corpus 最大 Raw 仍为 20.192，没有抬高极端尾部；
- BID 2719427 +HDHR 的 Raw 保持 4.251，其余八轴完全不变。

本次修复恢复的是混合速率图中被错误 winner 选择压低的值，没有重新放宽短 burst
支撑。可提交的机器可读汇总见 `MAP_DEMAND_V010_BETA91_AUDIT.json`；完整逐图结果保留在
忽略目录 `tmp/profile-audit-beta91-v1/`。
