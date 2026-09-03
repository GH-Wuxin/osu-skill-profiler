# Skill Profile beta7 人工 BID 次级验证审计 V01

审计日期：2026-09-02<br>
结论级别：**SECONDARY / ASSISTED SANITY EVIDENCE ONLY**<br>
数据源：`training/datasets/map_demand_bid_review_v01/human_responses.jsonl`

## 结论

这批人工记录不能用于拟合 beta7、调整轴尺度或设置发布阈值。64/64 条记录都是
`ASSISTED_ALGORITHM_VISIBLE`，来自同一 reviewer，且标注时可见旧算法数值；其中
25 条还是没有 Endurance 的旧八轴 schema。它适合发现需要复核的具体反例，也适合
检查新版本是否发生灾难性漂移，但不是独立真值。

按 beta7 对所有可解析记录重算后，60/60 个唯一 `(path, mods)` 均成功，九轴均
能产生结构化输出；234 个去重后的 `APPROXIMATE` 点值比较没有 abstention。初次
人工审计本身没有独立确认通用 bug，也没有用这批输入修改算法、尺度、calibration
或 runtime。但后续不依赖人工值的公式审计和 metamorphic probes 独立确认了一个
Flow P1：旧公式按单个弱转向累加，能让缺乏相邻连续性的分散证据通过数量放大。

当前实现已改为同一 section 内相邻有效转向权重的乘积链。BID 764517 +HDDT
由修复前的 `3.2566` 降为 `1.9171`。这项修复的授权证据是独立公式不变量和
合成变形测试，不是 assisted 标签本身；人工资料仍只是次级 sanity panel。

## 数据规模与偏差边界

- 64 条 response，55 个唯一 BID，60 个唯一 `(path_abs, effective_mods)`；64/64 路径存在。
- review mode：64/64 为 `ASSISTED_ALGORITHM_VISIBLE`；reviewer：仅 `local-reviewer`。
- schema：`atomic_v0.6.0` 25 条（旧八轴，无 Endurance）；`atomic_v0.8.0` 39 条（九轴）。
- 当时可见算法版本：0.6.0 为 25 条，0.8.0 为 13 条，0.9.5.0 为 26 条。
- mods（按 response 计）：NM 45、HD 12、HDDT 3、HDHR 2、DT 2。空或缺失 mods 按 NM；
  已写入记录的人工纠正条件按修正后的 `algorithm_identity.effective_mods` 使用。
- confidence：MEDIUM 53、HIGH 7、未填 4。
- 551 个轴槽位恰好等于 `25*8 + 39*9`：`APPROXIMATE` 242、`AT_LEAST` 9、`SKIP` 300。
- 重复的 `(path, mods, axis)` 点标注用中位数折叠，避免同一谱面伪增样本量；242 个原始
  approximate 槽位折叠为 234 个点。9 个 `AT_LEAST` 折叠为 8 个下界，完全不进入
  MAE、中位绝对误差或秩相关。

这些限制意味着：下表只能描述“beta7 与这位 reviewer 在看见旧算法后的输入差异”，
不能测量真实泛化误差。尤其是旧可见值与人工值很接近时，不能反推 beta7 应向旧尺度
靠拢。

## 重算方法

每个唯一谱面条件通过
`tools/map_demand_v01/model_v010_beta7.py:extract_from_path` 提取 Local 0.4，再通过
`extract_components` 取得 `beta7_spatial_axes`、`beta7_tapping_axes` 和
`beta7_reading`。统计直接使用各 evidence envelope 的 `value`；beta7 发布层在
`model_v010_beta7.py:373` 起将该值原样应用到轴输出，因此不需要、也没有使用旧
calibration 或总 SR 来做这次比较。所有被比较 envelope 的 `total_sr_used` 都是
`false`。

误差定义为 `beta7 - human`。秩相关为带平均 tie-rank 的 Spearman rho，仅在去重
点数 `n >= 8` 时报告。本批各轴都达到这个描述性门槛，但 Endurance 只有 11 点，且
所有点仍来自同一 assisted reviewer，不能据此做显著性或发布结论。

