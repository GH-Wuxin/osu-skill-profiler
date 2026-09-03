# Map Demand 0.10.0-beta.6 — Jump/Flow 路径口径修正版

beta.6 是 opt-in 试用版本，默认 runtime 仍为 beta.5。它保留 beta.5 的
Reading、beta.4 的 Aim Control 以及其余公开轴，只在 Local 0.4 输入上替换
Jump Aim 与 Flow Aim 的证据路由。

## 输入身份

- beta.1–beta.5 继续固定使用 Local Signal 0.3；
- beta.6 明确使用 Local Signal 0.4；
- Local 0.4 修正 legacy compound Bezier 分段，详见
  `docs/LOCAL_SIGNAL_CONTRACT_V04.md`；
- Reference Signal 0.2 仍冻结在 Local 0.3。

beta.6 的 calibration ID 带有 `aim_routing_1:local04`，cache identity 与
beta.5 分离。该版本已注册为 `v010-beta6`，但未改默认算法、未改
`tmp/runtime-release.json`。

历史 extractor 的 metadata 形状保持不变；`local_signal_version` 只由 beta.6
wrapper 增补。这样 beta.1–beta.5 的既有 CLI envelope 不会因 beta.6 的
provenance 要求发生漂移。

组件提取必须显式携带来源版本，并接收 beta.6 extractor 返回的版本化 rows
envelope。envelope 带有本次提取边界的凭据与 canonical content digest；未标注
rows、Local 0.3 rows、脱壳成普通 list 的 rows，以及提取后被修改的 rows 都会
fail closed。最终 identity 与 `release_basis_identity` 都记录实际的 Local 0.4，
不会把“beta.5 公式 + Local 0.4 输入”的内部 basis 冒充为可重放的 beta.5/Local
0.3。

该 envelope 是 public API 的防误用边界，不是对同进程恶意 Python 调用者的
密码学证明；能显式访问模块私有符号的代码仍属于受信任进程边界。

## Jump Aim

首选同一物理阶段的一对量：

```text
minimum jump distance / minimum jump time
```

只有其中任一量不可用时才整体回退为：

```text
raw head distance / full adjusted delta time
```

禁止使用 raw head distance / minimum jump time，也禁止只替换这对量的一半。
distance gate 与 velocity gate 先在每一条 transition 内组成 joint kinematic
score，再取 tail quantile；全图 distance p99 与另一条 transition 的 velocity p99
只保留为诊断，不能拼成正证据。
此外保留两个彼此独立、仍然同口径的正证据：

```text
lazy jump distance / full adjusted delta time
timely circle-to-circle distance（minimum distance + minimum time）
```

第二个通道只用固定 CS4 参考半径判断大距离；不接受 slider 后 raw distance，
也不把慢速大跨度直接当作高 Jump。有效 pair 覆盖率只惩罚缺失几何，不惩罚
正常的容易 filler。circle 通道同时记录全部有效 transition 占比、最多 8 条
transition 的局部窗口密度和连续大跳长度；单个稀有 circle pair 即使在
circle-only 分母中占 100%，也不能独自证明整图 Jump，短而密集的真实 Jump
段则不会被长图的全局分母抹掉。该通道的规范分数不用二值 count：距离从
3.25R 到 3.75R 连续进入，时间在 250 ms 内为全权重、到 320 ms 连续淡出。
原 3.75R / 250 ms count 仅作诊断，因此边界两侧不会让 Jump support 跳变。
通用 high-pair persistence 同样使用连续的 load/time 权重；250 ms 后到 320 ms
淡出，旧的 hard count 与 hard chain length 不参与规范 support。

## Flow Aim

跨物件完整路径使用：

```text
(previous slider lazy travel + current lazy jump) / full adjusted delta time
```

当前 slider 内部 travel 另行报告，但不能单独产生 Flow support；它已经通过
下一条 transition 的完整 lazy 路径参与几何，避免跨 section 借用一条快 slider
给别处的链加分。独立的 slider peak 仅作诊断，不进入最终 support。

