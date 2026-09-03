# docs/archive — 归档目录

本目录存放 2026-08-16 经用户确认后从 `docs/` 移入的**过期文档**。
文件内容保持原样未修改（frozen）；仓库内仍指向这些文档的引用已改为
`docs/archive/...` 路径。

规则：

- 归档文件是历史记录，不得编辑、覆盖或删除。
- 归档文件内部的相对链接可能仍指向移动前的 `docs/` 位置；这是历史快照的
  一部分，保持原样。仓库内**当前文档/测试/工具**的引用已同步更新。
- 如需重新启用，必须显式移回 `docs/` 并更新所有引用。
- 本次清理只移动 `docs/` 下的文档；`training/datasets/**`、`src/**`、
  tests 数据夹具与任何历史数据集均未改动。
- 未 commit、未 push。

## 本次归档清单（16 个文件）

| 文件 | 归档原因 |
|---|---|
| `ACTIVE_LEARNING_V01_HANDOVER_2026-08-13.md` | 实现前的交接文档，已被 `ACTIVE_LEARNING_ANNOTATION_DESIGN_V01.md` 与后续正式报告取代 |
| `WEAK_SUPERVISION_V01_HANDOVER_2026-08-13.md` | 实现前的交接文档，已被 `WEAK_SUPERVISION_INFRASTRUCTURE_V01.md` / Pilot 报告取代 |
| `HUMAN_CODE_GAP_AUDIT_V01_HANDOVER_2026-08-14.md` | 审计前的交接文档，已被 `HUMAN_CODE_GAP_AUDIT_V01.md` + `HUMAN_CODE_GAP_HYPOTHESIS_CHECK_V01.md` 取代 |
| `HUMAN_ANNOTATION_COLLECTION_001_ANALYSIS_V01.md` | interim 分析，已被 `HUMAN_ANNOTATION_COLLECTION_001_FINAL_ANALYSIS_V01.md` 取代 |
| `HUMAN_ANNOTATION_COLLECTION_001_DISPOSITION_V01.json` | interim 处置，已被 `HUMAN_ANNOTATION_COLLECTION_001_FINAL_DISPOSITION_V01.json` 取代 |
| `HUMAN_ANNOTATION_PILOT_SESSION_001_DISPOSITION.json` | 首个 pilot 的旧处置，已被 remediation 与 collection_001 final 取代 |
| `HUMAN_TARGETED_RETEST_V01.md` | V01 重测包，已被 `HUMAN_TARGETED_RETEST_V02.md`（0.2.1，已开放收集）取代 |
| `HUMAN_TARGETED_RETEST_V01.json` | 同上，V01 机器可读包 |
| `ACTIVE_LEARNING_DRY_RUN_V01_REPORT.md` | dry-run 报告；真实 collection_001 已完成并另有最终分析 |
| `SMALL_HUMAN_ANNOTATION_PILOT_V01.md` | “等待真人标注者”阶段的旧状态文档；该 pilot 已由 collection_001 完成 |
| `HUMAN_ANNOTATION_PILOT_REMEDIATION_V01.md` | 首个 pilot 的历史 remediation 报告；被 collection_001 final 与 code-gap audit 取代 |
| `FEATURE_CONTRACT_REVIEW_V0.md` | V0（104 字段）历史审计；当前为 Feature 0.2，迁移记录见 `docs/FEATURE_MIGRATION_V01_TO_V02.md` |
| `LOCAL_SIGNAL_V02_FINAL_REPORT.md` | Local 0.2 历史实现报告；当前契约为 Local 0.3 |
| `PPY_REFERENCE_SIGNAL_PARITY_V01.md` | Reference 0.1 历史 parity 报告；当前契约为 Reference 0.2 |
| `PPY_REFERENCE_SIGNAL_V01_FINAL_REPORT.md` | Reference 0.1 历史实现报告；当前契约为 Reference 0.2 |
| `SEGMENT_SIGNAL_QA_V01.md` | v0.1 历史 Segment QA 报告；修正版本由 Pre-ML Foundation Remediation 覆盖 |

## 本次同步更新的引用位置

- `README.md`（文档索引 + Local v0.2 报告链接）
- `docs/INDEPENDENT_RED_TEAM_AUDIT_V01.md`（2 处）
- `docs/HUMAN_CODE_GAP_AUDIT_V01.md`（handover 路径）
- `docs/HUMAN_QUESTION_DEFINITIONS_V02.md`（V01 retest 路径）
- `docs/HUMAN_TARGETED_RETEST_V02.md`（V01 retest 路径）
- `docs/PPY_DIFFICULTY_REFERENCE_AUDIT.md`（Feature V0 review 链接）
- `tests/test_human_annotation_collection_analysis_v01.py`
- `tests/test_human_annotation_remediation_v01.py`
- `tools/prepare_human_annotation_pilot_v02.py`