## 各轴统计

`n` 列为“原始非 SKIP 槽位 / 去重后唯一 approximate 点”；`AT_LEAST` 只计入
前者及最后一列，不进入误差统计。“旧可见 MAE/rho”只用于显示
assisted anchoring 风险，不是候选模型基线或真值。

| 轴 | n | beta7 MAE | beta7 中位绝对差 | beta7 bias | Spearman rho | 旧可见 MAE | 旧可见 rho | 唯一下界数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Jump | 26 / 25 | 0.871 | 0.688 | +0.032 | 0.585 | 0.516 | 0.902 | 1 |
| Flow | 33 / 30 | 0.863 | 0.737 | +0.403 | 0.832 | 0.732 | 0.686 | 1 |
| Control | 41 / 36 | 1.096 | 0.826 | -0.463 | 0.342 | 0.794 | 0.566 | 3 |
| Precision | 26 / 26 | 3.265 | 3.065 | -3.265 | 0.478 | 0.947 | 0.571 | 0 |
| Raw Speed | 27 / 26 | 1.125 | 0.822 | +0.738 | 0.829 | 0.599 | 0.808 | 0 |
| Stamina | 21 / 21 | 2.918 | 2.541 | -2.918 | 0.477 | 0.516 | 0.847 | 0 |
| Endurance | 11 / 11 | 0.759 | 0.795 | -0.564 | 0.963 | 0.340 | 0.936 | 0 |
| Finger Control | 31 / 29 | 1.570 | 1.510 | -1.052 | 0.607 | 1.616 | 0.378 | 0 |
| Reading | 35 / 30 | 1.225 | 1.016 | -0.717 | 0.450 | 1.062 | 0.401 | 3 |

观察边界：

- 当前 Flow 与 Raw Speed 的描述性排序最好（分别约 `rho=.832/.829`）。Flow 修复后
  在这个有偏 panel 上的 MAE 高于旧可见值；由于标注时可见旧值，这个差值不能
  被解读为修复回归，更不能替代 blind validation。
- Precision 和 Stamina 的所有点都是 beta7 低于人工输入，bias 的绝对值等于 MAE。
  同时人工值与旧可见值非常接近。这是最强的“量纲/定义迁移 + 可见值 anchoring”信号，
  不是把 beta7 整轴上移的依据。
- Endurance 的 rho 很高，但 `n=11`，并且旧八轴记录完全没有这个轴；它只能算一个
  值得扩大盲测的弱信号。
- beta7 没有因为人工值常落在 0--10 而裁掉合法高尾：本批 Raw Speed 达 `11.953`，
  AR0 Reading +HD 达 `11.800`。高值本身不构成异常。

## 每轴最大点值偏差、Flow 命名反例与原始机制证据

下列行号指 JSONL 的 1-based 行。coverage、support、eligible/evidence count 和
winning window/run/section 均来自本次 beta7 重算，而不是旧 snapshot。

