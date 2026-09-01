# Map Demand 0.10.0-beta.4 — Aim Control 执行时间试用版

用户授权上线测试。仅发布评审后的
[Aim Control V03 实现](../tools/map_demand_v01/control_execution_v03.py)，
**不发布同期失败的 Reading 实验**。其余八维完整保持生产 beta.3。

## 变更与边界

- 对同样的运动调整，时间更紧产生更强控制成本，而不是仅凭相邻跳距反差给高分。
- 使用前后两次实际可用移动时间，不使用 mapper 的 BPM/二分/四分名称。
- 取连续八个局部转换的需求，不再从三秒范围内跳过轻松动作挑出八个高分。
- 无总 SR 输入、旧分数保底、BID 特判或人工分数拟合。
- beta.4 包装器只调用实验③的控制测量，不调用其 Reading 提取或分析。
- 摘要和主导维度随 Control 变化重新计算；其余八个 axis 对象不变。
- 版本和缓存身份独立，反馈携带 beta.4 身份，旧模型与缓存可保留回滚。

## 已知限制

数值是启发式而不是真值。用户接受本轮偏低的误差用于上线测试，并更关注过高。
3929365 从实验② 7.63 降为 6.88；极短控制段可能被连续八事件支持低估。
速度响应更强，极高速端仍需检查是否放大过度。模型没有完整模拟滑条内部光标轨迹。
Reading 仍有之前已知的问题，本次没有以 Aim Control 发布名义改动它。

## 验证与部署

```powershell
$env:PYTHONPATH = 'src;tools'
python -m unittest tests.test_map_demand_v010_beta4 -q
python tools/verify-control-beta4.py --replay <本地回放结果.json> --out tmp/beta4-release-verification.json
powershell -NoProfile -ExecutionPolicy Bypass -File tools/restart-skill-profiler.ps1 -Algorithm v010-beta4
```

部署脚本只停止经端口/进程命令行验证的 8767 Profiler，健康检查通过才保存
`tmp/runtime-release.json`；新版本启动失败会尝试恢复旧版本。开机启动沿用保存的选择。

回滚：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/restart-skill-profiler.ps1 -Algorithm v010-beta3
```

WuxinBot 的单图缓存和玩家画像缓存以算法 ID + 版本隔离；版本识别缓存 TTL 为 30 秒。
不需要清除历史结果、重启 Bot 或修改玩家聚合算法。卡片沿用现有 beta 试用标签。

## 2026-09-01 本地部署与清理记录

- 清理后的完整回归 561 项通过。
- 285 组谱面、Mod 与历史版本回放的完整输出对象逐字段相等；其中包含
  145 个 beta.4 本地谱面+Mod样本，以及已注册回滚版本的固定谱面矩阵。
- 发布版 Control 与评审后的 V03 实现精确相同；另外八个完整 axis 对象与 beta.3 精确相同。
- 服务健康接口已返回 `MAP_DEMAND_CONTROL_EXECUTION_V010_BETA4` / `0.10.0-beta.4`，
  索引谱面数仍为 102698，运行选择持久化为 `v010-beta4`。
- 使用 WuxinBot 的真实分析请求、版本化缓存和卡片数据构建器进行前后对照：
  3459395、2473220、4827799、3929365 NM 及 1475722 HDDT 均通过。
  卡片数据携带 `0.10.0-beta.4 · 试用`，重复调用命中同版本缓存；另外八维仍相同。
- 仅替换 Profiler 进程，Pippi 和前端进程未重启；未发送任何 QQ 消息。
- 失败的 Reading 实验、对应评估器、测试和文档已删除；正式 beta 与历史回滚入口保留。
