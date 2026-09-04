# Map Demand 0.10.0-beta.9.2 — Flow CS4 目标尺寸负荷

beta.9.2 是 beta.9.1 的单轴补丁，只改变 `flow_aim`。Raw Speed、Micro
Precision 和另外六轴完整继承；默认运行版本仍保持 `v010-beta5`，beta.9.2 必须显式
选择。

## 修复目标

beta.7 至 beta.9.1 的 Flow 使用 slider-aware 物理路径、局部方向连续性和局部节奏，
但 circle-only 路径在物理坐标还原后对 CS 完全不敏感。同一段移动和节奏在 CS2 与
CS5 下得到相同 Flow，不符合目标容差收紧带来的连续瞄准负担。

beta.9.2 不把 CS 作为独立星数奖励，也不重选局部窗口。它先把既有 Flow 星数逆变换
为 latent flow load，再施加 CS4 相对目标尺寸负荷，最后走原有对数标尺：

```text
base_load = (2^(base_flow / 3.5) - 1) / 1.55
size_load = (radius(CS4) / radius(effective_CS))^0.70
flow_9.2  = 3.5 * log2(1 + 1.55 * base_load * size_load)
```

其中半径采用 osu! stable/lazer 的 circle-size 公式。`0.70` 与既有 Flow 运动负荷的
速度指数一致；曲线不分档、不在高 CS 硬饱和。

## 明确不变量

- CS4 精确中性；
- 正 Flow 在审查范围 CS0–12 内随 CS 严格连续上升；
- 零 Flow 不会因 CS 凭空产生；
- slider-aware 几何、flow morphology、winning section、support 和 coverage 不变；
- CS7+ 不封顶，作为极端目标尺寸需求保留；
- CS 超出审查范围时只让 Flow abstain，不外推未知曲线；
- Jump、Raw、Micro、Control、Stamina、Endurance、Finger Control、Reading 的完整轴
  payload 与 beta.9.1 相同。

## 代表性标尺

固定旧 Flow 6.6 时：

| effective CS | beta.9.2 Flow |
|---:|---:|
| 2.0 | 6.046 |
| 4.0 | 6.600 |
| 4.2 | 6.664 |
| 4.5 | 6.764 |
| 5.0 | 6.942 |
| 6.0 | 7.345 |
| 7.0 | 7.834 |
| 8.0 | 8.445 |
| 9.0 | 9.252 |
| 10.0 | 10.412 |

常见的 CS4、4.2、4.5、5.0 在公开一位小数上分别显示为 6.6、6.7、6.8、6.9；
CS7 以上的间距继续扩大，没有把 CS7 与 CS10 压成同一级。

## 版本身份

```text
runtime key       v010-beta9.2
map demand        0.10.0-beta.9.2
algorithm id      MAP_DEMAND_FLOW_TARGET_SIZE_V010_BETA92
changed axes      flow_aim
default runtime   v010-beta5（未改变）
```

合成全管线 canonical JSON 回放锁：

```text
beta.9.1  61b99162cbfb8413d2bdd5b8ae9e84190ac119b94afcceadfc61f829b7fd2e5d
beta.9.2  328ac82abf339562a7bbc7f455278d99a70f125eb74d9ae312555dff70d083f5
```

## 冻结任务全量审计

使用 beta.9.1 的同一份 1567 图任务清单比较 beta.9.1→beta.9.2：

- 1567/1567 成功，失败 0；
- 九维合同违例 0；
- 除 Flow 外八轴完整 payload 漂移 0；
- ordinary 968 图的 Flow mean 3.0318→3.0341，p90 5.2064→5.2434，
  p99 7.1498→7.3076，max 8.8408 不变；
- ordinary 最大上升 0.9730：CS7 `Tatakau Monotachi` 4.1465→5.1195；
- legal-extreme 最大上升 1.6160：CS10 `A New Summer Adventure!`
  1.4123→3.0283；该结果是极小目标对已存在低 Flow 的加重，并未凭空生成高 Flow；
- Aspire p99/max 仍为 7.2891/7.2927，最大单图变化仅 0.2466；
- non-Aspire pathological max 10.8215→10.8959；
- BID 2719427 +HD 的有效 CS4 保持 6.6062；+HDHR 的有效 CS5.2 从
  6.5765 调整为 6.9929，另外八轴完全不变。

冻结清单中有两份 `.osu` 在本次运行前已被外部改动，校验和与任务记录不符：
`Couple Breaking [ktgster's SHD]` 与 `Daidai Genome [Murderous]`。审计的
beta.9.1/9.2 对照仍使用同一份当前字节，因此版本差异有效，但不能把本次运行声明为
1567/1567 源文件零漂移复现。完整逐图结果保留在忽略目录
`tmp/profile-audit-beta92-v1/`；可提交的摘要见
`MAP_DEMAND_V010_BETA92_AUDIT.json`。