| 轴 | JSONL / BID / mods | human -> beta7（差） | beta7 原始证据摘要 | 判定 |
|---|---|---:|---|---|
| Jump | 47 / 949011 / NM | 5.700 -> 7.634（+1.934） | FULL，coverage 1.000，support .936，503 eligible；8 events、1.200s，joint load 2.929 | 同轴局部证据很强。review note 实际质疑的是 Raw Speed，不足以否定 Jump；量纲/主观差异。 |
| Flow | 11 / 2744036 / NM | 6.200 -> 8.868（+2.668） | FULL，coverage 1.000，1392 eligible；winning 48 events、4.052s，individual sum 30.499，linked mass 18.204，effective pairs 52.011，coherence .719，persistence 1.000，velocity .696 px/ms，spacing 1.644R；support .532 | 当前 Flow 唯一点的最大偏差；相邻连续转向证据集中且完整，属于量纲/主观差异，不是旧 P1 的弱证据数量放大。 |
| Flow 命名 probe | 19 / 764517 / HDDT | 0.000 -> 1.917（+1.917） | FULL，coverage 1.000，114 eligible；winning 48 events、11.714s，individual sum 4.186，linked mass .364，effective pairs 1.040，coherence .221，persistence .052，velocity .827 px/ms，spacing 4.650R；support .0091、counterevidence .9909 | **P1 已修复并锁回归**：人工值只用来命名反例；独立变形测试确认旧的单点累加会放大分散弱转向，当前相邻乘积链使 persistence/support 回落。 |
| Control | 4 / 1451703 / NM | 8.900 -> 4.645（-4.255） | FULL，coverage 1.000，support .449，838 eligible；8-event winner，morphology effort .840 | reviewer 明确把“超级大跳”算入 Control；beta7 将大跳与控制形态拆轴。属于 taxonomy 分歧，不是 Control 证据缺失。 |
| Precision | 52 / 5186856 / DT | 7.300 -> 2.198（-5.102） | FULL，coverage 1.000，support .255，454 eligible；8-event winner，precision effort .501；旧可见值 10.399 | 当前轴测 minimum-phase target tolerance，review note 却质疑 pre-aim/finger，且输入接近高旧值；定义/anchoring 冲突，没有独立机制 bug 证据。 |
| Raw Speed | 20 / 5225100 / HDDT | 7.000 -> 11.953（+4.953） | FULL，coverage 1.000，support .978，56 evidence；winning run 约 3.043s、18.401/s；旧可见值 9.826 | reviewer 将其称为“耐力串图”；高速局部 run 的 Raw 证据真实存在。当前值为合法 unbounded 高尾，不应因数值大而裁尾。 |
| Stamina | 7 / 5573770 / NM | 10.000 -> 3.918（-6.082） | FULL，coverage 1.000，3968 evidence；winning effective duration 199.336s、10.136/s，speed pressure .663；同图 beta7 Endurance 为 8.408 | 该行是旧八轴 schema；review note 明确把“长”和同 BPM 连续性同时塞进 Stamina/Finger。beta7 将持续长度放入 Endurance，所以主要是 schema/taxonomy 迁移。 |
| Endurance | 38 / 4590529 / HDHR | 9.700 -> 7.970（-1.730） | FULL，coverage 1.000，support .788，3240 evidence；winner 1213 events、120.891s | 机制证据闭环，样本又只有 11 个；暂归为小样本尺度差。 |
| Finger Control | 7 / 5573770 / NM | 6.400 -> 2.182（-4.218） | FULL，coverage 1.000，support .199，activation .387，2511 evidence；42-transition winner，mean predictability .972 | reviewer 把长时间同 BPM 按压视作 Finger；beta7 Finger 测局部 timing-pattern 不规则度，规则性很高时低值符合当前定义。taxonomy 分歧。 |
| Reading | 5 / 4007768 / NM | 6.500 -> 3.402（-3.098） | FULL，coverage 1.000，support .441，659 eligible；8-event、.750s winner | review note 只写“知名 Aim control”，没有 Reading 专属原始理由；不能据此判 Reading 漏证据。 |

其他大偏差也呈相同模式：Precision 的 BID 4704022 NM/DT、4684761 NM/HD 和
5225100 HD 都有完整 coverage，但当前 target-tolerance support 只有约 `.17--.29`；
人工值却靠近当时高旧值。Stamina 的 BID 1857321 只有 8 个 eligible tapping evidence、
activation `.043`，而 reviewer 描述的是 slider jump、double tap 和 rhythm。它们应进入
重新写清轴定义后的盲测，不应直接转化为尺度修正。

## `AT_LEAST` 下界

下界不参与点误差。它们更适合检查合法尾部是否被丢失。

