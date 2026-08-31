# Map Demand 0.10.0-beta.1 — 九维解耦公开试用版

本次发布复用已经人工查看三批案例的 `decoupled-v01 R2`，只新增发布身份，
不修改九维公式、阈值或分数。旧 `v096` 与独立实验入口 `decoupled-v01` 均保留。
之前封存的 0.97/0.98 不被覆盖或复用。

## 版本与缓存

- 算法：`MAP_DEMAND_DECOUPLED_V010_BETA1`
- 算法版本：`0.10.0-beta.1`；状态：`PUBLIC_BETA`
- 校准标识使用独立 `md010beta1:` 前缀。反馈继续绑定算法身份、BID、Mod 和输入校验和。
- 单图及玩家画像缓存按算法身份隔离，不删除旧版缓存/人工反馈。
- Python 基础包版本不变；谱面类型检测仍是独立的实验功能。

## 已知限制

1. Finger Control 在缺少切换证据时可能为 0；不代表玩家完全不需要手指控制。
2. Jump / Flow 仍保留 R2 的 `参考锚点 × 1.08` 保护限值；本次不偷偷取消或重调。
3. 本地 NM 星数来自 `osu!.db`；Mod 锚点是结构变换估计，缺少 NM SR 时有结构回退。
   它不是官方实时 Mod SR。卡片顶部的官方 SR 与模型锚点应区分理解。
4. Reading、Stamina、Micro Precision 等仍需真实样本观察；人工旧分值仅作参考。

## 部署与回滚（Windows）

```powershell
# 发布试用版；仅重启 8767 对应的 Skill Profiler Python 服务
powershell -NoProfile -File tools/restart-skill-profiler.ps1 -Algorithm v010-beta1
# 回退 V0.96，选择将保存在 tmp/runtime-release.json，自启动也沿用
powershell -NoProfile -File tools/restart-skill-profiler.ps1 -Algorithm v096
```

脚本检查端口对应进程与旧版本身份，后台启动、健康检查后才保存默认选择；
启动失败时尝试恢复先前算法。`SKILL_PROFILER_ALGORITHM` 环境变量可显式覆盖默认选择。
不需要改动 QQ/NapCat，且不删除谱面、反馈或旧实验文件。

独立复跑可用 `analyze --algorithm v010-beta1` / `--algorithm v096` / `--algorithm decoupled-v01`。
定向测试：`python -m unittest tests.test_map_demand_v010_beta1 tests.test_map_demand_decoupled_v01`。
