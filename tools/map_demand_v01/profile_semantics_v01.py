"""Versioned profile-output semantics for post-beta.6 experiments.

This module deliberately does not alter any historical Map Demand release.  It
provides a small, strict boundary between an axis calculator and the public
profile shape:

* missing evidence is distinct from observed zero demand;
* axis status, value, and score cannot contradict one another;
* summaries combine only quantities with the same unit semantics; and
* archetype completeness is measured over the seven competing star axes only.

The helpers are dependency-free so a future release can opt in without
changing replay behaviour for an existing release.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping


SCHEMA_VERSION = "profile_semantics_v0.2.0"
ARCHETYPE_SCHEMA_VERSION = "profile_archetype_v0.2.0"

MEASURE_OK = "OK"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
AXIS_EMITTED = "EMITTED"
NOT_PUBLISHED_MIXED_UNITS = "NOT_PUBLISHED_MIXED_UNITS"

STAR_AXES = (
    "jump_aim",
    "flow_aim",
    "aim_control",
    "spatial_precision",
    "raw_speed",
    "finger_control",
    "reading",
)
BOUNDED_AUXILIARY_AXES = ("stamina", "endurance")
ALL_PROFILE_AXES = (
    "jump_aim",
    "flow_aim",
    "aim_control",
    "spatial_precision",
    "raw_speed",
    "stamina",
    "endurance",
    "finger_control",
    "reading",
)

AIM_STAR_AXES = ("jump_aim", "flow_aim", "aim_control", "spatial_precision")
TAPPING_STAR_AXES = ("raw_speed", "finger_control")

MIN_CLASSIFIED_STAR_AXES = 6
BALANCED_SPREAD_MAX = 0.14
MIN_TOP_SCORE = 0.50
MIN_PROMINENCE = 0.07
CO_DOMINANT_GAP_MAX = 0.08
MAX_DOMINANT_AXES = 3

DESCRIPTOR_SEMANTICS = (
    "PEAK_LOCAL_DEMAND_AXIS_DESCRIPTOR_NOT_PREDOMINANT_MAP_STYLE"
)
CONFIDENCE_POLICY = (
    "MIN_OF_STRUCTURAL_AND_PARTICIPATING_AXIS_CONFIDENCE_V01"
)
SCORE_SEMANTICS = "VALUE_DIV_10_DISPLAY_RATIO_NOT_PROBABILITY"
STAR_SUMMARY_INTERPRETATION = (
    "DESCRIPTIVE_MEAN_OF_INDEPENDENT_LOCAL_PEAK_AXIS_SCALES_"
    "NOT_OSU_STAR_RATING_OR_OVERALL_DIFFICULTY"
)
BOUNDED_SUMMARY_INTERPRETATION = (
    "DESCRIPTIVE_MEAN_OF_BOUNDED_0_10_SUSTAIN_TRAITS"
)
_CONFIDENCE_RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
_CONFIDENCE_UNCERTAINTY_FLOOR = {
    "NONE": 1.0,
    "LOW": 0.5,
    "MEDIUM": 0.25,
    "HIGH": 0.0,
}

_AXIS_TYPES = {axis: f"{axis.upper()}_DOMINANT" for axis in STAR_AXES}
_PAIR_TYPES = {
    frozenset({"jump_aim", "spatial_precision"}): "JUMP_PRECISION",
    frozenset({"raw_speed", "finger_control"}): "SPEED_FINGER_CONTROL",
    frozenset({"finger_control", "reading"}): "FINGER_CONTROL_READING",
    frozenset({"aim_control", "reading"}): "AIM_CONTROL_READING",
}


def _finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite non-negative number") from exc
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return number


def _scan_finite(value: Any, label: str) -> None:
    """Reject non-finite evidence without restricting descriptive metadata."""

    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite evidence at {label}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _scan_finite(item, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_finite(item, f"{label}[{index}]")


@dataclass(frozen=True)
class EvidenceEnvelope:
    """Availability and provenance accompanying one atomic axis measure.

    ``observed_zero`` is intentionally explicit.  An eligible observation that
    genuinely measures zero is publishable; a missing field or zero eligible
    observations is not.
    """

    eligible_count: int
    signals: Mapping[str, Any] = field(default_factory=dict)
    missing_required_fields: tuple[str, ...] = ()
    observed_zero: bool = False
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "eligible_count": self.eligible_count,
            "signals": dict(self.signals),
            "missing_required_fields": list(self.missing_required_fields),
            "observed_zero": self.observed_zero,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AxisMeasure:
    """A calculator result before it is applied to an axis output object."""

    status: str
    value: float | None
    evidence: EvidenceEnvelope

    @classmethod
    def observed(
        cls,
        value: float,
        *,
        eligible_count: int,
        signals: Mapping[str, Any] | None = None,
    ) -> "AxisMeasure":
        number = _finite_nonnegative(value, "AxisMeasure.value")
        return cls(
            status=MEASURE_OK,
            value=number,
            evidence=EvidenceEnvelope(
                eligible_count=eligible_count,
                signals={} if signals is None else signals,
                observed_zero=number == 0.0,
            ),
        )

    @classmethod
    def insufficient(
        cls,
        *,
        reason: str,
        eligible_count: int = 0,
        missing_required_fields: tuple[str, ...] = (),
        signals: Mapping[str, Any] | None = None,
    ) -> "AxisMeasure":
        return cls(
            status=INSUFFICIENT_EVIDENCE,
            value=None,
            evidence=EvidenceEnvelope(
                eligible_count=eligible_count,
                signals={} if signals is None else signals,
                missing_required_fields=missing_required_fields,
                observed_zero=False,
                reason=reason,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "value": self.value,
            "evidence": self.evidence.as_dict(),
        }


def validate_evidence_envelope(envelope: EvidenceEnvelope) -> EvidenceEnvelope:
    if not isinstance(envelope, EvidenceEnvelope):
        raise TypeError("evidence must be an EvidenceEnvelope")
    if isinstance(envelope.eligible_count, bool) or not isinstance(
        envelope.eligible_count, int
    ):
        raise ValueError("eligible_count must be an integer")
    if envelope.eligible_count < 0:
        raise ValueError("eligible_count must be non-negative")
    if not isinstance(envelope.observed_zero, bool):
        raise ValueError("observed_zero must be boolean")
    missing = envelope.missing_required_fields
    if not isinstance(missing, tuple) or any(
        not isinstance(field_name, str) or not field_name for field_name in missing
    ):
        raise ValueError("missing_required_fields must be non-empty strings in a tuple")
    if len(set(missing)) != len(missing):
        raise ValueError("missing_required_fields must not contain duplicates")
    if envelope.reason is not None and (
        not isinstance(envelope.reason, str) or not envelope.reason
    ):
        raise ValueError("reason must be None or a non-empty string")
    if not isinstance(envelope.signals, Mapping):
        raise ValueError("signals must be a mapping")
    _scan_finite(envelope.signals, "evidence.signals")
    return envelope


def validate_axis_measure(measure: AxisMeasure) -> AxisMeasure:
    if not isinstance(measure, AxisMeasure):
        raise TypeError("measure must be an AxisMeasure")
    evidence = validate_evidence_envelope(measure.evidence)
    if measure.status == MEASURE_OK:
        value = _finite_nonnegative(measure.value, "AxisMeasure.value")
        if evidence.eligible_count <= 0:
            raise ValueError("an OK measure requires at least one eligible observation")
        if evidence.missing_required_fields:
            raise ValueError("an OK measure cannot have missing required fields")
        if evidence.reason is not None:
            raise ValueError("an OK measure cannot have an insufficiency reason")
        if evidence.observed_zero != (value == 0.0):
            raise ValueError("observed_zero must exactly match whether value is zero")
    elif measure.status == INSUFFICIENT_EVIDENCE:
        if measure.value is not None:
            raise ValueError("an insufficient measure must not carry a value")
        if evidence.observed_zero:
            raise ValueError("missing evidence is not an observed zero")
        if evidence.reason is None:
            raise ValueError("an insufficient measure requires a reason")
    else:
        raise ValueError(f"unknown AxisMeasure status: {measure.status!r}")
    return measure


def validate_axis_output(
    axis_output: Mapping[str, Any], *, value_key: str = "demand_star_equivalent"
) -> Mapping[str, Any]:
    if not isinstance(axis_output, Mapping):
        raise TypeError("axis output must be a mapping")
    status = axis_output.get("status")
    value = axis_output.get(value_key)
    score = axis_output.get("score")
    if status == AXIS_EMITTED:
        number = _finite_nonnegative(value, f"axis.{value_key}")
        score_number = _finite_nonnegative(score, "axis.score")
        if not math.isclose(score_number, number / 10.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("an emitted axis score must equal value / 10")
    elif status == INSUFFICIENT_EVIDENCE:
        if value is not None or score is not None:
            raise ValueError("an insufficient axis must have null value and score")
    else:
        raise ValueError(f"unknown axis status: {status!r}")
    return axis_output


def apply_axis_measure(
    axis_output: Mapping[str, Any] | None,
    measure: AxisMeasure,
    *,
    method: str,
    scale_method: str,
    component: str,
    evidence_tag: str,
    confidence: str = "LOW",
    value_key: str = "demand_star_equivalent",
) -> dict[str, Any]:
    """Return a new, internally consistent axis output for ``measure``."""

    validate_axis_measure(measure)
    result = dict(axis_output or {})
    result.update(
        method=method,
        scale_method=scale_method,
        percentile_rank=None,
        score_semantics=SCORE_SEMANTICS,
        evidence=[
            {
                "component": component,
                "measure": measure.as_dict(),
                "evidence_tag": evidence_tag,
            }
        ],
    )
    if measure.status == MEASURE_OK:
        value = float(measure.value)  # validated above
        result.update(
            status=AXIS_EMITTED,
            confidence=confidence,
            score=value / 10.0,
        )
        result[value_key] = value
    else:
        result.update(
            status=INSUFFICIENT_EVIDENCE,
            confidence="NONE",
            score=None,
        )
        result[value_key] = None
    validate_axis_output(result, value_key=value_key)
    return result


def _axis_value(
    axes: Mapping[str, Any], axis: str, *, value_key: str
) -> float | None:
    item = axes.get(axis)
    if not isinstance(item, Mapping) or item.get("status") != AXIS_EMITTED:
        return None
    validate_axis_output(item, value_key=value_key)
    return float(item[value_key])


def _summary(
    axes: Mapping[str, Any],
    source_axes: tuple[str, ...],
    *,
    unit: str,
) -> dict[str, Any]:
    values: list[float] = []
    missing: list[str] = []
    source_confidences: dict[str, str] = {}
    for axis in source_axes:
        value = _axis_value(axes, axis, value_key="demand_star_equivalent")
        if value is None:
            missing.append(axis)
        else:
            values.append(value)
            item = axes[axis]
            assert isinstance(item, Mapping)
            source_confidences[axis] = _emitted_axis_confidence(item)
    value = None if missing else sum(values) / len(values)
    confidence = (
        "NONE"
        if missing
        else min(
            source_confidences.values(),
            key=_CONFIDENCE_RANK.__getitem__,
        )
    )
    interpretation = (
        STAR_SUMMARY_INTERPRETATION
        if unit == "star_equivalent"
        else BOUNDED_SUMMARY_INTERPRETATION
    )
    return {
        "status": INSUFFICIENT_EVIDENCE if missing else AXIS_EMITTED,
        "value": value,
        "score": None if value is None else value / 10.0,
        "unit": unit,
        "source_axes": list(source_axes),
        "missing_axes": missing,
        "confidence": confidence,
        "source_axis_confidences": {
            axis: source_confidences[axis]
            for axis in source_axes
            if axis in source_confidences
        },
        "confidence_policy": "MIN_SOURCE_AXIS_CONFIDENCE_V01",
        "policy": "SAME_UNIT_ARITHMETIC_MEAN_V01",
        "score_semantics": SCORE_SEMANTICS,
        "interpretation": interpretation,
    }


def derive_profile_summaries(axes: Mapping[str, Any]) -> dict[str, Any]:
    """Derive only same-unit summaries; refuse a mixed nine-axis scalar."""

    missing_all = [
        axis
        for axis in ALL_PROFILE_AXES
        if _axis_value(axes, axis, value_key="demand_star_equivalent") is None
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "aim_star_summary": _summary(
            axes, AIM_STAR_AXES, unit="star_equivalent"
        ),
        "tapping_star_summary": _summary(
            axes, TAPPING_STAR_AXES, unit="star_equivalent"
        ),
        "primary_star_summary": _summary(
            axes, STAR_AXES, unit="star_equivalent"
        ),
        "bounded_sustain_summary": _summary(
            axes, BOUNDED_AUXILIARY_AXES, unit="bounded_0_10"
        ),
        "overall_demand": {
            "status": NOT_PUBLISHED_MIXED_UNITS,
            "value": None,
            "score": None,
            "confidence": "NONE",
            "unit": None,
            "source_axes": list(ALL_PROFILE_AXES),
            "missing_axes": missing_all,
            "policy": NOT_PUBLISHED_MIXED_UNITS,
            "score_semantics": SCORE_SEMANTICS,
            "interpretation": (
                "NO_OVERALL_SCALAR_BECAUSE_STAR_EQUIVALENT_PEAK_AXES_AND_"
                "BOUNDED_0_10_TRAITS_HAVE_DIFFERENT_UNITS"
            ),
            "reason": (
                "unbounded star-equivalent axes and bounded 0-10 auxiliary "
                "axes do not share a publishable scalar unit"
            ),
        },
    }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _demand_tier(peak: float) -> str:
    if peak < 0.30:
        return "LOW"
    if peak < 0.50:
        return "MODERATE"
    if peak < 0.70:
        return "HIGH"
    return "EXTREME"


def _emitted_axis_confidence(item: Mapping[str, Any]) -> str:
    """Return a conservative, comparable confidence for one emitted axis."""

    confidence = str(item.get("confidence") or "").upper()
    # Older/ad-hoc callers may omit this metadata.  Such an axis is usable as
    # a numeric competitor, but it cannot justify more than LOW confidence in
    # the resulting ordering.
    return confidence if confidence in {"LOW", "MEDIUM", "HIGH"} else "LOW"


def _lower_confidence(left: str, right: str) -> str:
    return left if _CONFIDENCE_RANK[left] <= _CONFIDENCE_RANK[right] else right


def _auxiliary_traits(axes: Mapping[str, Any]) -> dict[str, Any]:
    traits: dict[str, Any] = {}
    for axis in BOUNDED_AUXILIARY_AXES:
        item = axes.get(axis)
        if not isinstance(item, Mapping) or item.get("status") != AXIS_EMITTED:
            traits[axis] = {"status": INSUFFICIENT_EVIDENCE, "value": None}
            continue
        validate_axis_output(item)
        traits[axis] = {
            "status": AXIS_EMITTED,
            "value": float(item["demand_star_equivalent"]),
            "score": float(item["score"]),
            "unit": "bounded_0_10",
        }
    return traits


def classify_star_archetype(axes: Mapping[str, Any]) -> dict[str, Any]:
    """Describe the strongest local peak among the seven competing star axes.

    This is deliberately not a predominant map-style classifier.  Every
    emitted axis participates in the ordering, so the classification cannot
    be more confident than the least-confident participating axis.
    """

    scores: dict[str, float] = {}
    axis_confidences: dict[str, str] = {}
    missing: list[str] = []
    for axis in STAR_AXES:
        item = axes.get(axis)
        if not isinstance(item, Mapping) or item.get("status") != AXIS_EMITTED:
            missing.append(axis)
            continue
        validate_axis_output(item)
        scores[axis] = float(item["score"])
        axis_confidences[axis] = _emitted_axis_confidence(item)

    completeness = len(scores) / len(STAR_AXES)
    input_confidence_cap = min(
        axis_confidences.values(),
        key=_CONFIDENCE_RANK.__getitem__,
        default="NONE",
    )
    common = {
        "schema_version": ARCHETYPE_SCHEMA_VERSION,
        "policy_id": "SEVEN_STAR_AXIS_DOMINANCE_WITH_BOUNDED_AUXILIARY_V02",
        "competition_axes": list(STAR_AXES),
        "excluded_auxiliary_axes": list(BOUNDED_AUXILIARY_AXES),
        "competition_axis_count": len(STAR_AXES),
        "emitted_competition_axis_count": len(scores),
        "completeness": completeness,
        "axis_scores": {axis: scores[axis] for axis in STAR_AXES if axis in scores},
        "missing_axes": missing,
        "auxiliary_traits": _auxiliary_traits(axes),
        "descriptor_semantics": DESCRIPTOR_SEMANTICS,
        "confidence_policy": CONFIDENCE_POLICY,
        "participating_axis_confidences": {
            axis: axis_confidences[axis]
            for axis in STAR_AXES
            if axis in axis_confidences
        },
        "input_confidence_cap": input_confidence_cap,
    }
    if len(scores) < MIN_CLASSIFIED_STAR_AXES:
        return {
            **common,
            "status": INSUFFICIENT_EVIDENCE,
            "primary_type": None,
            "secondary_types": [],
            "dominant_axes": [],
            "confidence": "NONE",
            "uncertainty_score": 1.0,
            "demand_tier": None,
            "decision_evidence": [
                {
                    "reason": "INSUFFICIENT_COMPETING_STAR_AXES",
                    "minimum_emitted_axis_count": MIN_CLASSIFIED_STAR_AXES,
                }
            ],
        }

    ranked = sorted(scores.items(), key=lambda item: (-item[1], STAR_AXES.index(item[0])))
    top_axis, top_score = ranked[0]
    second_score = ranked[1][1]
    center = _median(list(scores.values()))
    spread = top_score - min(scores.values())
    prominence = top_score - center
    balanced = spread <= BALANCED_SPREAD_MAX or (
        top_score < MIN_TOP_SCORE and prominence < MIN_PROMINENCE
    )
    dominant: list[str] = []
    if not balanced:
        dominant.append(top_axis)
        for axis, score in ranked[1:]:
            if len(dominant) >= MAX_DOMINANT_AXES:
                break
            if (
                top_score - score <= CO_DOMINANT_GAP_MAX
                and score >= MIN_TOP_SCORE
                and score - center >= MIN_PROMINENCE
            ):
                dominant.append(axis)

    if balanced:
        primary = "BALANCED"
        secondary: list[str] = []
        decision_distance = max(0.0, BALANCED_SPREAD_MAX - spread)
    elif len(dominant) == 1:
        primary = _AXIS_TYPES[dominant[0]]
        secondary = []
        decision_distance = max(
            0.0, (top_score - second_score) - CO_DOMINANT_GAP_MAX
        )
    elif len(dominant) == 2:
        primary = _PAIR_TYPES.get(frozenset(dominant), "HYBRID")
        secondary = [_AXIS_TYPES[axis] for axis in dominant]
        decision_distance = max(
            0.0, CO_DOMINANT_GAP_MAX - (top_score - second_score)
        )
    else:
        primary = "HYBRID"
        secondary = [_AXIS_TYPES[axis] for axis in dominant]
        decision_distance = max(
            0.0,
            CO_DOMINANT_GAP_MAX - (top_score - scores[dominant[2]]),
        )

    if (
        completeness == 1.0
        and top_score >= 0.70
        and decision_distance >= 0.05
    ):
        structural_confidence = "HIGH"
    elif (
        completeness < 1.0
        or decision_distance < 0.02
        or top_score < MIN_TOP_SCORE
    ):
        structural_confidence = "LOW"
    else:
        structural_confidence = "MEDIUM"
    confidence = _lower_confidence(
        structural_confidence,
        input_confidence_cap,
    )
    structural_uncertainty = max(
        0.0,
        min(
            1.0,
            1.0
            - min(1.0, decision_distance / 0.12)
            + (1.0 - completeness) * 0.5,
        ),
    )
    uncertainty = max(
        structural_uncertainty,
        _CONFIDENCE_UNCERTAINTY_FLOOR[input_confidence_cap],
    )
    return {
        **common,
        "status": "CLASSIFIED",
        "primary_type": primary,
        "secondary_types": secondary,
        "dominant_axes": dominant,
        "confidence": confidence,
        "uncertainty_score": uncertainty,
        "demand_tier": _demand_tier(top_score),
        "decision_evidence": [
            {
                "top_axis": top_axis,
                "top_score": top_score,
                "second_score": second_score,
                "median_score": center,
                "spread": spread,
                "top_prominence": prominence,
                "decision_distance": decision_distance,
                "structural_confidence": structural_confidence,
                "input_confidence_cap": input_confidence_cap,
            }
        ],
    }


__all__ = [
    "SCHEMA_VERSION",
    "ARCHETYPE_SCHEMA_VERSION",
    "MEASURE_OK",
    "INSUFFICIENT_EVIDENCE",
    "AXIS_EMITTED",
    "NOT_PUBLISHED_MIXED_UNITS",
    "STAR_AXES",
    "BOUNDED_AUXILIARY_AXES",
    "ALL_PROFILE_AXES",
    "AIM_STAR_AXES",
    "TAPPING_STAR_AXES",
    "DESCRIPTOR_SEMANTICS",
    "CONFIDENCE_POLICY",
    "SCORE_SEMANTICS",
    "STAR_SUMMARY_INTERPRETATION",
    "BOUNDED_SUMMARY_INTERPRETATION",
    "EvidenceEnvelope",
    "AxisMeasure",
    "validate_evidence_envelope",
    "validate_axis_measure",
    "validate_axis_output",
    "apply_axis_measure",
    "derive_profile_summaries",
    "classify_star_archetype",
]
