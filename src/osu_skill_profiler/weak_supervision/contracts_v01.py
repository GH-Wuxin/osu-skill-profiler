"""Versioned weak-evidence contracts.

These records are evidence about provisional propositions.  They are not
labels, calibrated probabilities, or ground truth.  The legacy ``WeakLabel*``
surface remains in :mod:`base` for historical baseline compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping

WEAK_EVIDENCE_SCHEMA_VERSION = "0.1.0"
PROPOSITION_REGISTRY_VERSION = "0.1.0"
SOURCE_REGISTRY_VERSION = "0.1.0"
WEAK_RULE_CONTRACT_VERSION = "0.1.0"
WEAK_EVIDENCE_DISCLAIMER = "WEAK EVIDENCE != LABEL != GROUND TRUTH"


class EntityScope(str, Enum):
    MAP = "MAP"
    SEGMENT = "SEGMENT"
    # Reserved schema values. v0.1 rules do not emit these scopes.
    OBJECT = "OBJECT"
    OBJECT_PAIR = "OBJECT_PAIR"


class PropositionStatus(str, Enum):
    PROVISIONAL = "PROVISIONAL"


class SourceFamily(str, Enum):
    OBSERVABLE = "OBSERVABLE"
    LOCAL_SIGNAL = "LOCAL_SIGNAL"
    REFERENCE_PPY = "REFERENCE_PPY"
    DETERMINISTIC_RELATION = "DETERMINISTIC_RELATION"
    COMMUNITY = "COMMUNITY"
    HUMAN = "HUMAN"
    MODEL_DERIVED = "MODEL_DERIVED"


class EvidenceStatus(str, Enum):
    EMITTED = "EMITTED"
    ABSTAINED = "ABSTAINED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class EvidenceDirection(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    SCALAR = "SCALAR"
    PAIRWISE = "PAIRWISE"


class ConfidenceBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AbstentionReason(str, Enum):
    MISSING_REQUIRED_SIGNAL = "MISSING_REQUIRED_SIGNAL"
    INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"
    GEOMETRY_BLOCKED = "GEOMETRY_BLOCKED"
    OUTSIDE_CALIBRATED_RANGE = "OUTSIDE_CALIBRATED_RANGE"
    AMBIGUOUS_EVIDENCE = "AMBIGUOUS_EVIDENCE"
    CONFLICTING_INPUTS = "CONFLICTING_INPUTS"
    UNSUPPORTED_SEMANTICS = "UNSUPPORTED_SEMANTICS"
    REFERENCE_UNAVAILABLE = "REFERENCE_UNAVAILABLE"


@dataclass(frozen=True)
class EntityRef:
    scope: EntityScope
    map_checksum: str
    segment_index: int | None = None
    segment_start_ms: float | None = None
    segment_end_ms: float | None = None
    pair_entity_key: str | None = None

    def __post_init__(self) -> None:
        if not self.map_checksum.startswith("sha256:") or len(self.map_checksum) != 71:
            raise ValueError("map_checksum must be sha256:<64 lowercase hex>")
        try:
            int(self.map_checksum[7:], 16)
        except ValueError as exc:
            raise ValueError("map_checksum must be sha256:<64 lowercase hex>") from exc
        if self.map_checksum != self.map_checksum.lower():
            raise ValueError("map_checksum must use lowercase hex")
        if self.scope == EntityScope.SEGMENT:
            if self.segment_index is None or self.segment_index < 0:
                raise ValueError("SEGMENT requires a non-negative segment_index")
            if self.segment_start_ms is None or self.segment_end_ms is None:
                raise ValueError("SEGMENT requires start/end bounds")
            if not math.isfinite(self.segment_start_ms) or not math.isfinite(self.segment_end_ms):
                raise ValueError("segment bounds must be finite")
            if self.segment_end_ms < self.segment_start_ms:
                raise ValueError("segment end must not precede start")
        elif any(value is not None for value in (self.segment_index, self.segment_start_ms, self.segment_end_ms)):
            raise ValueError("segment identity fields are valid only for SEGMENT")
        if self.scope == EntityScope.OBJECT_PAIR and not self.pair_entity_key:
            raise ValueError("OBJECT_PAIR requires pair_entity_key")
        if self.scope != EntityScope.OBJECT_PAIR and self.pair_entity_key is not None:
            raise ValueError("pair_entity_key is valid only for OBJECT_PAIR")

    @property
    def stable_key(self) -> str:
        suffix = ""
        if self.scope == EntityScope.SEGMENT:
            suffix = f":segment:{self.segment_index}"
        elif self.scope == EntityScope.OBJECT_PAIR:
            suffix = f":pair:{self.pair_entity_key}"
        return f"{self.scope.value}:{self.map_checksum}{suffix}"

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"scope": self.scope.value, "map_checksum": self.map_checksum}
        if self.scope == EntityScope.SEGMENT:
            payload.update({
                "segment_index": self.segment_index,
                "segment_start_ms": self.segment_start_ms,
                "segment_end_ms": self.segment_end_ms,
            })
        if self.scope == EntityScope.OBJECT_PAIR:
            payload["pair_entity_key"] = self.pair_entity_key
        return payload


@dataclass(frozen=True)
class EvidenceValue:
    direction: EvidenceDirection
    scalar: float | None = None
    pair_preference: str | None = None

    def __post_init__(self) -> None:
        if self.direction == EvidenceDirection.SCALAR:
            if self.scalar is None or not math.isfinite(self.scalar):
                raise ValueError("SCALAR evidence requires a finite scalar")
        elif self.scalar is not None:
            raise ValueError("scalar is valid only for SCALAR evidence")
        if self.direction == EvidenceDirection.PAIRWISE:
            if not self.pair_preference:
                raise ValueError("PAIRWISE evidence requires pair_preference")
        elif self.pair_preference is not None:
            raise ValueError("pair_preference is valid only for PAIRWISE evidence")

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"direction": self.direction.value}
        if self.scalar is not None:
            payload["scalar"] = self.scalar
        if self.pair_preference is not None:
            payload["pair_preference"] = self.pair_preference
        return payload


@dataclass(frozen=True)
class RuleOutcome:
    status: EvidenceStatus
    value: EvidenceValue | None = None
    strength: float | None = None
    confidence_band: ConfidenceBand | None = None
    reason: AbstentionReason | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status == EvidenceStatus.EMITTED:
            if self.value is None or self.strength is None or self.confidence_band is None:
                raise ValueError("EMITTED requires value, strength, and confidence_band")
            if not math.isfinite(self.strength) or not 0.0 <= self.strength <= 1.0:
                raise ValueError("strength must be a finite deterministic value in [0, 1]")
            if self.reason is not None:
                raise ValueError("EMITTED cannot carry an abstention reason")
        else:
            if self.value is not None or self.strength is not None or self.confidence_band is not None:
                raise ValueError("non-emitted outcomes cannot carry evidence values")
            if self.reason is None:
                raise ValueError("non-emitted outcomes require a machine-readable reason")


@dataclass(frozen=True)
class WeakEvidenceRecord:
    entity: EntityRef
    proposition_key: str
    proposition_version: str
    status: EvidenceStatus
    source_id: str
    source_version: str
    source_family: SourceFamily
    rule_id: str
    rule_version: str
    input_dependencies: tuple[str, ...]
    semantic_lineage: tuple[str, ...]
    independence_group: str
    value: EvidenceValue | None = None
    strength: float | None = None
    confidence_band: ConfidenceBand | None = None
    abstention_reason: AbstentionReason | None = None
    diagnostics: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = WEAK_EVIDENCE_SCHEMA_VERSION
    disclaimer: str = WEAK_EVIDENCE_DISCLAIMER

    def __post_init__(self) -> None:
        RuleOutcome(
            status=self.status,
            value=self.value,
            strength=self.strength,
            confidence_band=self.confidence_band,
            reason=self.abstention_reason,
            diagnostics=self.diagnostics,
        )
        if not self.semantic_lineage:
            raise ValueError("semantic_lineage must be explicit and non-empty")
        if not self.input_dependencies:
            raise ValueError("input_dependencies must be explicit and non-empty")
        if not self.independence_group:
            raise ValueError("independence_group is required")

    @property
    def stable_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.entity.stable_key,
            self.proposition_key,
            self.proposition_version,
            self.rule_id,
            self.rule_version,
        )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "entity": self.entity.as_dict(),
            "proposition": {"key": self.proposition_key, "version": self.proposition_version},
            "status": self.status.value,
            "source": {
                "id": self.source_id,
                "version": self.source_version,
                "family": self.source_family.value,
            },
            "rule": {"id": self.rule_id, "version": self.rule_version},
            "input_dependencies": list(self.input_dependencies),
            "semantic_lineage": list(self.semantic_lineage),
            "independence_group": self.independence_group,
            "diagnostics": list(self.diagnostics),
            "provenance": dict(self.provenance),
            "disclaimer": self.disclaimer,
        }
        if self.value is not None:
            payload["value"] = self.value.as_dict()
            payload["strength"] = self.strength
            payload["confidence_band"] = self.confidence_band.value if self.confidence_band else None
        if self.abstention_reason is not None:
            payload["abstention_reason"] = self.abstention_reason.value
        return payload


@dataclass(frozen=True)
class RuleContext:
    entity: EntityRef
    values: Mapping[str, Any]
    provenance: Mapping[str, Any] = field(default_factory=dict)
