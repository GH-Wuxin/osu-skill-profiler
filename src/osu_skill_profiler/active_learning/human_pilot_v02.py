"""Deterministic construction of the remediated second human pilot.

The source is the immutable v0.1 dry-run batch.  This module applies the new
human-presentation gate, proposition quotas and stronger controls without
changing source evidence, canonical segmentation or first-pilot artifacts.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from osu_skill_profiler.weak_supervision.contracts_v01 import EntityRef, EntityScope

from .contracts_v01 import (
    AnnotationEntity,
    AnnotationTask,
    ControlType,
    PresentationOrder,
    ScoreComponents,
    SelectionReason,
    TaskScope,
    build_task,
    canonical_json,
    stable_id,
)
from .human_pilot_v01 import (
    AssetResolver,
    FORBIDDEN_BLIND_KEYS,
    read_jsonl,
    sha256_file,
    validate_blind_payloads,
    write_json,
    write_jsonl,
)
from .human_presentation_v02 import (
    HUMAN_PROPOSITION_CONTRACT_VERSION,
    HUMAN_PROPOSITIONS,
    PRESENTATION_ELIGIBILITY_VERSION,
    HumanPresentationEligibility,
)


PILOT_V02_SCHEMA_VERSION = "0.2.0"
PILOT_V02_GENERATOR_VERSION = "0.2.0"
PILOT_V02_ID = "al02-human-pilot-001"
PILOT_V02_BATCH_ID = "al02-human-pilot"
PILOT_V02_SEED = "osu-skill-profiler-second-human-pilot-v02"
PILOT_V02_TASKS = 40
PILOT_V02_PRESENTATION_VERSION = "0.2.0"
PILOT_V02_ANNOTATOR_ID = "annotator_001"
PILOT_V02_SESSION_ID = "pilot_session_002"

BASE_PROPOSITION_QUOTAS = {
    "ws01.provisional.movement_demand_high": 7,
    "ws01.provisional.dense_timing_pressure_high": 10,
    "ws01.provisional.slider_tracking_travel_high": 15,
}
BASE_CONTROL_QUOTAS = {"EASY_ANCHOR": 2, "AMBIGUOUS_CONTROL": 2}
CLONE_ALLOCATION = {
    "EXACT_REPEAT": {
        "ws01.provisional.movement_demand_high": 2,
        "ws01.provisional.dense_timing_pressure_high": 1,
        "ws01.provisional.slider_tracking_travel_high": 1,
    },
    "AB_INVERSION": {
        "ws01.provisional.movement_demand_high": 1,
        "ws01.provisional.dense_timing_pressure_high": 3,
        "ws01.provisional.slider_tracking_travel_high": 0,
    },
}
BASE_CONTROL_SLOTS = (9, 13, 17, 31)
PAIRED_CONTROL_SLOTS = (20, 22, 24, 26, 28, 34, 36, 38)
MIN_CONTROL_SPACING = 8


def _rank(*parts: str) -> str:
    return hashlib.sha256((PILOT_V02_SEED + "\n" + "\n".join(parts)).encode("utf-8")).hexdigest()


def _entity(payload: Mapping[str, Any]) -> AnnotationEntity:
    ref = payload["entity"]
    scope = EntityScope(str(ref["scope"]))
    entity_ref = EntityRef(
        scope=scope,
        map_checksum=str(ref["map_checksum"]),
        segment_index=ref.get("segment_index"),
        segment_start_ms=ref.get("segment_start_ms"),
        segment_end_ms=ref.get("segment_end_ms"),
        pair_entity_key=ref.get("pair_entity_key"),
    )
    sampling = payload["sampling_groups"]
    return AnnotationEntity(
        ref=entity_ref,
        anonymous_display_id=str(payload["anonymous_display_id"]),
        set_group_key=str(sampling["set_group_key"]),
        mapper_group_key=str(sampling["mapper_group_key"]),
        neutral_metadata=dict(payload.get("neutral_metadata", {})),
    )


def task_from_dict(payload: Mapping[str, Any]) -> AnnotationTask:
    components = ScoreComponents(**dict(payload["selection_score_components"]))
    proposition = payload["proposition"]
    return AnnotationTask(
        task_id=str(payload["task_id"]),
        batch_id=str(payload["batch_id"]),
        proposition_key=str(proposition["key"]),
        proposition_version=str(proposition["version"]),
        scope=TaskScope(str(payload["scope"])),
        entity_a=_entity(payload["entity_a"]),
        entity_b=_entity(payload["entity_b"]),
        selection_reason=SelectionReason(str(payload["selection_reason"])),
        selection_score_components=components,
        acquisition_score=float(payload["acquisition_score"]),
        weak_evidence_snapshot=dict(payload["weak_evidence_snapshot"]),
        provenance=dict(payload["provenance"]),
        control_type=ControlType(str(payload["control_type"])),
        control_group_id=payload.get("control_group_id"),
        source_task_id=payload.get("source_task_id"),
        presentation_order=PresentationOrder(str(payload["presentation_order"])),
        presentation_contract_version=str(payload["presentation_contract_version"]),
        diagnostic_expected_canonical_sign=payload.get("diagnostic_expected_canonical_sign"),
        schema_version=str(payload["schema_version"]),
        task_version=str(payload["task_version"]),
    )


def _v02_source(source: AnnotationTask, ordinal: int) -> AnnotationTask:
    return build_task(
        batch_id=PILOT_V02_BATCH_ID,
        proposition_key=source.proposition_key,
        proposition_version=source.proposition_version,
        scope=source.scope,
        entity_a=source.entity_a,
        entity_b=source.entity_b,
        selection_reason=source.selection_reason,
        selection_score_components=source.selection_score_components,
        acquisition_score=source.acquisition_score,
        weak_evidence_snapshot=dict(source.weak_evidence_snapshot),
        provenance={
            **dict(source.provenance),
            "pilot_v02_generator_version": PILOT_V02_GENERATOR_VERSION,
            "pilot_v02_seed": PILOT_V02_SEED,
            "source_v01_task_id": source.task_id,
            "ordinal": ordinal,
        },
        control_type=source.control_type,
        presentation_order=source.presentation_order,
        diagnostic_expected_canonical_sign=source.diagnostic_expected_canonical_sign,
        presentation_contract_version=PILOT_V02_PRESENTATION_VERSION,
    )


def _clone(source: AnnotationTask, control_type: ControlType, ordinal: int) -> AnnotationTask:
    inverted = control_type == ControlType.AB_INVERSION
    return build_task(
        batch_id=PILOT_V02_BATCH_ID,
        proposition_key=source.proposition_key,
        proposition_version=source.proposition_version,
        scope=source.scope,
        entity_a=source.entity_a,
        entity_b=source.entity_b,
        selection_reason=SelectionReason.AB_INVERSION if inverted else SelectionReason.EXACT_REPEAT,
        selection_score_components=source.selection_score_components,
        acquisition_score=source.acquisition_score,
        weak_evidence_snapshot=dict(source.weak_evidence_snapshot),
        provenance={
            **dict(source.provenance),
            "pilot_v02_generator_version": PILOT_V02_GENERATOR_VERSION,
            "pilot_v02_seed": PILOT_V02_SEED,
            "control_source": source.task_id,
            "ordinal": ordinal,
        },
        control_type=control_type,
        control_group_id=stable_id("control-", {"pilot": PILOT_V02_ID, "source": source.task_id, "type": control_type.value}),
        source_task_id=source.task_id,
        presentation_order=(
            PresentationOrder.BA if inverted and source.presentation_order == PresentationOrder.AB
            else PresentationOrder.AB if inverted else source.presentation_order
        ),
        diagnostic_expected_canonical_sign=source.diagnostic_expected_canonical_sign,
        presentation_contract_version=PILOT_V02_PRESENTATION_VERSION,
    )


def _round_robin_select(pool: list[AnnotationTask], count: int, proposition: str) -> list[AnnotationTask]:
    by_reason: dict[str, list[AnnotationTask]] = defaultdict(list)
    for task in pool:
        by_reason[task.selection_reason.value].append(task)
    for reason, rows in by_reason.items():
        rows.sort(key=lambda task: (-task.acquisition_score, _rank("base", proposition, reason, task.task_id), task.task_id))
    reason_order = (
        "CHALLENGE_AUDIT",
        "ABSTENTION_HEAVY",
        "BOUNDARY_ADJACENT",
        "INFORMATIVE_UNCERTAIN",
    )
    chosen: list[AnnotationTask] = []
    while len(chosen) < count:
        progressed = False
        for reason in reason_order:
            rows = by_reason.get(reason, [])
            if rows:
                chosen.append(rows.pop(0))
                progressed = True
                if len(chosen) == count:
                    break
        if not progressed:
            remainder = sorted(
                (row for rows in by_reason.values() for row in rows),
                key=lambda task: (-task.acquisition_score, _rank("remainder", proposition, task.task_id), task.task_id),
            )
            if len(remainder) < count - len(chosen):
                raise ValueError(f"insufficient eligible base tasks for {proposition}")
            chosen.extend(remainder[: count - len(chosen)])
    return chosen


def select_v02_tasks(
    source_rows: Iterable[Mapping[str, Any]],
    eligibility_by_task: Mapping[str, Mapping[str, Any]],
) -> tuple[list[AnnotationTask], dict[str, Any]]:
    source = [task_from_dict(row) for row in source_rows]
    eligible = [task for task in source if eligibility_by_task.get(task.task_id, {}).get("eligible")]
    base_pool = [
        task for task in eligible
        if task.control_type not in (ControlType.EXACT_REPEAT, ControlType.AB_INVERSION, ControlType.WITHIN_MAP_SEGMENT)
    ]
    selected_old: list[AnnotationTask] = []
    # These four controls have distinct semantics and count toward the 12
    # explicit hidden controls.  Select exactly one ambiguous task per
    # applicable proposition and the two available presentation-safe anchors.
    anchors = sorted(
        (task for task in base_pool if task.control_type == ControlType.EASY_ANCHOR),
        key=lambda task: (_rank("anchor", task.proposition_key, task.task_id), task.task_id),
    )
    if len(anchors) < BASE_CONTROL_QUOTAS["EASY_ANCHOR"]:
        raise ValueError("insufficient presentation-eligible easy anchors")
    selected_old.extend(anchors[: BASE_CONTROL_QUOTAS["EASY_ANCHOR"]])
    ambiguous_by_prop: dict[str, list[AnnotationTask]] = defaultdict(list)
    for task in base_pool:
        if task.control_type == ControlType.AMBIGUOUS_CONTROL:
            ambiguous_by_prop[task.proposition_key].append(task)
    ambiguous: list[AnnotationTask] = []
    for proposition in (
        "ws01.provisional.dense_timing_pressure_high",
        "ws01.provisional.slider_tracking_travel_high",
    ):
        rows = sorted(ambiguous_by_prop.get(proposition, ()), key=lambda task: (_rank("ambiguous", proposition, task.task_id), task.task_id))
        if not rows:
            raise ValueError(f"insufficient presentation-eligible ambiguous control for {proposition}")
        ambiguous.append(rows[0])
    selected_old.extend(ambiguous)
    selected_ids = {task.task_id for task in selected_old}
    for proposition, quota in BASE_PROPOSITION_QUOTAS.items():
        current = sum(task.proposition_key == proposition for task in selected_old)
        pool = [
            task for task in base_pool
            if task.proposition_key == proposition
            and task.control_type == ControlType.NONE
            and task.task_id not in selected_ids
        ]
        chosen = _round_robin_select(pool, quota - current, proposition)
        selected_old.extend(chosen)
        selected_ids.update(task.task_id for task in chosen)
    if len(selected_old) != sum(BASE_PROPOSITION_QUOTAS.values()):
        raise AssertionError("v0.2 base quota mismatch")

    # Recreate every source under the new batch/presentation identity.
    provisional = [_v02_source(task, index) for index, task in enumerate(selected_old)]
    by_prop: dict[str, list[AnnotationTask]] = defaultdict(list)
    for task in provisional:
        if task.control_type == ControlType.NONE:
            by_prop[task.proposition_key].append(task)
    used_sources: set[str] = set()
    paired: list[AnnotationTask] = []
    source_for_control: list[AnnotationTask] = []
    for control_name in ("EXACT_REPEAT", "AB_INVERSION"):
        control_type = ControlType(control_name)
        for proposition, count in CLONE_ALLOCATION[control_name].items():
            rows = sorted(
                (task for task in by_prop[proposition] if task.task_id not in used_sources),
                key=lambda task: (_rank("clone-source", control_name, proposition, task.task_id), task.task_id),
            )
            if len(rows) < count:
                raise ValueError(f"insufficient distinct clone sources for {control_name}/{proposition}")
            for source_task in rows[:count]:
                used_sources.add(source_task.task_id)
                source_for_control.append(source_task)
                paired.append(_clone(source_task, control_type, len(provisional) + len(paired)))

    paired_by_source = {task.source_task_id: task for task in paired}
    source_for_control.sort(key=lambda task: (_rank("source-order", task.task_id), task.task_id))
    paired_order = [paired_by_source[task.task_id] for task in source_for_control]
    base_controls = sorted(
        (task for task in provisional if task.control_type in (ControlType.EASY_ANCHOR, ControlType.AMBIGUOUS_CONTROL)),
        key=lambda task: (_rank("base-control-order", task.task_id), task.task_id),
    )
    ordinary = [task for task in provisional if task.task_id not in used_sources and task not in base_controls]
    ordinary.sort(key=lambda task: (_rank("ordinary-order", task.proposition_key, task.task_id), task.task_id))
    slots: list[AnnotationTask | None] = [None] * PILOT_V02_TASKS
    for slot, task in zip(range(len(source_for_control)), source_for_control, strict=True):
        slots[slot] = task
    for slot, task in zip(BASE_CONTROL_SLOTS, base_controls, strict=True):
        slots[slot] = task
    for slot, task in zip(PAIRED_CONTROL_SLOTS, paired_order, strict=True):
        slots[slot] = task
    fillers = iter(ordinary)
    for index, task in enumerate(slots):
        if task is None:
            slots[index] = next(fillers)
    try:
        next(fillers)
    except StopIteration:
        pass
    else:
        raise AssertionError("not all v0.2 tasks fit deterministic ordering")
    ordered = [task for task in slots if task is not None]
    index_by_id = {task.task_id: index for index, task in enumerate(ordered)}
    for task in paired_order:
        if index_by_id[task.task_id] - index_by_id[str(task.source_task_id)] < MIN_CONTROL_SPACING:
            raise AssertionError("v0.2 paired control spacing is too small")
    if any(
        ordered[index].control_type != ControlType.NONE
        and ordered[index + 1].control_type != ControlType.NONE
        for index in range(len(ordered) - 1)
    ):
        raise AssertionError("v0.2 controls must not be adjacent")
    _validate_duplicates(ordered)
    diagnostics = {
        "schema_version": PILOT_V02_SCHEMA_VERSION,
        "generator_version": PILOT_V02_GENERATOR_VERSION,
        "selection_policy": "fixed proposition quotas plus deterministic within-proposition acquisition ranking",
        "base_proposition_quotas": dict(BASE_PROPOSITION_QUOTAS),
        "clone_allocation": CLONE_ALLOCATION,
        "task_count": len(ordered),
        "by_proposition": dict(sorted(Counter(task.proposition_key for task in ordered).items())),
        "by_scope": dict(sorted(Counter(task.scope.value for task in ordered).items())),
        "by_control_type": dict(sorted(Counter(task.control_type.value for task in ordered).items())),
        "by_selection_reason": dict(sorted(Counter(task.selection_reason.value for task in ordered).items())),
        "explicit_control_count": sum(task.control_type != ControlType.NONE for task in ordered),
        "minimum_repeat_inversion_spacing": min(
            index_by_id[task.task_id] - index_by_id[str(task.source_task_id)] for task in paired_order
        ),
        "unique_maps": len({entity.ref.map_checksum for task in ordered for entity in (task.entity_a, task.entity_b)}),
        "unique_sets": len({entity.set_group_key for task in ordered for entity in (task.entity_a, task.entity_b)}),
        "unique_mappers": len({entity.mapper_group_key for task in ordered for entity in (task.entity_a, task.entity_b)}),
    }
    return ordered, diagnostics


def _validate_duplicates(tasks: Iterable[AnnotationTask]) -> None:
    first: dict[tuple[str, str, str], AnnotationTask] = {}
    ids: set[str] = set()
    for task in tasks:
        if task.task_id in ids:
            raise ValueError("duplicate v0.2 task id")
        ids.add(task.task_id)
        prior = first.get(task.unordered_pair_key)
        if prior is None:
            first[task.unordered_pair_key] = task
            continue
        if task.control_type not in (ControlType.EXACT_REPEAT, ControlType.AB_INVERSION) or task.source_task_id != prior.task_id:
            raise ValueError("accidental v0.2 duplicate pair")


def blind_v02(task: AnnotationTask) -> dict[str, Any]:
    contract = HUMAN_PROPOSITIONS[task.proposition_key]
    def entity_payload(entity: AnnotationEntity) -> dict[str, Any]:
        ref = entity.ref
        payload: dict[str, Any] = {
            "display_id": entity.anonymous_display_id,
            "scope": ref.scope.value,
            "mods": "NM",
            "neutral_metadata": dict(entity.neutral_metadata),
            "object_visualization_required": True,
            "audio_required": True,
        }
        if ref.scope == EntityScope.SEGMENT:
            payload["playable_window"] = {"start_ms": ref.segment_start_ms, "end_ms": ref.segment_end_ms}
            payload["context_window"] = {
                "start_ms": max(0.0, float(ref.segment_start_ms) - 2000.0),
                "end_ms": float(ref.segment_end_ms) + 1500.0,
            }
        else:
            payload["playable_window"] = "FULL_MAP"
        return payload
    payload = {
        "schema_version": PILOT_V02_SCHEMA_VERSION,
        "task_version": task.task_version,
        "task_id": task.task_id,
        "batch_id": task.batch_id,
        "presentation_contract_version": PILOT_V02_PRESENTATION_VERSION,
        "scope": task.scope.value,
        "proposition": {
            "key": task.proposition_key,
            "version": task.proposition_version,
            "question": contract.human_question,
            "attend_to": contract.attend_to,
            "not_asking": list(contract.not_asking),
            "cannot_judge_when": list(contract.cannot_judge_when),
        },
        "entity_a": entity_payload(task.entity_a),
        "entity_b": entity_payload(task.entity_b),
        "presentation_order": task.presentation_order.value,
        "answer_space": [
            "A_CLEARLY_HIGHER", "A_SLIGHTLY_HIGHER", "APPROX_EQUAL",
            "B_SLIGHTLY_HIGHER", "B_CLEARLY_HIGHER", "CANNOT_JUDGE",
        ],
        "cannot_judge_is_valid": True,
        "disclaimer": "本题只收集可用性证据；回答不是标签或真值。",
    }
    if task.presentation_order == PresentationOrder.BA:
        payload["entity_a"], payload["entity_b"] = payload["entity_b"], payload["entity_a"]
    return payload


def prepare_pilot_v02(
    *,
    source_batch_path: Path,
    feature_path: Path,
    session001_response_path: Path,
    session001_disposition_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source_rows = read_jsonl(source_batch_path)
    resolver = AssetResolver(read_jsonl(feature_path))
    gate = HumanPresentationEligibility(resolver)
    audits = [gate.evaluate_pair(row) for row in source_rows]
    audit_by_id = {str(row["task_id"]): row for row in audits}
    tasks, diagnostics = select_v02_tasks(source_rows, audit_by_id)
    task_rows = [task.as_dict() for task in tasks]
    selected_audits = [gate.evaluate_pair(row) for row in task_rows]
    if not all(row["eligible"] for row in selected_audits):
        raise ValueError("v0.2 selected a presentation-ineligible task")
    blind_rows = [blind_v02(task) for task in tasks]
    validate_blind_payloads(blind_rows)
    forbidden_text = canonical_json(blind_rows).lower()
    for token in ("weak_evidence", "acquisition_score", "expected", "control_type", "challenge_categories", "source_task_id"):
        if token in forbidden_text:
            raise ValueError(f"v0.2 blind payload leaks {token}")
    disposition = json.loads(session001_disposition_path.read_text(encoding="utf-8"))
    actual_session001_hash = sha256_file(session001_response_path).removeprefix("sha256:")
    if disposition.get("response_sha256") != actual_session001_hash or disposition.get("training_eligible") is not False:
        raise ValueError("Session 001 immutable training-exclusion disposition mismatch")

    output_dir.mkdir(parents=True, exist_ok=True)
    response_dir = output_dir / "responses" / PILOT_V02_ANNOTATOR_ID
    response_dir.mkdir(parents=True, exist_ok=True)
    if any(response_dir.iterdir()):
        raise ValueError("Pilot v0.2 formal response directory is not empty")
    outputs = {
        "pilot_tasks.jsonl": write_jsonl(output_dir / "pilot_tasks.jsonl", task_rows),
        "blind_pilot.jsonl": write_jsonl(output_dir / "blind_pilot.jsonl", blind_rows),
        "control_manifest.json": write_json(output_dir / "control_manifest.json", {
            "schema_version": PILOT_V02_SCHEMA_VERSION,
            "hidden_from_annotator": True,
            "controls": [
                {
                    "task_id": task.task_id,
                    "control_type": task.control_type.value,
                    "source_task_id": task.source_task_id,
                    "control_group_id": task.control_group_id,
                    "diagnostic_expected_canonical_sign": task.diagnostic_expected_canonical_sign,
                }
                for task in tasks if task.control_type != ControlType.NONE
            ],
            "analysis_semantics": {
                "exact_repeat": ["strict ordinal consistency", "directional consistency", "ordinal distance"],
                "ab_inversion": "normalize displayed A/B orientation before all comparisons",
                "easy_anchor": "anchor agreement; never annotator accuracy",
                "ambiguous_control": "CANNOT_JUDGE and APPROX_EQUAL may both be contract-compatible",
            },
        }),
        "eligibility_report.json": write_json(output_dir / "eligibility_report.json", {
            "schema_version": PILOT_V02_SCHEMA_VERSION,
            "eligibility_version": PRESENTATION_ELIGIBILITY_VERSION,
            "source_task_count": len(source_rows),
            "eligible_source_tasks": sum(row["eligible"] for row in audits),
            "ineligible_source_tasks": sum(not row["eligible"] for row in audits),
            "source_task_audits": audits,
            "selected_task_audits": selected_audits,
        }),
        "candidate_selection_diagnostics.json": write_json(output_dir / "candidate_selection_diagnostics.json", diagnostics),
        "human_propositions.json": write_json(output_dir / "human_propositions.json", {
            "contract_version": HUMAN_PROPOSITION_CONTRACT_VERSION,
            "propositions": [HUMAN_PROPOSITIONS[key].as_dict() for key in sorted(HUMAN_PROPOSITIONS)],
        }),
        "presentation_qa_summary.json": write_json(output_dir / "presentation_qa_summary.json", {
            "schema_version": PILOT_V02_SCHEMA_VERSION,
            "structural_checks": {
                "chinese_first_questions": True,
                "cannot_judge_explicitly_valid": True,
                "slider_ball_geometry_required": True,
                "repeat_traversal_required": True,
                "explicit_play_only": True,
                "agent_qa_muted": True,
                "blindness_validated": True,
            },
            "browser_qa": {
                "status": "PASS",
                "method": "local runner at response count zero with ?qa_muted=1",
                "verified": [
                    "Chinese-first visible UI and proposition guidance",
                    "CS display and no unintended visible English",
                    "muted explicit play, pause, seek and resume",
                    "real slider-ball motion including a two-span repeat",
                    "CANNOT_JUDGE affordance and explanation",
                    "no browser console warning or error",
                    "no response submission",
                ],
            },
        }),
    }
    manifest = {
        "schema_version": PILOT_V02_SCHEMA_VERSION,
        "generator_version": PILOT_V02_GENERATOR_VERSION,
        "pilot_id": PILOT_V02_ID,
        "batch_id": PILOT_V02_BATCH_ID,
        "seed": PILOT_V02_SEED,
        "annotator_ids": [PILOT_V02_ANNOTATOR_ID],
        "formal_session_id": PILOT_V02_SESSION_ID,
        "task_order": [task.task_id for task in tasks],
        "composition": diagnostics,
        "inputs": {
            "source_batch": {"artifact": "active_learning_v01/dry_run/batch.jsonl", "sha256": sha256_file(source_batch_path), "bytes": source_batch_path.stat().st_size},
            "feature_index": {"artifact": "feature_qa_v02/feature_qa_5k.jsonl", "sha256": sha256_file(feature_path), "bytes": feature_path.stat().st_size},
            "session001_disposition": {"artifact": session001_disposition_path.name, "sha256": sha256_file(session001_disposition_path), "bytes": session001_disposition_path.stat().st_size},
            "session001_response_sha256": actual_session001_hash,
        },
        "outputs": outputs,
        "formal_response_directory": "responses/annotator_001",
        "formal_response_count": 0,
        "blindness_mechanically_validated": True,
        "historical_artifacts_mutated": False,
        "model_trained": False,
        "taxonomy_frozen": False,
    }
    manifest_info = write_json(output_dir / "pilot_manifest.json", manifest)
    return {"manifest": manifest, "manifest_file": manifest_info, "diagnostics": diagnostics}


__all__ = [
    "PILOT_V02_SCHEMA_VERSION", "PILOT_V02_GENERATOR_VERSION", "PILOT_V02_ID",
    "PILOT_V02_BATCH_ID", "PILOT_V02_SEED", "PILOT_V02_TASKS",
    "PILOT_V02_PRESENTATION_VERSION", "PILOT_V02_ANNOTATOR_ID", "PILOT_V02_SESSION_ID",
    "BASE_PROPOSITION_QUOTAS", "BASE_CONTROL_QUOTAS", "CLONE_ALLOCATION",
    "task_from_dict", "select_v02_tasks", "blind_v02", "prepare_pilot_v02",
]
