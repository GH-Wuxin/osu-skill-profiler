# 0.10.0-beta.3 — Precision 平衡修正版

本轮只改变 `spatial_precision`（显示名 Micro Precision），Stamina 及另外七维保持 beta.2 原样。
不修改玩家成绩质量修正、BP 衰减、雷达投影，不按其他维度补底分。

## 修正原因

beta.2 用有界基础项乘以 `radius^-1.65` 等圈大小倍率，造成普通／大圈的数值天花板过低，
而极小圈把整个基础项过度放大。单独减轻低 CS 惩罚不能解决两端的尺度不连续体感。

## 新公式

- `r` 为 Mod 后实际圆半径；`r_ref` 为 CS4 半径。
- `A = 1 - exp(-distance_px / 32)`：是否需要重新落点，物理间距很快饱和，避免成为 Jump Aim。
- `D = 2.2 * log2(1 + taps_per_second / 2)`：当前真实时间间隔下的落点截止时间需求。
- `u = log2(r_ref / r)`；小圈 `T = 4.2*u`，大圈 `T = 1.6*u`。
- 单次需求 `A * max(0, D + T) + 0.65*micro`。micro 沿用 beta.2 有界物理微调证据。
- 聚合沿用 beta.2：三秒局部最高八项平均（带证据支持量），90% 局部峰值 + 10% 中位数。

大圈仍减分，但不再乘掉整个维度；小圈每缩小一倍增加固定需求而不是指数放大所有项。
CS4 两侧连续。没有 10 分硬上限、没有普通 CS 的固定 2～3 分天花板，也不消费总 SR。
静止连打不会仅凭高速、小圈获得重新落点需求。

这些系数是可复核的启发式量表，不是生理模型或人工标注拟合真值。
局部时间压力依然可能与其他 Aim 维度相关；CS 相同不保证 Pre 相同。

## 验证与回放

`tests/test_map_demand_v010_beta3.py` 覆盖 CS 单调／连续性、温和大圈减法、小圈无陡增、
普通圈无低天花板、微调信号、总 SR 独立、八维冻结、Mod HTTP 身份与旧缓存隔离。

`tools/evaluate-map-demand-beta3.py --sample tmp/beta2-evaluation.json --out tmp/beta3-evaluation.json`
在同一批 144 个本地谱面／Mod 案例上回放两版：零错误，其余八维逐项一致。
这是方便取样的回归集，不是全体谱面统计；不包含硬编码 BID 算法分支。

| 案例 | 有效 CS | beta.2 Pre | beta.3 Pre |
| --- | ---: | ---: | ---: |
| C-TYPE +HR | 8.06 | 7.04 | 8.13 |
| Brazil NM | 7.00 | 5.10 | 7.54 |
| Crystalia +HDDT | 3.30 | 2.24 | 6.13 |
| Peach Pit and Cyanide NM | 4.00 | 2.33 | 4.98 |
| new beginnings NM | 2.00 | 0.84 | 0.89 |

玩家集成测试使用真实本地谱面需求 + **合成 BP50 成绩质量**，确认成绩惩罚与优秀 FC 奖励仍有效，
八维聚合不变。不把旧 BP20 图片快照冒充玩家当前 BP50 数据。

部署：`powershell -File tools/restart-skill-profiler.ps1 -Algorithm v010-beta3`。
回滚：`powershell -File tools/restart-skill-profiler.ps1 -Algorithm v010-beta2`。
脚本只替换 8767 的已验证 Profiler 进程；健康检查成功才持久化选择，新版失败尝试恢复旧版。
`beta.2`、`beta.1`、V0.96 均保留。缓存通过新的算法／版本／校准身份隔离。