| 轴 | BID / mods | 人工下界 | beta7 | 下界差额 | 证据结论 |
|---|---|---:|---:|---:|---|
| Control | 862088 / NM | 9.0 | 6.354 | 2.646 | FULL，coverage 1，1893 eligible，support .596 |
| Control | 591347 / NM | 8.0 | 5.391 | 2.609 | FULL，coverage 1，1047 eligible，support .517 |
| Control | 1754266 / NM | 8.5 | 6.212 | 2.288 | FULL，coverage 1，1557 eligible，support .587 |
| Jump | 591347 / NM | 7.0 | 4.943 | 2.057 | FULL，coverage 1，1052 eligible，support .689，joint load 1.521 |
| Flow | 1754266 / NM | 7.7 | 7.919 | 已满足 | FULL，coverage 1，1557 eligible，support .467，linked mass 8.894，coherence .551 |
| Reading | 4303461 / NM | 11.0 | 10.826 | .174 | FULL，coverage 1，AR0 高尾保留 |
| Reading | 3839996 / NM | 7.0 | 7.105 | 已满足 | FULL，coverage 1，AR6 高尾保留 |
| Reading | 4303461 / HD | 11.0 | 11.800 | 已满足 | FULL，coverage 1；HD 高于 NM，高尾未裁剪 |

Reading 的三个唯一极端下界总体支持当前尾部方向，尤其 AR0 的 NM/HD 顺序正确；
它们仍是 assisted、单 reviewer 输入，只能作为合法极端保留样本，不能用来拟合 Reading
系数。

## 机制漏洞与量纲差异的处置

### 后续独立审计已确认并修复一个 Flow P1

- 60 个唯一条件全部重算成功，0 路径缺失、0 提取异常、0 point-label abstention。
- 最大偏差项的 evidence envelope 都是结构化、finite、`total_sr_used=false`，没有把
  missing 当作 observed zero 的迹象。
- 初次人工审计只把 764517 标记为待独立复核的 P1，没有用 assisted 值设阈值或
  调参。后续公式审计确认，旧 Flow 把每个有效转向的单点权重相加，不要求高权重
  转向必须相邻，因而分散的弱转向能靠数量放大。
- 当前 `LOCAL_DIRECTIONAL_PATH_COHERENCE_PHYSICAL_LOG_V03` 改用
  `previous_effective_weight * current_effective_weight` 构成 `linked_pair_mass`；availability
  与 coherence 仍分离，spinner/section 边界仍不可跨越。
- Precision/Stamina 的系统负偏差与旧可见值 anchoring、八轴到九轴定义迁移高度混杂；
  这不是代码证据，不能授权平移或重标定。
- 大于 10 的 Raw/Reading 值均有同轴局部机制证据；不建议 clipping、统一压尾或以
  “看起来夸张”为失败条件。

### 必须保留的 P1 非人工回归

BID 764517 +HDDT 保留为 Flow 命名机制 probe。该图本身只提示了疑点；下列的
公式与 metamorphic probes 才是确认和验收 P1 的主证据：

1. 转向角从 `pi/2 -> .10 -> .01 -> 0` 时 Flow 严格下降并连续趋近 0；
   `.01` 时 value `<.01`，0 时 exact zero。
2. 400 个弱 `pi/5` 转向即使填满 48-event winner，value 仍 `<1`、effective pairs
   `<.25`，不能仅靠 filler 数量越过机制门槛。
3. 集中链与摊薄链的 `individual_weight_sum` 完全相同，均为 `6.6510046672`；
   集中链 `linked_pair_mass=4.8382975247`、Flow `6.8462368441`，摊薄链
   `linked_pair_mass=0`、Flow `0`。这直接证明新公式测的是连续链，不是单点总量。
4. spinner/明确 section separator 前后不合并；只有当 coherence 与峰值来自同一
   section 时才能输出高 Flow。
5. 764517 +HDDT 回归要求 FULL coverage、`total_sr_used=false`、value `<2`、
   `linked_pair_mass<.75`；当前精确值为 `1.9170708116` 与 `.3641592788`。

这些测试不引用人工星数设阈值，同时保留真正集中连续 Flow 的高尾。本次文档更新
只记录已落盘修复与证据，不再修改公式或 runtime。

## cohort 与后续 gate

后续人工或非人工验证必须分开三类：

