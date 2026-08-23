"""Deterministic blind-presentation contract for pairwise annotation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts_v01 import AnnotationEntity, AnnotationTask, PresentationOrder, TaskScope


PRESENTATION_CONTRACT_VERSION = "0.1.0"

PROPOSITION_QUESTIONS = {
    "ws01.provisional.movement_demand_high": (
        "Which presented map or pattern demands more rapid or larger cursor movement?"
    ),
    "ws01.provisional.dense_timing_pressure_high": (
        "Which presented map or pattern demands more frequent hit timing?"
    ),
    "ws01.provisional.slider_tracking_travel_high": (
        "Which presented segment demands more sustained cursor travel while following sliders?"
    ),
}


@dataclass(frozen=True)
class PresentationContract:
    version: str = PRESENTATION_CONTRACT_VERSION
    segment_pre_roll_ms: int = 2000
    segment_post_roll_ms: int = 1500
    audio_policy: str = "REQUIRED_WHERE_AVAILABLE"
    object_visualization_policy: str = "REQUIRED"
    neighboring_context_policy: str = "REQUIRED"
    replay_video_policy: str = "OPTIONAL_NOT_ASSUMED_AVAILABLE"
    mod_policy: str = "UNMODDED_EXPLICIT"
    metadata_policy: str = "ANONYMOUS_NEUTRAL_SUBSET"
    blind_to_weak_evidence: bool = True
    blind_to_selection_metadata: bool = True
    blind_to_control_identity: bool = True
    blind_to_split_challenge_metadata: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "segment_context": {
                "pre_roll_ms": self.segment_pre_roll_ms,
                "post_roll_ms": self.segment_post_roll_ms,
                "neighboring_context": self.neighboring_context_policy,
            },
            "audio": self.audio_policy,
            "object_visualization": self.object_visualization_policy,
            "replay_video": self.replay_video_policy,
            "mods": self.mod_policy,
            "map_metadata": self.metadata_policy,
            "blindness": {
                "weak_evidence": self.blind_to_weak_evidence,
                "selection_metadata": self.blind_to_selection_metadata,
                "control_identity": self.blind_to_control_identity,
                "split_challenge_metadata": self.blind_to_split_challenge_metadata,
            },
            "statement": (
                "A segment is presented with its canonical playable window plus bounded context; "
                "the contract specifies required inputs but does not claim that replay/video assets exist."
            ),
        }


DEFAULT_PRESENTATION = PresentationContract()


def _entity_payload(entity: AnnotationEntity, scope: TaskScope, contract: PresentationContract) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "display_id": entity.anonymous_display_id,
        "scope": entity.ref.scope.value,
        "neutral_metadata": dict(entity.neutral_metadata),
        "mods": "NM",
        "audio_required_where_available": True,
        "object_visualization_required": True,
    }
    if scope == TaskScope.SEGMENT_PAIR:
        start = float(entity.ref.segment_start_ms or 0.0)
        end = float(entity.ref.segment_end_ms or start)
        payload["playable_window"] = {"start_ms": start, "end_ms": end}
        payload["context_window"] = {
            "start_ms": max(0.0, start - contract.segment_pre_roll_ms),
            "end_ms": end + contract.segment_post_roll_ms,
        }
        payload["neighboring_pattern_context_required"] = True
    else:
        payload["playable_window"] = "FULL_MAP"
    return payload


def blind_task_payload(
    task: AnnotationTask,
    contract: PresentationContract = DEFAULT_PRESENTATION,
) -> dict[str, Any]:
    if task.presentation_contract_version != contract.version:
        raise ValueError("task/presentation contract version mismatch")
    question = PROPOSITION_QUESTIONS.get(task.proposition_key)
    if question is None:
        raise ValueError("no reviewed human-facing question for provisional proposition")
    a = _entity_payload(task.entity_a, task.scope, contract)
    b = _entity_payload(task.entity_b, task.scope, contract)
    if task.presentation_order == PresentationOrder.BA:
        a, b = b, a
    return {
        "schema_version": task.schema_version,
        "task_id": task.task_id,
        "task_version": task.task_version,
        "batch_id": task.batch_id,
        "proposition": {
            "key": task.proposition_key,
            "version": task.proposition_version,
            "question": question,
            "provisional": True,
        },
        "scope": task.scope.value,
        "presentation_order": task.presentation_order.value,
        "entity_a": a,
        "entity_b": b,
        "answer_space": [
            "A_CLEARLY_HIGHER",
            "A_SLIGHTLY_HIGHER",
            "APPROX_EQUAL",
            "B_SLIGHTLY_HIGHER",
            "B_CLEARLY_HIGHER",
            "CANNOT_JUDGE",
        ],
        "presentation_contract_version": contract.version,
        "disclaimer": "The proposition is provisional; human judgement is evidence, not ground truth.",
    }


__all__ = [
    "PRESENTATION_CONTRACT_VERSION",
    "PROPOSITION_QUESTIONS",
    "PresentationContract",
    "DEFAULT_PRESENTATION",
    "blind_task_payload",
]
