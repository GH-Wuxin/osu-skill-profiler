"""Weak supervision contracts.

WEAK LABEL != GROUND TRUTH. A weak label is a low-confidence, rule-generated
candidate signal with full provenance. It must never be persisted or consumed
as if it were a human-validated label.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from ..segments.base import Segment

WEAK_LABEL_DISCLAIMER = "WEAK LABEL != GROUND TRUTH"


@dataclass(frozen=True)
class WeakLabelResult:
    skill: str
    suggested_score: Optional[float]
    confidence: float
    rule_id: str
    evidence: tuple[str, ...]
    segment_index: Optional[int] = None


class WeakLabelRule(Protocol):
    rule_id: str
    description: str

    def apply(self, features: dict, segments: list[Segment]) -> list[WeakLabelResult]:
        """Emit conservative candidate labels from deterministic features."""


@dataclass(frozen=True)
class WeakLabelEvidence:
    rule_id: str
    skill: str
    suggested_score: Optional[float]
    confidence: float
    evidence: tuple[str, ...]
    segment_index: Optional[int]
    features_version: str
    taxonomy_version: str
    input_checksum: str
    disclaimer: str = WEAK_LABEL_DISCLAIMER

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "skill": self.skill,
            "suggested_score": self.suggested_score,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "segment_index": self.segment_index,
            "features_version": self.features_version,
            "taxonomy_version": self.taxonomy_version,
            "input_checksum": self.input_checksum,
            "disclaimer": self.disclaimer,
        }