1. **常规谱面**：用于常规分布、盲测排序和误差描述。
2. **合法极端谱面**：用于确认同轴证据闭环和不裁高尾；不能因值高自动判异常。
3. **Aspire/adversarial**：单独成队，只检查解析覆盖、finite/abstention、局部证据归属、
   变形鲁棒性和跨段借证据；绝不进入常规 MAE、阈值、percentile 或 calibration。

当前 human BID 文件没有 Aspire 记录。测试中的 Aspire real-map case 只作为机制 provenance
压力测试，未并入上表任何统计。

建议优先级：

- **P1（已修复，必须保留）**：764517 +HDDT、弱转向 filler、集中链 > 同权重摊薄链、
  spinner/section 边界共同组成非人工 regression gate，防止单点累加语义回潮。
- **P2**：按 beta7 九轴定义重新采集 blind、多 reviewer、分 mods 的标签；Control/Jump、
  Precision/pre-aim、Raw/Stamina、Stamina/Endurance、Finger/规则长串必须给出互斥示例。
- **P2**：发布 gate 以 availability、同 section 证据闭环、mods/时间/空间变形不变量和
  合法极端保留为主；本 assisted panel 只设防灾报警，不设拟合目标。
- **P3**：积累足够盲测后再报告分 cohort 的 rank/误差；Aspire 永远单列。

## 可复现性与测试

审计时文件 SHA256：

```text
03a6def67800b4833c5cdb9f5406d7b5b55ed76ed24bb01b662d274d7fd2e157  human_responses.jsonl
1b6698226848bf7b939dd3dbfa7c0820f1f320dde137610a94a05d9772631669  model_v010_beta7.py
d527553ce0c7004be8070588bc274aa6c9c9b46bd0bfe4e05013f95482863510  paired_transition_geometry_v01.py
3b372bf1657d016621c8aed8d6fbfda9266e7aae731d1fcf9cfea3a88ddeb3f7  spatial_axes_v02.py
74a4168be1dd379e8f0609b4aea3fefeedae1c91ab67abe6d8b23970aa828e4f  tapping_axes_v02.py
4cbfd89be91e2e111c92514ff1ab65cf368639b9ba856a7e7a73925fefefa21b  reading_order_v02.py
5aed6fa45201a8456e21b1c0b5f109e74be513638a4389423f3262d22ae177ee  profile_semantics_v01.py
```

上述代码 hash 是初次人工审计快照。Flow P1 跟进重算使用的当前文件为：

```text
41a96c4366a57134ab204699a29d4d056784f6d8aa841c68cd8b68980373cc22  model_v010_beta7.py
5caa4315f0cd8e6dd761fe93bf057d51f69b53f968c6569f3142438e3976b444  spatial_axes_v02.py
3b96e7c4711b61892bc41d781941fd5ed79751411b400f4714cf2422d489b00c  test_spatial_axes_v02.py
```

跟进时对 30 个去重 Flow approximate 点重算，表中 Flow 统计与个案均已按新
相邻乘积链更新；这仍只是 assisted secondary panel，不是拟合运行。

Python 3.12.13。相关测试：

```text
python -m unittest \
  tests.test_profile_semantics_v01 \
  tests.test_spatial_axes_v02 \
  tests.test_tapping_axes_v02 \
  tests.test_reading_order_v02 \
  tests.test_map_demand_v010_beta7

Ran 65 tests in 2.091s — OK (skipped=1)
```

Flow P1 跟进另外单独运行：

```text
python -m unittest tests.test_spatial_axes_v02

Ran 23 tests in 0.716s — OK
```

唯一 skip 是默认关闭的 real-corpus extreme test。以
`OSU_SKILL_RUN_CORPUS_TESTS=1` 单独运行
`tests.test_tapping_axes_v02.OptionalRealExtremeTests` 后：

```text
Ran 1 test in 31.642s — OK
```

因此相关 66 项在显式启用 corpus 后均通过。缺失只来自人工 `SKIP`、旧八轴没有
Endurance，以及数据本身没有 blind/multi-reviewer/Aspire cohort；不是本次路径或 beta7
重算失败。