strict 与 broad 的长度、cadence、spacing、velocity、smoothness 和 wide-head
shape 先在同一条不间断 run 内联合算分，再在 run 之间取最大值。spinner、缺失
path、缺失 angle 或不满足该 channel 的 directional event 都会断链；全图 p90、
coverage 与最长链只作诊断或数据质量衰减，不能把慢长段的长度与另一短快段的
速率拼成高 Flow。

物理完整路径与方向形态分开计数：第二个物件已经可以提供第一条完整路径，角度
则从第三个物件才有定义。首个有效角度以“两条 transition、三个 note”为链基数，
但单个角只描述一次转向，不能证明 Flow persistence；strict 与 broad 都在第三个
到第四个 effective note 间连续激活。完整路径 coverage 与有效方向 coverage
都会衰减 support，缺失 angle 不能靠少数残存样本饱和。

节奏窗口没有硬切：strict 在 300 ms 内为全权重、到 360 ms 连续淡出；broad
在 220 ms 内为全权重、到 300 ms 连续淡出。morphology context 只有在至少
四个 effective note 的连续性成立后才进入规范 support。

几何门使用固定 CS4 参考半径；HR 只通过温和的目标尺寸负担影响 load，不再因
`6 × current radius` 上限缩小而断链。broad chain 的强度同时要求长度和局部
cadence；纯长度不能单独接近饱和。宽跳反证按“lazy jump / 完整路径”的连续
head-dominance 权重统计，零 travel slider 与 circle 一致，也不会在 0 与极小
travel 之间翻转；wide-distance 权重在 3.25R 到 3.75R 间连续进入。只有
majority-wide 的极端 head-dominated 形态才压低其所在 run 的 Flow 正通道，
超长链有保留。完整路径 coverage 进入 support，缺失量不再是死组件。

## 失败与回退

`beta6_aim_routing` 使用精确 nested schema，并校验 finite、count、coverage 和
所有派生 support。组件缺字段、多字段、非有限值、来源版本不符或派生值不一致时
分析直接失败，包括 invalid/unsupported mod 的早退路径；证据不足时保留对应
beta.5 轴并输出告警，不伪造零值。没有合格连续链时，Flow 也保留 beta.5，
不会把“缺少新正证据”解释成确定的零需求。Jump 与 Flow 都用各自的
`routing_activation` 将 beta.5 值连续混合到 beta.6 候选值；该 activation
由实际 pair/方向覆盖率与合格链共同约束，未知数据不会被当成确定反证。

## 当前验证结论

在 BID 2719427 上，NM/HD 从 beta.5 的 Jump/Flow `7.1423 / 5.2021`
变为 `5.4111 / 7.3760`；HR/HDHR 从 `7.5708 / 4.7980` 变为
`5.7357 / 7.8185`。HDDT 反例 BID 764517 的孤立三物件 strict turn 不再
激活 Flow，beta.5/beta.6 都保持 `0.0`。

40 条现有人工记录全部是 `ASSISTED_ALGORITHM_VISIBLE`，只能作 sanity panel：
Jump 的 26 条 MAE 从 `0.6734` 恶化到 `0.8025`，Flow 的 33 条 MAE 从
`1.1601` 改善到 `1.0186`。因此 beta.6 仅保持 opt-in；尤其 Jump 路由还不能
据此升级为默认或宣称已完成独立校准。

## 已知边界

- stacking 尚未实现；
- Flow 的角度/链 gate 仍是机制启发式，不是人工标签训练结果；
- star-equivalent 仍借用 osu!.db 总 SR anchor；support 并非独立训练出的绝对尺度；
- 现有人工 Jump/Flow 记录全部为 assisted，可作防灾线，不能作为唯一校准真值；
- compound Bezier 已版本化修正，但其他特殊 path syntax 尚未宣称完整 ppy parity；
- beta.6 未经大规模人工回归前不应切换为默认 runtime。
