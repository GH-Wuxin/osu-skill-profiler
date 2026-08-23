"""Active Learning and Human Annotation contracts v0.1.

The contracts deliberately represent tasks, raw human responses and HUMAN
evidence. They do not define a final taxonomy, ground truth or model labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from osu_skill_profiler.weak_supervision.contracts_v01 import EntityRef, EntityScope


ANNOTATION_SCHEMA_VERSION = "0.1.0"
ANNOTATION_TASK_VERSION = "0.1.0"
ANNOTATION_RESPONSE_VERSION = "0.1.0"
HUMAN_EVIDENCE_VERSION = "0.1.0"
HUMAN_EVIDENCE_DISCLAIMER = "HUMAN EVIDENCE != LABEL != GROUND TRUTH"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")


class TaskScope(str, Enum):
    MAP_PAIR = "MAP_PAIR"
    SEGMENT_PAIR = "SEGMENT_PAIR"


class PairwiseAnswer(str, Enum):
    A_CLEARLY_HIGHER = "A_CLEARLY_HIGHER"
    A_SLIGHTLY_HIGHER = "A_SLIGHTLY_HIGHER"
    APPROX_EQUAL = "APPROX_EQUAL"
    B_SLIGHTLY_HIGHER = "B_SLIGHTLY_HIGHER"
    B_CLEARLY_HIGHER = "B_CLEARLY_HIGHER"
    CANNOT_JUDGE = "CANNOT_JUDGE"


class PresentationOrder(str, Enum):
    AB = "AB"
    BA = "BA"


class ControlType(str, Enum):
    NONE = "NONE"
    EXACT_REPEAT = "EXACT_REPEAT"
    AB_INVERSION = "AB_INVERSION"
    EASY_ANCHOR = "EASY_ANCHOR"
    AMBIGUOUS_CONTROL = "AMBIGUOUS_CONTROL"
    WITHIN_MAP_SEGMENT = "WITHIN_MAP_SEGMENT"


class SelectionReason(str, Enum):
    INFORMATIVE_UNCERTAIN = "INFORMATIVE_UNCERTAIN"
    ABSTENTION_HEAVY = "ABSTENTION_HEAVY"
    BOUNDARY_ADJACENT = "BOUNDARY_ADJACENT"
    CHALLENGE_AUDIT = "CHALLENGE_AUDIT"
    EASY_ANCHOR = "EASY_ANCHOR"
    AMBIGUOUS_CONTROL = "AMBIGUOUS_CONTROL"
    WITHIN_MAP_SEGMENT = "WITHIN_MAP_SEGMENT"
    EXACT_REPEAT = "EXACT_REPEAT"
    AB_INVERSION = "AB_INVERSION"


class ConfidenceBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class HumanEvidenceStatus(str, Enum):
    OBSERVED = "OBSERVED"
    ABSTAINED = "ABSTAINED"
    INVALID = "INVALID"


ANSWER_RANK = {
    PairwiseAnswer.B_CLEARLY_HIGHER: -2,
    PairwiseAnswer.B_SLIGHTLY_HIGHER: -1,
    PairwiseAnswer.APPROX_EQUAL: 0,
    PairwiseAnswer.A_SLIGHTLY_HIGHER: 1,
    PairwiseAnswer.A_CLEARLY_HIGHER: 2,
}


def _validate_id(value: str, name: str) -> None:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{name} must be a stable opaque identifier")


def _strict(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite number at {path}")
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        if len(normalized) >= 3 and normalized[1:3] == ":/":
            raise ValueError(f"absolute Windows path at {path}")
        if normalized.startswith("/"):
            raise ValueError(f"absolute POSIX path at {path}")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _strict(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _strict(item, f"{path}[{index}]")


def canonical_json(value: Any) -> str:
    _strict(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def stable_id(prefix: str, value: Any, length: int = 24) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}{digest[:length]}"


def entity_scope(entity: EntityRef) -> TaskScope:
    if entity.scope == EntityScope.MAP:
        return TaskScope.MAP_PAIR
    if entity.scope == EntityScope.SEGMENT:
        return TaskScope.SEGMENT_PAIR
    raise ValueError("Active Learning v0.1 supports MAP and SEGMENT pairs only")


@dataclass(frozen=True)
class ScoreComponents:
    uncertainty: float
    independent_disagreement: float
    abstention_pressure: float
    boundary_proximity: float
    low_effective_support: float
    novelty_underrepresentation: float
    challenge_audit_bonus: float
    pair_proximity: float

    def __post_init__(self) -> None:
        for name, value in self.as_dict().items():
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"score component {name} must be in [0, 1]")

    def as_dict(self) -> dict[str, float]:
        return {
            "uncertainty": self.uncertainty,
            "independent_disagreement": self.independent_disagreement,
            "abstention_pressure": self.abstention_pressure,
            "boundary_proximity": self.boundary_proximity,
            "low_effective_support": self.low_effective_support,
            "novelty_underrepresentation": self.novelty_underrepresentation,
            "challenge_audit_bonus": self.challenge_audit_bonus,
            "pair_proximity": self.pair_proximity,
        }


@dataclass(frozen=True)
class AnnotationEntity:
    ref: EntityRef
    anonymous_display_id: str
    set_group_key: str
    mapper_group_key: str
    neutral_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_id(self.anonymous_display_id, "anonymous_display_id")
        if not self.set_group_key or not self.mapper_group_key:
            raise ValueError("sampling group identities are required")
        _strict(dict(self.neutral_metadata))

    @property
    def stable_key(self) -> str:
        return self.ref.stable_key

    def as_dict(self, *, internal: bool = True) -> dict[str, Any]:
        payload = {
            "entity": self.ref.as_dict(),
            "anonymous_display_id": self.anonymous_display_id,
            "neutral_metadata": dict(self.neutral_metadata),
        }
        if internal:
            payload["sampling_groups"] = {
                "set_group_key": self.set_group_key,
                "mapper_group_key": self.mapper_group_key,
            }
        return payload


@dataclass(frozen=True)
class AnnotationTask:
    task_id: str
    batch_id: str
    proposition_key: str
    proposition_version: str
    scope: TaskScope
    entity_a: AnnotationEntity
    entity_b: AnnotationEntity
    selection_reason: SelectionReason
    selection_score_components: ScoreComponents
    acquisition_score: float
    weak_evidence_snapshot: Mapping[str, Any]
    provenance: Mapping[str, Any]
    control_type: ControlType = ControlType.NONE
    control_group_id: str | None = None
    source_task_id: str | None = None
    presentation_order: PresentationOrder = PresentationOrder.AB
    presentation_contract_version: str = "0.1.0"
    diagnostic_expected_canonical_sign: int | None = None
    schema_version: str = ANNOTATION_SCHEMA_VERSION
    task_version: str = ANNOTATION_TASK_VERSION

    def __post_init__(self) -> None:
        for name, value in (
            ("task_id", self.task_id),
            ("batch_id", self.batch_id),
            ("proposition_key", self.proposition_key),
        ):
            _validate_id(value, name)
        _validate_id(self.proposition_version, "proposition_version")
        if self.schema_version != ANNOTATION_SCHEMA_VERSION or self.task_version != ANNOTATION_TASK_VERSION:
            raise ValueError("unsupported annotation task schema/version")
        if self.scope != entity_scope(self.entity_a.ref) or self.scope != entity_scope(self.entity_b.ref):
            raise ValueError("pair entities must match the declared task scope")
        if self.entity_a.stable_key == self.entity_b.stable_key:
            raise ValueError("pair entities must be distinct")
        if not math.isfinite(self.acquisition_score) or not 0.0 <= self.acquisition_score <= 1.0:
            raise ValueError("acquisition_score must be in [0, 1]")
        if self.control_type in (ControlType.EXACT_REPEAT, ControlType.AB_INVERSION):
            if not self.source_task_id or not self.control_group_id:
                raise ValueError("repeat/inversion controls require source_task_id and control_group_id")
        if self.source_task_id is not None:
            _validate_id(self.source_task_id, "source_task_id")
        if self.control_group_id is not None:
            _validate_id(self.control_group_id, "control_group_id")
        if self.diagnostic_expected_canonical_sign not in (None, -1, 0, 1):
            raise ValueError("diagnostic expected sign must be -1, 0, 1 or None")
        if self.presentation_contract_version not in ("0.1.0", "0.2.0"):
            raise ValueError("unsupported presentation contract version")
        _strict(dict(self.weak_evidence_snapshot))
        _strict(dict(self.provenance))

    @property
    def unordered_pair_key(self) -> tuple[str, str, str]:
        a, b = sorted((self.entity_a.stable_key, self.entity_b.stable_key))
        return self.proposition_key, a, b

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_version": self.task_version,
            "batch_id": self.batch_id,
            "proposition": {"key": self.proposition_key, "version": self.proposition_version},
            "scope": self.scope.value,
            "entity_a": self.entity_a.as_dict(),
            "entity_b": self.entity_b.as_dict(),
            "selection_reason": self.selection_reason.value,
            "selection_score_components": self.selection_score_components.as_dict(),
            "acquisition_score": self.acquisition_score,
            "weak_evidence_snapshot": dict(self.weak_evidence_snapshot),
            "provenance": dict(self.provenance),
            "control_type": self.control_type.value,
            "control_group_id": self.control_group_id,
            "source_task_id": self.source_task_id,
            "presentation_order": self.presentation_order.value,
            "presentation_contract_version": self.presentation_contract_version,
            "diagnostic_expected_canonical_sign": self.diagnostic_expected_canonical_sign,
        }

    def as_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, **self.identity_payload()}


def build_task(**kwargs: Any) -> AnnotationTask:
    provisional = AnnotationTask(task_id="task-pending", **kwargs)
    identity = provisional.identity_payload()
    return AnnotationTask(task_id=stable_id("task-", identity), **kwargs)


@dataclass(frozen=True)
class AnnotationResponse:
    response_id: str
    task_id: str
    task_version: str
    batch_id: str
    annotator_id: str
    session_id: str
    answer: PairwiseAnswer
    presentation_order: PresentationOrder
    response_time_ms: int | None = None
    confidence_band: ConfidenceBand | None = None
    reason_codes: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = ANNOTATION_SCHEMA_VERSION
    response_version: str = ANNOTATION_RESPONSE_VERSION

    def __post_init__(self) -> None:
        for name, value in (
            ("response_id", self.response_id),
            ("task_id", self.task_id),
            ("batch_id", self.batch_id),
            ("annotator_id", self.annotator_id),
            ("session_id", self.session_id),
        ):
            _validate_id(value, name)
        _validate_id(self.task_version, "task_version")
        if self.schema_version != ANNOTATION_SCHEMA_VERSION or self.response_version != ANNOTATION_RESPONSE_VERSION:
            raise ValueError("unsupported annotation response schema/version")
        if self.response_time_ms is not None and self.response_time_ms < 0:
            raise ValueError("response_time_ms must be non-negative")
        for reason in self.reason_codes:
            _validate_id(reason, "reason_code")
        _strict(dict(self.provenance))

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "response_version": self.response_version,
            "response_id": self.response_id,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "batch_id": self.batch_id,
            "annotator_id": self.annotator_id,
            "session_id": self.session_id,
            "answer": self.answer.value,
            "presentation_order": self.presentation_order.value,
            "reason_codes": list(self.reason_codes),
            "provenance": dict(self.provenance),
        }
        if self.response_time_ms is not None:
            payload["response_time_ms"] = self.response_time_ms
        if self.confidence_band is not None:
            payload["confidence_band"] = self.confidence_band.value
        return payload


@dataclass(frozen=True)
class HumanEvidenceRecord:
    evidence_id: str
    task_id: str
    proposition_key: str
    proposition_version: str
    entity_a_key: str
    entity_b_key: str
    annotator_id: str
    response_id: str
    status: HumanEvidenceStatus
    raw_answer: PairwiseAnswer
    canonical_ordinal: int | None
    provenance: Mapping[str, Any]
    evidence_family: str = "HUMAN"
    schema_version: str = HUMAN_EVIDENCE_VERSION
    disclaimer: str = HUMAN_EVIDENCE_DISCLAIMER

    def __post_init__(self) -> None:
        for name, value in (
            ("evidence_id", self.evidence_id),
            ("task_id", self.task_id),
            ("proposition_key", self.proposition_key),
            ("proposition_version", self.proposition_version),
            ("annotator_id", self.annotator_id),
            ("response_id", self.response_id),
        ):
            _validate_id(value, name)
        if self.evidence_family != "HUMAN" or self.disclaimer != HUMAN_EVIDENCE_DISCLAIMER:
            raise ValueError("HUMAN evidence family/disclaimer is immutable")
        if self.status == HumanEvidenceStatus.ABSTAINED and self.canonical_ordinal is not None:
            raise ValueError("abstained HUMAN evidence cannot carry an ordinal")
        if self.status == HumanEvidenceStatus.OBSERVED and self.canonical_ordinal not in (-2, -1, 0, 1, 2):
            raise ValueError("observed HUMAN evidence requires a supported ordinal")
        _strict(dict(self.provenance))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "evidence_family": self.evidence_family,
            "task_id": self.task_id,
            "proposition": {"key": self.proposition_key, "version": self.proposition_version},
            "entity_a_key": self.entity_a_key,
            "entity_b_key": self.entity_b_key,
            "annotator_id": self.annotator_id,
            "response_id": self.response_id,
            "status": self.status.value,
            "raw_answer": self.raw_answer.value,
            "canonical_ordinal": self.canonical_ordinal,
            "provenance": dict(self.provenance),
            "disclaimer": self.disclaimer,
        }


def invert_answer(answer: PairwiseAnswer) -> PairwiseAnswer:
    mapping = {
        PairwiseAnswer.A_CLEARLY_HIGHER: PairwiseAnswer.B_CLEARLY_HIGHER,
        PairwiseAnswer.A_SLIGHTLY_HIGHER: PairwiseAnswer.B_SLIGHTLY_HIGHER,
        PairwiseAnswer.APPROX_EQUAL: PairwiseAnswer.APPROX_EQUAL,
        PairwiseAnswer.B_SLIGHTLY_HIGHER: PairwiseAnswer.A_SLIGHTLY_HIGHER,
        PairwiseAnswer.B_CLEARLY_HIGHER: PairwiseAnswer.A_CLEARLY_HIGHER,
        PairwiseAnswer.CANNOT_JUDGE: PairwiseAnswer.CANNOT_JUDGE,
    }
    return mapping[answer]


def canonical_answer(task: AnnotationTask, response: AnnotationResponse) -> PairwiseAnswer:
    if response.task_id != task.task_id or response.task_version != task.task_version:
        raise ValueError("response task identity/version mismatch")
    if response.batch_id != task.batch_id:
        raise ValueError("response batch mismatch")
    if response.presentation_order != task.presentation_order:
        raise ValueError("response presentation order mismatch")
    answer = response.answer
    if task.presentation_order == PresentationOrder.BA:
        answer = invert_answer(answer)
    if task.entity_a.stable_key > task.entity_b.stable_key:
        answer = invert_answer(answer)
    return answer


def response_to_human_evidence(task: AnnotationTask, response: AnnotationResponse) -> HumanEvidenceRecord:
    normalized = canonical_answer(task, response)
    ordinal = ANSWER_RANK.get(normalized)
    status = (
        HumanEvidenceStatus.ABSTAINED
        if normalized == PairwiseAnswer.CANNOT_JUDGE
        else HumanEvidenceStatus.OBSERVED
    )
    identity = {
        "task_id": task.task_id,
        "response_id": response.response_id,
        "annotator_id": response.annotator_id,
    }
    return HumanEvidenceRecord(
        evidence_id=stable_id("human-", identity),
        task_id=task.task_id,
        proposition_key=task.proposition_key,
        proposition_version=task.proposition_version,
        entity_a_key=min(task.entity_a.stable_key, task.entity_b.stable_key),
        entity_b_key=max(task.entity_a.stable_key, task.entity_b.stable_key),
        annotator_id=response.annotator_id,
        response_id=response.response_id,
        status=status,
        raw_answer=response.answer,
        canonical_ordinal=ordinal,
        provenance={
            "batch_id": response.batch_id,
            "session_id": response.session_id,
            "presentation_order": response.presentation_order.value,
            "reason_codes": list(response.reason_codes),
            "confidence_band": response.confidence_band.value if response.confidence_band else None,
            "raw_response": response.as_dict(),
        },
    )


class ResponseLedger:
    """Fail-closed response validation while preserving accepted raw rows."""

    def __init__(self, tasks: Iterable[AnnotationTask], annotator_ids: Iterable[str]) -> None:
        task_rows = list(tasks)
        self.tasks = {task.task_id: task for task in task_rows}
        if len(self.tasks) != len(task_rows):
            raise ValueError("duplicate annotation task identity")
        self.annotator_ids = frozenset(annotator_ids)
        for annotator_id in self.annotator_ids:
            _validate_id(annotator_id, "annotator_id")
        self._response_ids: set[str] = set()
        self._judgements: set[tuple[str, str, str]] = set()
        self.responses: list[AnnotationResponse] = []
        self.evidence: list[HumanEvidenceRecord] = []

    def add(self, response: AnnotationResponse) -> HumanEvidenceRecord:
        task = self.tasks.get(response.task_id)
        if task is None:
            raise ValueError("unknown annotation task")
        if response.annotator_id not in self.annotator_ids:
            raise ValueError("unknown annotator")
        if response.response_id in self._response_ids:
            raise ValueError("duplicate response_id")
        judgement = (response.annotator_id, response.task_id, response.task_version)
        if judgement in self._judgements:
            raise ValueError("duplicate annotator response for task/version")
        evidence = response_to_human_evidence(task, response)
        self._response_ids.add(response.response_id)
        self._judgements.add(judgement)
        self.responses.append(response)
        self.evidence.append(evidence)
        return evidence


__all__ = [
    "ANNOTATION_SCHEMA_VERSION",
    "ANNOTATION_TASK_VERSION",
    "ANNOTATION_RESPONSE_VERSION",
    "HUMAN_EVIDENCE_VERSION",
    "HUMAN_EVIDENCE_DISCLAIMER",
    "ANSWER_RANK",
    "TaskScope",
    "PairwiseAnswer",
    "PresentationOrder",
    "ControlType",
    "SelectionReason",
    "ConfidenceBand",
    "HumanEvidenceStatus",
    "ScoreComponents",
    "AnnotationEntity",
    "AnnotationTask",
    "AnnotationResponse",
    "HumanEvidenceRecord",
    "ResponseLedger",
    "build_task",
    "canonical_answer",
    "canonical_json",
    "entity_scope",
    "invert_answer",
    "response_to_human_evidence",
    "stable_id",
]
