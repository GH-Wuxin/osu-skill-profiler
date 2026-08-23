"""Deterministic, fail-closed analysis of multi-annotator pilot collections.

This module reads the real append-only response files produced by the v0.2
multi-annotator runner.  It never mutates the live collection, never converts
human judgements into ground truth, and never authorises training.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping

from .contracts_v01 import (
    AnnotationResponse,
    ConfidenceBand,
    PairwiseAnswer,
    PresentationOrder,
    ResponseLedger,
    canonical_answer,
    canonical_json,
    stable_id,
)
from .human_pilot_v01 import read_jsonl
from .human_pilot_v02 import PILOT_V02_ID, task_from_dict
from .metrics_v01 import annotation_metrics


COLLECTION_ANALYSIS_VERSION = "0.1.0"
COLLECTION_SNAPSHOT_VERSION = "0.1.0"
SUPPORTED_COLLECTION_SCHEMAS = frozenset({"0.4.0", "0.5.0", "0.6.0"})
TRAINING_ELIGIBLE = False
HUMAN_EVIDENCE_IS_GROUND_TRUTH = False


@dataclass(frozen=True)
class CapturedParticipant:
    annotator_id: str
    session_id: str
    response_path: str
    assigned_task_ids: tuple[str, ...]
    response_bytes: bytes
    response_rows: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class CollectionCapture:
    collection_id: str
    registry_sha256: str
    pilot_tasks_sha256: str
    allocated_participant_count: int
    task_rows: tuple[Mapping[str, Any], ...]
    tasks: tuple[Any, ...]
    participants: tuple[CapturedParticipant, ...]
    responses: tuple[AnnotationResponse, ...]
    raw_response_rows: tuple[Mapping[str, Any], ...]
    human_evidence_rows: tuple[Mapping[str, Any], ...]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json_bytes(data: bytes, *, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not strict UTF-8 JSON") from exc


def _load_jsonl_bytes(data: bytes, *, label: str) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} is not UTF-8") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label}:{line_number} is not strict JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{label}:{line_number} must be a JSON object")
        rows.append(row)
    return rows


def _safe_response_path(collection_dir: Path, relative: str) -> Path:
    candidate = (collection_dir / relative).resolve()
    try:
        candidate.relative_to(collection_dir.resolve())
    except ValueError as exc:
        raise ValueError("response_path escapes collection directory") from exc
    return candidate


def _optional_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _stable_collection_read(
    collection_dir: Path,
    *,
    max_attempts: int,
) -> tuple[bytes, dict[str, bytes | None]]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    registry_path = collection_dir / "collection.json"
    for _ in range(max_attempts):
        registry_before = registry_path.read_bytes()
        registry = _load_json_bytes(registry_before, label="collection.json")
        if not isinstance(registry, dict) or not isinstance(registry.get("participants"), list):
            raise ValueError("collection registry participants must be a list")
        declared = {
            str(entry.get("response_path", "")): _safe_response_path(
                collection_dir, str(entry.get("response_path", "")),
            )
            for entry in registry["participants"]
            if isinstance(entry, dict)
        }
        first = {relative: _optional_bytes(path) for relative, path in declared.items()}
        registry_after = registry_path.read_bytes()
        second = {relative: _optional_bytes(path) for relative, path in declared.items()}
        if registry_before == registry_after and first == second:
            return registry_before, first
    raise RuntimeError("collection changed during capture; retry after the current submission settles")


def _validate_registry(
    registry: Mapping[str, Any],
    *,
    task_ids: set[str],
    collection_dir: Path,
) -> tuple[list[dict[str, Any]], set[Path]]:
    if registry.get("schema_version") not in SUPPORTED_COLLECTION_SCHEMAS:
        raise ValueError("unsupported collection registry schema")
    if registry.get("pilot_id") != PILOT_V02_ID:
        raise ValueError("collection pilot identity mismatch")
    if registry.get("tasks_per_participant") != 5:
        raise ValueError("collection tasks_per_participant mismatch")
    expandable = registry.get("schema_version") == "0.6.0"
    if expandable and registry.get("task_batch_size") != 5:
        raise ValueError("collection task_batch_size mismatch")
    pool = registry.get("task_pool")
    if not isinstance(pool, list) or len(pool) != 40 or len(set(pool)) != 40:
        raise ValueError("collection must expose exactly 40 unique tasks")
    if set(str(value) for value in pool) != task_ids:
        raise ValueError("collection task pool does not match immutable pilot tasks")
    collection_id = registry.get("collection_id")
    if not isinstance(collection_id, str) or not collection_id:
        raise ValueError("collection identity missing")

    participants = registry.get("participants")
    if not isinstance(participants, list):
        raise ValueError("participants must be a list")
    annotators: set[str] = set()
    sessions: set[str] = set()
    response_paths: set[Path] = set()
    validated: list[dict[str, Any]] = []
    for raw in participants:
        if not isinstance(raw, dict):
            raise ValueError("participant entry must be an object")
        annotator_id = raw.get("annotator_id")
        session_id = raw.get("session_id")
        response_path = raw.get("response_path")
        assigned = raw.get("task_ids")
        token_digest = raw.get("session_token_hash")
        if not all(isinstance(value, str) and value for value in (annotator_id, session_id, response_path)):
            raise ValueError("participant identity/path missing")
        if not isinstance(token_digest, str) or len(token_digest) != 64:
            raise ValueError("participant token hash is invalid")
        valid_assignment_size = (
            isinstance(assigned, list)
            and (
                len(assigned) == 5
                if not expandable
                else 5 <= len(assigned) <= len(task_ids) and len(assigned) % 5 == 0
            )
        )
        if not valid_assignment_size or len(set(assigned)) != len(assigned) or not set(str(value) for value in assigned) <= task_ids:
            raise ValueError("participant assignment is invalid")
        path = _safe_response_path(collection_dir, response_path)
        if annotator_id in annotators or session_id in sessions or path in response_paths:
            raise ValueError("duplicate participant identity, session, or response path")
        annotators.add(annotator_id)
        sessions.add(session_id)
        response_paths.add(path)
        validated.append({
            "annotator_id": annotator_id,
            "session_id": session_id,
            "response_path": response_path,
            "task_ids": [str(value) for value in assigned],
        })
    return validated, response_paths


def _response_from_row(row: Mapping[str, Any]) -> AnnotationResponse:
    required = {
        "response_id", "task_id", "task_version", "batch_id", "annotator_id",
        "session_id", "answer", "presentation_order", "reason_codes",
        "provenance", "schema_version", "response_version", "pilot_id",
        "response_timestamp_utc",
    }
    missing = sorted(required - set(row))
    if missing:
        raise ValueError(f"response missing required fields: {missing}")
    timestamp = row["response_timestamp_utc"]
    if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
        raise ValueError("response timestamp must be UTC with Z suffix")
    try:
        datetime.fromisoformat(timestamp.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError("response timestamp is invalid") from exc
    if row.get("pilot_id") != PILOT_V02_ID:
        raise ValueError("response pilot identity mismatch")
    provenance = row.get("provenance")
    if (
        not isinstance(provenance, dict)
        or provenance.get("pilot_id") != PILOT_V02_ID
        or provenance.get("explicit_human_submission") is not True
    ):
        raise ValueError("response provenance is not an explicit human submission")
    reasons = row.get("reason_codes")
    if not isinstance(reasons, list):
        raise ValueError("response reason_codes must be a list")
    response_time = row.get("response_time_ms")
    if response_time is not None and (not isinstance(response_time, int) or isinstance(response_time, bool)):
        raise ValueError("response_time_ms must be an integer")
    return AnnotationResponse(
        response_id=str(row["response_id"]),
        task_id=str(row["task_id"]),
        task_version=str(row["task_version"]),
        batch_id=str(row["batch_id"]),
        annotator_id=str(row["annotator_id"]),
        session_id=str(row["session_id"]),
        answer=PairwiseAnswer(str(row["answer"])),
        presentation_order=PresentationOrder(str(row["presentation_order"])),
        response_time_ms=response_time,
        confidence_band=(
            ConfidenceBand(str(row["confidence_band"]))
            if row.get("confidence_band") is not None else None
        ),
        reason_codes=tuple(str(value) for value in reasons),
        provenance=dict(provenance),
        schema_version=str(row["schema_version"]),
        response_version=str(row["response_version"]),
    )


def capture_collection(
    *,
    pilot_dir: Path,
    collection_dir: Path,
    max_attempts: int = 5,
) -> CollectionCapture:
    """Capture and validate one stable point-in-time view of a live collection."""

    pilot_dir = pilot_dir.resolve()
    collection_dir = collection_dir.resolve()
    task_path = pilot_dir / "pilot_tasks.jsonl"
    task_bytes = task_path.read_bytes()
    task_rows = _load_jsonl_bytes(task_bytes, label="pilot_tasks.jsonl")
    tasks = tuple(task_from_dict(row) for row in task_rows)
    task_ids = {task.task_id for task in tasks}
    if len(tasks) != 40 or len(task_ids) != 40:
        raise ValueError("immutable pilot must contain 40 unique tasks")

    registry_bytes, response_blobs = _stable_collection_read(
        collection_dir, max_attempts=max_attempts,
    )
    registry = _load_json_bytes(registry_bytes, label="collection.json")
    participants, declared_paths = _validate_registry(
        registry, task_ids=task_ids, collection_dir=collection_dir,
    )
    actual_files = set((collection_dir / "responses").rglob("*.jsonl"))
    actual_files = {path.resolve() for path in actual_files}
    if not actual_files <= declared_paths:
        raise ValueError("collection contains undeclared response files")

    task_by_id = {task.task_id: task for task in tasks}
    ledger = ResponseLedger(tasks, [row["annotator_id"] for row in participants])
    captured: list[CapturedParticipant] = []
    raw_rows: list[Mapping[str, Any]] = []
    responses: list[AnnotationResponse] = []
    for participant in participants:
        relative = participant["response_path"]
        blob = response_blobs.get(relative)
        if not blob:
            continue
        rows = _load_jsonl_bytes(blob, label=relative)
        if len(rows) > len(participant["task_ids"]):
            raise ValueError("participant response count exceeds assignment")
        expected_ids = participant["task_ids"][:len(rows)]
        if [str(row.get("task_id", "")) for row in rows] != expected_ids:
            raise ValueError("participant responses do not preserve assigned task order")
        parsed: list[AnnotationResponse] = []
        for row in rows:
            response = _response_from_row(row)
            if response.annotator_id != participant["annotator_id"]:
                raise ValueError("response annotator does not match response path owner")
            if response.session_id != participant["session_id"]:
                raise ValueError("response session does not match collection registry")
            expected_response_id = stable_id("response-", {
                "pilot_id": PILOT_V02_ID,
                "annotator_id": response.annotator_id,
                "session_id": response.session_id,
                "task_id": response.task_id,
            })
            if response.response_id != expected_response_id:
                raise ValueError("response identity is not the deterministic session/task identity")
            task = task_by_id.get(response.task_id)
            if task is None:
                raise ValueError("response references unknown pilot task")
            ledger.add(response)
            parsed.append(response)
            responses.append(response)
            raw_rows.append(dict(row))
        captured.append(CapturedParticipant(
            annotator_id=participant["annotator_id"],
            session_id=participant["session_id"],
            response_path=relative,
            assigned_task_ids=tuple(participant["task_ids"]),
            response_bytes=blob,
            response_rows=tuple(dict(row) for row in rows),
        ))

    return CollectionCapture(
        collection_id=str(registry["collection_id"]),
        registry_sha256=_sha256(registry_bytes),
        pilot_tasks_sha256=_sha256(task_bytes),
        allocated_participant_count=len(participants),
        task_rows=tuple(dict(row) for row in task_rows),
        tasks=tasks,
        participants=tuple(captured),
        responses=tuple(responses),
        raw_response_rows=tuple(raw_rows),
        human_evidence_rows=tuple(row.as_dict() for row in ledger.evidence),
    )


def _quantile(values: list[int], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _direction(answer: PairwiseAnswer) -> int | None:
    if answer == PairwiseAnswer.CANNOT_JUDGE:
        return None
    if answer in (PairwiseAnswer.A_CLEARLY_HIGHER, PairwiseAnswer.A_SLIGHTLY_HIGHER):
        return 1
    if answer in (PairwiseAnswer.B_CLEARLY_HIGHER, PairwiseAnswer.B_SLIGHTLY_HIGHER):
        return -1
    return 0


def _ordinal(answer: PairwiseAnswer) -> int | None:
    return {
        PairwiseAnswer.B_CLEARLY_HIGHER: -2,
        PairwiseAnswer.B_SLIGHTLY_HIGHER: -1,
        PairwiseAnswer.APPROX_EQUAL: 0,
        PairwiseAnswer.A_SLIGHTLY_HIGHER: 1,
        PairwiseAnswer.A_CLEARLY_HIGHER: 2,
        PairwiseAnswer.CANNOT_JUDGE: None,
    }[answer]


def _control_pair_summary(pairs: list[tuple[PairwiseAnswer, PairwiseAnswer]]) -> dict[str, Any]:
    comparable = directional_agree = strict_agree = excluded = 0
    distance_sum = 0.0
    for source_answer, control_answer in pairs:
        source_direction = _direction(source_answer)
        control_direction = _direction(control_answer)
        source_ordinal = _ordinal(source_answer)
        control_ordinal = _ordinal(control_answer)
        if source_direction is None or control_direction is None:
            excluded += 1
            continue
        assert source_ordinal is not None and control_ordinal is not None
        comparable += 1
        directional_agree += source_direction == control_direction
        strict_agree += source_answer == control_answer
        distance_sum += abs(source_ordinal - control_ordinal)
    return {
        "observed_pairs": len(pairs),
        "comparable_non_abstain_pairs": comparable,
        "abstention_excluded_pairs": excluded,
        "directional_agreement_rate": directional_agree / comparable if comparable else None,
        "strict_ordinal_agreement_rate": strict_agree / comparable if comparable else None,
        "mean_ordinal_distance": distance_sum / comparable if comparable else None,
    }


def _control_relationship_metrics(
    tasks: Iterable[Any],
    responses: Iterable[AnnotationResponse],
) -> dict[str, Any]:
    task_by_id = {task.task_id: task for task in tasks}
    by_task: dict[str, list[tuple[AnnotationResponse, PairwiseAnswer]]] = defaultdict(list)
    for response in responses:
        task = task_by_id[response.task_id]
        by_task[response.task_id].append((response, canonical_answer(task, response)))

    same_pairs: dict[str, list[tuple[PairwiseAnswer, PairwiseAnswer]]] = defaultdict(list)
    cross_pairs: dict[str, list[tuple[PairwiseAnswer, PairwiseAnswer]]] = defaultdict(list)
    represented_same: Counter[str] = Counter()
    represented_cross: Counter[str] = Counter()
    for task in tasks:
        if task.control_type.value not in ("EXACT_REPEAT", "AB_INVERSION") or not task.source_task_id:
            continue
        control_type = task.control_type.value
        left = by_task.get(task.source_task_id, [])
        right = by_task.get(task.task_id, [])
        relationship_same = relationship_cross = False
        for source_response, source_answer in left:
            for control_response, control_answer in right:
                if source_response.annotator_id == control_response.annotator_id:
                    relationship_same = True
                    same_pairs[control_type].append((source_answer, control_answer))
                else:
                    relationship_cross = True
                    cross_pairs[control_type].append((source_answer, control_answer))
        represented_same[control_type] += relationship_same
        represented_cross[control_type] += relationship_cross

    def section(
        rows: Mapping[str, list[tuple[PairwiseAnswer, PairwiseAnswer]]],
        represented: Mapping[str, int],
        interpretation: str,
    ) -> dict[str, Any]:
        all_pairs = [pair for values in rows.values() for pair in values]
        return {
            **_control_pair_summary(all_pairs),
            "represented_control_relationships": sum(represented.values()),
            "by_control_type": {
                control_type: {
                    **_control_pair_summary(rows.get(control_type, [])),
                    "represented_control_relationships": represented.get(control_type, 0),
                }
                for control_type in ("EXACT_REPEAT", "AB_INVERSION")
            },
            "interpretation": interpretation,
        }
    return {
        "same_annotator": section(
            same_pairs,
            represented_same,
            "explicit source/control pairs answered by the same annotator; bounded diagnostic only",
        ),
        "cross_annotator": section(
            cross_pairs,
            represented_cross,
            (
                "cross-annotator control comparison; combines presentation/control stability "
                "with annotator disagreement and is not intra-annotator reliability"
            ),
        ),
    }


def _task_overlap_diagnostics(
    tasks: Iterable[Any],
    responses: Iterable[AnnotationResponse],
) -> list[dict[str, Any]]:
    task_by_id = {task.task_id: task for task in tasks}
    by_task: dict[str, list[AnnotationResponse]] = defaultdict(list)
    for response in responses:
        by_task[response.task_id].append(response)
    rows: list[dict[str, Any]] = []
    for task_id in sorted(by_task):
        task_responses = by_task[task_id]
        if len(task_responses) < 2:
            continue
        task = task_by_id[task_id]
        canonical = [canonical_answer(task, response) for response in task_responses]
        directions = [_direction(answer) for answer in canonical]
        ordinals = [_ordinal(answer) for answer in canonical]
        comparable = agreement = 0
        distance_sum = 0.0
        for left in range(len(canonical)):
            for right in range(left + 1, len(canonical)):
                if directions[left] is None or directions[right] is None:
                    continue
                assert ordinals[left] is not None and ordinals[right] is not None
                comparable += 1
                agreement += directions[left] == directions[right]
                distance_sum += abs(ordinals[left] - ordinals[right]) / 4.0
        rows.append({
            "task_id": task_id,
            "proposition_key": task.proposition_key,
            "scope": task.scope.value,
            "control_type": task.control_type.value,
            "response_count": len(task_responses),
            "canonical_response_distribution": dict(sorted(Counter(
                answer.value for answer in canonical
            ).items())),
            "comparable_non_abstain_pairs": comparable,
            "directional_agreement_rate": agreement / comparable if comparable else None,
            "mean_normalized_ordinal_distance": distance_sum / comparable if comparable else None,
        })
    return rows


def analyze_capture(capture: CollectionCapture) -> dict[str, Any]:
    task_by_id = {task.task_id: task for task in capture.tasks}
    response_counts = Counter(response.task_id for response in capture.responses)
    coverage_histogram = Counter(response_counts.values())
    coverage_histogram[0] = len(capture.tasks) - len(response_counts)
    participant_counts = Counter(response.annotator_id for response in capture.responses)
    complete = sum(count == 5 for count in participant_counts.values())
    partial = sum(0 < count < 5 for count in participant_counts.values())
    response_times = [
        response.response_time_ms for response in capture.responses
        if response.response_time_ms is not None
    ]
    confidence = Counter(
        response.confidence_band.value if response.confidence_band else "UNSET"
        for response in capture.responses
    )
    note_count = sum(
        bool(str(response.provenance.get("optional_note") or "").strip())
        for response in capture.responses
    )

    by_dimension: dict[tuple[str, str], list[AnnotationResponse]] = defaultdict(list)
    for response in capture.responses:
        task = task_by_id[response.task_id]
        by_dimension[(task.proposition_key, task.scope.value)].append(response)
    strata: list[dict[str, Any]] = []
    for (proposition, scope), rows in sorted(by_dimension.items()):
        metrics = annotation_metrics(capture.tasks, rows)
        strata.append({
            "proposition_key": proposition,
            "scope": scope,
            "response_count": len(rows),
            "distinct_task_count": len({row.task_id for row in rows}),
            "response_distribution": metrics["response_distribution"],
            "abstention_count": metrics["abstention_count"],
            "abstention_rate": metrics["abstention_rate"],
            "directional_inter_annotator_agreement": metrics["directional_inter_annotator_agreement"],
            "weighted_ordinal_disagreement": metrics["weighted_ordinal_disagreement"],
        })

    metrics = annotation_metrics(capture.tasks, capture.responses)
    snapshot_identity = {
        "analysis_version": COLLECTION_ANALYSIS_VERSION,
        "snapshot_version": COLLECTION_SNAPSHOT_VERSION,
        "collection_id": capture.collection_id,
        "registry_sha256": capture.registry_sha256,
        "pilot_tasks_sha256": capture.pilot_tasks_sha256,
        "response_files": [
            {
                "annotator_id": participant.annotator_id,
                "response_path": participant.response_path,
                "sha256": _sha256(participant.response_bytes),
                "size": len(participant.response_bytes),
                "response_count": len(participant.response_rows),
            }
            for participant in capture.participants
        ],
    }
    return {
        "analysis_version": COLLECTION_ANALYSIS_VERSION,
        "snapshot_version": COLLECTION_SNAPSHOT_VERSION,
        "snapshot_id": stable_id("snapshot-", snapshot_identity),
        "collection_id": capture.collection_id,
        "source_integrity": snapshot_identity,
        "collection_state": {
            "allocated_participant_count": capture.allocated_participant_count,
            "responded_participant_count": len(participant_counts),
            "allocated_without_response_count": capture.allocated_participant_count - len(participant_counts),
            "complete_five_response_sessions": complete,
            "partial_sessions": partial,
            "response_count": len(capture.responses),
            "unique_response_id_count": len({row.response_id for row in capture.responses}),
            "task_pool_count": len(capture.tasks),
            "covered_task_count": len(response_counts),
            "coverage_histogram": {
                str(count): coverage_histogram[count] for count in sorted(coverage_histogram)
            },
        },
        "timing": {
            "recorded_response_count": len(response_times),
            "median_ms": statistics.median(response_times) if response_times else None,
            "p25_ms": _quantile(response_times, 0.25),
            "p75_ms": _quantile(response_times, 0.75),
            "interpretation": "recorded page elapsed time; not a direct measure of attention or expertise",
        },
        "confidence_distribution": dict(sorted(confidence.items())),
        "optional_note_count": note_count,
        "strata": strata,
        "metrics": metrics,
        "control_relationship_diagnostics": _control_relationship_metrics(
            capture.tasks, capture.responses,
        ),
        "task_overlap_diagnostics": _task_overlap_diagnostics(
            capture.tasks, capture.responses,
        ),
        "interpretation_boundaries": {
            "human_evidence_is_ground_truth": HUMAN_EVIDENCE_IS_GROUND_TRUTH,
            "training_eligible": TRAINING_ELIGIBLE,
            "taxonomy_frozen": False,
            "majority_vote_label_created": False,
            "partial_sessions_preserved": True,
            "raw_responses_preserved": True,
        },
    }


def _canonical_jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    materialized = list(rows)
    if not materialized:
        return b""
    return ("\n".join(canonical_json(dict(row)) for row in materialized) + "\n").encode("utf-8")


def _write_exact(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"refusing to overwrite non-identical snapshot file: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _report_markdown(analysis: Mapping[str, Any]) -> str:
    state = analysis["collection_state"]
    metrics = analysis["metrics"]
    overlap = metrics["directional_inter_annotator_agreement"]
    controls = analysis["control_relationship_diagnostics"]
    same_controls = controls["same_annotator"]
    cross_controls = controls["cross_annotator"]
    coverage_text = ", ".join(
        f"{count} 次：{tasks} 题" for count, tasks in state["coverage_histogram"].items()
    )
    lines = [
        "# 多人真人标注 Collection 分析 v0.1",
        "",
        f"Snapshot: `{analysis['snapshot_id']}`  ",
        f"Collection: `{analysis['collection_id']}`",
        "",
        "## 已观察到的收集状态",
        "",
        f"- 已分配编号：{state['allocated_participant_count']}",
        f"- 实际提交者：{state['responded_participant_count']}",
        f"- 完成 5 题：{state['complete_five_response_sessions']}",
        f"- 部分完成：{state['partial_sessions']}",
        f"- 有效原始回答：{state['response_count']}",
        f"- 已覆盖任务：{state['covered_task_count']} / {state['task_pool_count']}",
        f"- 覆盖次数分布：{coverage_text}",
        "",
        "## 保守诊断",
        "",
        f"- `CANNOT_JUDGE`：{metrics['abstention_count']}，占比 {metrics['abstention_rate']:.3f}",
        f"- 同题跨标注者可比对数：{overlap['annotator_pairs']}",
        f"- 同题方向一致率：{overlap['rate'] if overlap['rate'] is not None else '不可计算'}",
        f"- 同人显式 control 可比对数：{same_controls['comparable_non_abstain_pairs']}",
        f"- 跨人显式 control 可比对数：{cross_controls['comparable_non_abstain_pairs']}",
        "",
        "跨人 control 同时混合了题面/控制稳定性与不同玩家判断差异，不能称为同一标注者复测可靠性。",
        "",
        "## 分层结果",
        "",
        "| 命题 | 范围 | 回答 | 覆盖任务 | 弃答 | 同题方向一致率 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in analysis["strata"]:
        agreement = row["directional_inter_annotator_agreement"]["rate"]
        lines.append(
            f"| `{row['proposition_key']}` | {row['scope']} | {row['response_count']} | "
            f"{row['distinct_task_count']} | {row['abstention_count']} | "
            f"{agreement if agreement is not None else '不可计算'} |"
        )
    lines.extend([
        "",
        "## 解释边界",
        "",
        "- 这些记录是带来源的 HUMAN evidence，不是 ground truth。",
        "- 本快照不生成多数票标签，不授权训练，不冻结 taxonomy。",
        "- 未完成会话仍按原始回答保留，不补值、不猜测。",
        "- 后续新增回答必须形成新的内容哈希快照，不修改本快照。",
        "",
    ])
    return "\n".join(lines)


def write_snapshot(
    capture: CollectionCapture,
    *,
    output_root: Path,
) -> tuple[Path, dict[str, Any]]:
    analysis = analyze_capture(capture)
    snapshot_dir = output_root / str(analysis["snapshot_id"])
    responses_bytes = _canonical_jsonl(capture.raw_response_rows)
    evidence_bytes = _canonical_jsonl(capture.human_evidence_rows)
    analysis_bytes = (canonical_json(analysis) + "\n").encode("utf-8")
    report_bytes = (_report_markdown(analysis).rstrip() + "\n").encode("utf-8")
    files = {
        "responses.jsonl": responses_bytes,
        "human_evidence.jsonl": evidence_bytes,
        "analysis.json": analysis_bytes,
        "REPORT.md": report_bytes,
    }
    manifest = {
        "snapshot_version": COLLECTION_SNAPSHOT_VERSION,
        "snapshot_id": analysis["snapshot_id"],
        "collection_id": capture.collection_id,
        "files": {
            name: {"sha256": _sha256(data), "size": len(data)}
            for name, data in sorted(files.items())
        },
        "training_eligible": TRAINING_ELIGIBLE,
        "human_evidence_is_ground_truth": HUMAN_EVIDENCE_IS_GROUND_TRUTH,
    }
    files["manifest.json"] = (canonical_json(manifest) + "\n").encode("utf-8")
    for name, data in files.items():
        _write_exact(snapshot_dir / name, data)
    return snapshot_dir, analysis


__all__ = [
    "COLLECTION_ANALYSIS_VERSION",
    "COLLECTION_SNAPSHOT_VERSION",
    "CapturedParticipant",
    "CollectionCapture",
    "capture_collection",
    "analyze_capture",
    "write_snapshot",
]
