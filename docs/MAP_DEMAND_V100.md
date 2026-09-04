# Map Demand 1.0.0

1.0.0 将用户实测认可的 Beta 9.2 冻结为正式版，不新增或调整算法公式。

## 版本与行为合同

| 身份 | 值 |
| --- | --- |
| Runtime key / 新安装默认 | `v100` |
| Map Demand version | `1.0.0` |
| Algorithm ID | `MAP_DEMAND_V100` |
| Output envelope schema | `map_demand_v1.0.0` |
| Release stage | `STABLE` |
| Frozen computation basis | `0.10.0-beta.9.2` |
| Local Signal | `0.4.0`（不变） |

`model_v100` 完整委托 `model_v010_beta92` 提取与计算，仅替换公开版本身份、发布说明
与直接基线身份。九维完整 payload、汇总、分类及计算证据均与 Beta 9.2 相同。
轴契约中保留 beta 标识作为真实实现来源，不为了正式版名称伪造新轴契约。
基础 Python 包及其基础层 Schema 保持独立版本，不随 Map Demand 升级。

Beta 9.2 的合成全管线 canonical JSON 锁：

```text
328ac82abf339562a7bbc7f455278d99a70f125eb74d9ae312555dff70d083f5
```

后续行为变更必须使用新版本，不能原地修改 1.0.0 或其冻结依赖的数值语义。

正式化验证：完整测试套件 829 项，0 失败，3 项条件跳过。新增冻结测试覆盖 NM、HD、
HR、HDHR、EZ、DT、HT 的全输出（仅允许身份字段变化），并实测 BID 2719427 +HDHR。

## 冻结内容与已知边界

- Raw 保留 Beta 9.1 的 powered support 候选阈值选择修复。
- Micro Precision 保留 Beta 9 的目标容差和非零微修正行为。
- Flow 保留 CS4 中性、指数 0.70 的地图级 latent-load 尺寸重标定。
  这是经实测选定的修正，并非新的逐物件目标容差耦合模型；本次不重写它。
- Jump、Control、Stamina、Endurance、Finger、Reading 保持原计算。
- 正式版表示冻结和发布承诺，不表示启发式量尺已经成为官方难度或人工真值。
- Aspire、病理谱和辅助 hitsound 层继续单独审计，不作为普通谱校准依据。

Beta 9.2 的 1567 图审计为本版数值基线：1567 成功、0 合同违例、非 Flow 八轴漂移 0。
该审计有 2 份源文件相对冻结清单发生校验和漂移，不声明零来源漂移。
详见 [Beta 9.2 审计](MAP_DEMAND_V010_BETA92_AUDIT.json)。

## 使用与回放

```powershell
python -m tools.map_demand_v01.cli analyze --map "map.osu" --algorithm v100
python -m tools.map_demand_v01.cli bid-review-ui --algorithm v100
```

旧版本仍可显式选用 `v010-beta9.2`、`v010-beta9.1` 等 key。
已有 `SKILL_PROFILER_ALGORITHM` 或 `tmp/runtime-release.json` 选择继续优先于默认值，
不会因更新仓库而静默覆盖用户的持久化回退选择。

本机可用 `tools/restart-skill-profiler.ps1 -Algorithm v100` 切换运行身份；启动失败会
尝试恢复之前版本。Git 标签 `v1.0.0` 用于锁定本次正式版代码。
