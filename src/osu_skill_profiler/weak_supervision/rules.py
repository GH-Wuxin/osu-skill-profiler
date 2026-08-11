"""A few deliberately conservative demonstration weak-label rules.

Every rule:
- consumes only deterministic map/segment features;
- emits low confidence values (<= 0.35);
- attaches measured evidence so the decision is auditable;
- is a candidate signal, never a label.
"""

from __future__ import annotations

from ..segments.base import Segment
from .base import WeakLabelResult


class ExtremeSpacingMovementRule:
    rule_id = "wsp001_extreme_spacing"
    description = "Very high spacing and movement velocity candidate for jump_aim."

    def apply(self, features: dict, segments: list[Segment]) -> list[WeakLabelResult]:
        distance_p95 = features.get("spatial.distance_norm_p95")
        velocity_p95 = features.get("spatial.velocity_norm_per_s_p95")
        if not isinstance(distance_p95, (int, float)) or not isinstance(velocity_p95, (int, float)):
            return []
        if distance_p95 < 0.35 or velocity_p95 < 6.0:
            return []
        score = min(0.5, (distance_p95 / 0.5) * 0.25 + (velocity_p95 / 12.0) * 0.25)
        return [
            WeakLabelResult(
                skill="jump_aim",
                suggested_score=round(score, 4),
                confidence=0.25,
                rule_id=self.rule_id,
                evidence=(
                    f"distance_norm_p95={distance_p95:.4f}",
                    f"velocity_norm_per_s_p95={velocity_p95:.4f}",
                ),
            )
        ]


class LongDenseSectionRule:
    rule_id = "wsp002_long_dense"
    description = "Long continuous high-density section candidate for stream/stamina."

    def apply(self, features: dict, segments: list[Segment]) -> list[WeakLabelResult]:
        longest = features.get("temporal.longest_dense_section_ms")
        peak_density = features.get("section.density_per_s_max")
        if not isinstance(longest, (int, float)) or not isinstance(peak_density, (int, float)):
            return []
        if longest < 4000.0 or peak_density < 6.0:
            return []
        score = min(0.5, (longest / 10000.0) * 0.3 + (peak_density / 12.0) * 0.2)
        return [
            WeakLabelResult(
                skill="stream",
                suggested_score=round(score, 4),
                confidence=0.25,
                rule_id=self.rule_id,
                evidence=(
                    f"longest_dense_section_ms={longest:.2f}",
                    f"section_density_per_s_max={peak_density:.2f}",
                ),
            )
        ]


class RhythmIrregularityRule:
    rule_id = "wsp003_rhythm_irregularity"
    description = "High rhythm entropy and interval diversity candidate for rhythm_complexity."

    def apply(self, features: dict, segments: list[Segment]) -> list[WeakLabelResult]:
        entropy = features.get("temporal.rhythm_entropy_bits")
        diversity = features.get("temporal.interval_diversity")
        if not isinstance(entropy, (int, float)) or not isinstance(diversity, (int, float)):
            return []
        if entropy < 2.8 or diversity < 0.35:
            return []
        score = min(0.4, (entropy / 4.0) * 0.25 + (diversity / 0.8) * 0.15)
        return [
            WeakLabelResult(
                skill="rhythm_complexity",
                suggested_score=round(score, 4),
                confidence=0.2,
                rule_id=self.rule_id,
                evidence=(
                    f"rhythm_entropy_bits={entropy:.4f}",
                    f"interval_diversity={diversity:.4f}",
                ),
            )
        ]


CONSERVATIVE_RULES: list = [ExtremeSpacingMovementRule(), LongDenseSectionRule(), RhythmIrregularityRule()]

