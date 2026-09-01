# Map Demand 0.10.0-beta.5 — Reading 顺序与遮挡试用版

## 版本边界

beta.5 以 beta.4 为基础，只替换 Reading。Aim Control 继续使用 beta.4 的执行时间模型，另外七个维度也保持 beta.4 数值不变。beta.4 仍是可直接选择的回滚版本。

Reading 不读取总星数，也不借用 Aim、Tapping 或耐力维度。它从谱面局部事件独立估计玩家需要辨认和保留的信息。

## 当前机制

- 相邻物件头部重叠本身不再等同于顺序歧义；重点检测非相邻折返、交叉和局部顺序冲突。
- 低 AR 只有在局部信息率和真实顺序证据存在时才明显加难，缓慢、规则、低信息场景不会仅凭长 preempt 获得高分。
- 长时间保留与快速解码取较强一侧，不把同一批物件重复相加。
- HD 使用“尚未解决的局部顺序记忆”近似消失物件负担，而不是固定倍率。
- 紧凑、规则的高速串会得到 relief，避免从 Flow Aim 或点击密度借来虚假的 Reading。
- 中速大位移只获得最多 20% 的轻微 relief；真实折返、低 AR 保留和 HD 记忆证据会保护 Reading。
- 使用局部支撑峰值和填充段分离，短而明确的难读段不会被大量简单部分冲淡。

该模型仍是启发式视觉需求近似，不是完整的 osu! 渲染、皮肤、显示器或玩家视线模拟。非常短的特殊滑条内部读图、复杂 hitsound 引导和个体读图习惯仍可能被低估或高估。

## 验证快照

- Reading 机制、独立性和版本契约由 19 组定向测试覆盖；仓库全量回归共 580 项。
- 本地 145 个谱面/Mod 样本重放分布：中位数 4.54，P90 6.00，最大值 11.80。
- 重点复核值：Heat abnormal HD 11.80、Xeroa 8.55、Peach Pit and Cyanide 6.79、BID 5648807 为 5.25、FDFD 6.68、两张 awkward aim 样本分别为 5.42 与 5.89。

这些数值是当前回归快照，不是固定人工标杆；后续修改仍应以机制正确性和更广泛案例为依据。

## 部署与回滚

部署 beta.5：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/restart-skill-profiler.ps1 -Algorithm v010-beta5
```

回滚 beta.4：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/restart-skill-profiler.ps1 -Algorithm v010-beta4
```

重启脚本会校验当前 8767 端口进程、等待健康检查，并只在启动成功后持久化运行版本；失败时会尝试恢复原版本。
