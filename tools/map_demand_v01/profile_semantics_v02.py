"""Public axis semantics for support-frontier Map Demand experiments.

The historical profile semantics module publishes a single local-peak value.
That is not enough to distinguish an atomic physical extreme from a mechanic
that is established, sustained, or repeated by the map.  This opt-in module
keeps the historical output aliases replay-compatible while making those
quantities explicit and independent.  Each axis also declares which support
frontiers are eligible for its public value; the selector is data, not a
hidden global blend.

No confidence value is allowed to attenuate a physical or frontier value.
Confidence describes evidence quality only.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Mapping

from . import profile_semantics_v01 as legacy


SCHEMA_VERSION = "profile_semantics_v0.4.0"
ARCHETYPE_SCHEMA_VERSION = "profile_archetype_v0.4.0"
AXIS_CONTRACT_VERSION = "axis_support_frontier_v0.2.0"

PUBLIC_VALUE_SEMANTICS = "AXIS_POLICY_SELECTED_SUPPORT_FRONTIER_STAR"
PHYSICAL_PEAK_SEMANTICS = "MAXIMUM_OBSERVED_ATOMIC_PHYSICAL_DEMAND"
EVIDENCE_CONFIDENCE_SEMANTICS = (
    "EVIDENCE_RELIABILITY_ONLY_NEVER_A_NUMERIC_DEMAND_MULTIPLIER"
)
SCORE_SEMANTICS = legacy.SCORE_SEMANTICS
DESCRIPTOR_SEMANTICS = (
    "PUBLIC_AXIS_DEMAND_DESCRIPTOR_NOT_PREDOMINANT_MAP_STYLE"
)

MEASURE_OK = legacy.MEASURE_OK
INSUFFICIENT_EVIDENCE = legacy.INSUFFICIENT_EVIDENCE
AXIS_EMITTED = legacy.AXIS_EMITTED
NOT_PUBLISHED_MIXED_UNITS = legacy.NOT_PUBLISHED_MIXED_UNITS

STAR_AXES = legacy.STAR_AXES
BOUNDED_AUXILIARY_AXES = legacy.BOUNDED_AUXILIARY_AXES
ALL_PROFILE_AXES = legacy.ALL_PROFILE_AXES
AIM_STAR_AXES = legacy.AIM_STAR_AXES
TAPPING_STAR_AXES = legacy.TAPPING_STAR_AXES

EvidenceEnvelope = legacy.EvidenceEnvelope
AxisMeasure = legacy.AxisMeasure
validate_evidence_envelope = legacy.validate_evidence_envelope
validate_axis_measure = legacy.validate_axis_measure


def _finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{label} must be a finite non-negative number"
        ) from exc
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return number


def _frontier_payload(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a mapping")
    result = copy.deepcopy(dict(raw))
    result["frontier_star"] = _finite_nonnegative(
        result.get("frontier_star"), f"{label}.frontier_star"
    )
    return result


def _physical_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        result = copy.deepcopy(dict(raw))
        candidate = result.get("star", result.get("value"))
    else:
        result = {}
        candidate = raw
    result["star"] = _finite_nonnegative(candidate, "physical_peak.star")
    result.pop("value", None)
    result.setdefault("semantics", PHYSICAL_PEAK_SEMANTICS)
    result.setdefault("unit", "star_equivalent")
    return result


def _public_frontier_payload(raw: Any) -> dict[str, Any]:
    result = _frontier_payload(raw, "public_frontier")
    selected = result.get("selected_component")
    eligible = result.get("eligible_components")
    if selected not in {"establishment", "sustain", "recurrence"}:
        raise ValueError("public_frontier.selected_component is invalid")
    if not isinstance(eligible, list) or selected not in eligible:
        raise ValueError("public_frontier eligible component contract is invalid")
    if result.get("confidence_affects_selection") is not False:
        raise ValueError("confidence must not affect public frontier selection")
    if result.get("physical_peak_is_candidate") is not False:
        raise ValueError("physical peak must not be a public frontier candidate")
    return result


def _confidence_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        result = copy.deepcopy(dict(raw))
        candidate = result.get("value")
    else:
        result = {}
        candidate = raw
    value = _finite_nonnegative(candidate, "evidence_confidence.value")
    if value > 1.0:
        raise ValueError("evidence_confidence.value must be in [0, 1]")
    result["value"] = value
    result.setdefault("semantics", EVIDENCE_CONFIDENCE_SEMANTICS)
    return result


def apply_supported_axis_measure(
    axis_output: Mapping[str, Any] | None,
    raw_measure: Mapping[str, Any],
    *,
    method: str,
    scale_method: str,
    component: str,
    evidence_tag: str,
    confidence: str = "LOW",
) -> dict[str, Any]:
    """Publish one support-aware star axis without conflating its quantities."""

    if not isinstance(raw_measure, Mapping):
        raise TypeError("raw_measure must be a mapping")
    status = str(raw_measure.get("status") or "INSUFFICIENT").upper()
    eligible = raw_measure.get(
        "eligible_count", raw_measure.get("evidence_count", 0)
    )
    if isinstance(eligible, bool) or not isinstance(eligible, int):
        try:
            eligible = int(eligible)
        except (TypeError, ValueError):
            eligible = 0
    eligible = max(0, eligible)

    if status not in {"OK", "FULL", "DEGRADED"}:
        measure = AxisMeasure.insufficient(
            reason=str(
                raw_measure.get("reason") or "INSUFFICIENT_SUPPORT_EVIDENCE"
            ),
            eligible_count=eligible,
            signals=dict(raw_measure),
        )
        result = legacy.apply_axis_measure(
            axis_output,
            measure,
            method=method,
            scale_method=scale_method,
            component=component,
            evidence_tag=evidence_tag,
            confidence=confidence,
        )
        result.update(
            axis_contract_version=AXIS_CONTRACT_VERSION,
            stars=None,
            public_value_semantics=PUBLIC_VALUE_SEMANTICS,
            physical_peak=None,
            evidence_confidence=None,
            establishment=None,
            sustain=None,
            recurrence=None,
            public_frontier=None,
        )
        return result

    establishment = _frontier_payload(
        raw_measure.get("establishment"), "establishment"
    )
    sustain = _frontier_payload(raw_measure.get("sustain"), "sustain")
    recurrence = _frontier_payload(
        raw_measure.get("recurrence"), "recurrence"
    )
    public_frontier = _public_frontier_payload(
        raw_measure.get("public_frontier")
    )
    physical_peak = _physical_payload(
        raw_measure.get(
            "physical_peak_details", raw_measure.get("physical_peak")
        )
    )
    evidence_confidence = _confidence_payload(
        raw_measure.get(
            "evidence_confidence_details",
            raw_measure.get("evidence_confidence"),
        )
    )
    public_value = public_frontier["frontier_star"]
    measure = AxisMeasure.observed(
        public_value,
        eligible_count=eligible,
        signals=dict(raw_measure),
    )
    result = legacy.apply_axis_measure(
        axis_output,
        measure,
        method=method,
        scale_method=scale_method,
        component=component,
        evidence_tag=evidence_tag,
        confidence=confidence,
    )
    result.update(
        axis_contract_version=AXIS_CONTRACT_VERSION,
        stars=public_value,
        public_value_semantics=PUBLIC_VALUE_SEMANTICS,
        physical_peak=physical_peak,
        evidence_confidence=evidence_confidence,
        establishment=establishment,
        sustain=sustain,
        recurrence=recurrence,
        public_frontier=public_frontier,
        legacy_aliases={
            "demand_star_equivalent": "stars",
            "score": "stars / 10",
        },
    )
    validate_supported_axis_output(result)
    return result


def annotate_legacy_axis(
    axis_output: Mapping[str, Any], *, source_contract: str
) -> dict[str, Any]:
    """Mark an inherited axis honestly; do not invent support frontiers for it."""

    result = copy.deepcopy(dict(axis_output))
    result["axis_contract_version"] = source_contract
    result["public_value_semantics"] = "INHERITED_LOCAL_AXIS_VALUE"
    value = result.get("demand_star_equivalent")
    result["stars"] = value
    result["support_frontiers_available"] = False
    return result


def validate_supported_axis_output(axis_output: Mapping[str, Any]) -> Mapping[str, Any]:
    legacy.validate_axis_output(axis_output)
    if axis_output.get("axis_contract_version") != AXIS_CONTRACT_VERSION:
        raise ValueError("support-aware axis contract version mismatch")
    if axis_output.get("status") == AXIS_EMITTED:
        stars = _finite_nonnegative(axis_output.get("stars"), "axis.stars")
        alias = _finite_nonnegative(
            axis_output.get("demand_star_equivalent"),
            "axis.demand_star_equivalent",
        )
        frontier = _finite_nonnegative(
            axis_output.get("public_frontier", {}).get("frontier_star"),
            "axis.public_frontier.frontier_star",
        )
        if stars != alias or stars != frontier:
            raise ValueError(
                "stars, demand_star_equivalent, and selected public frontier "
                "must be identical"
            )
        public_payload = _public_frontier_payload(
            axis_output.get("public_frontier")
        )
        selected_component = public_payload["selected_component"]
        selected_payload = axis_output.get(selected_component)
        selected_star = _finite_nonnegative(
            selected_payload.get("frontier_star")
            if isinstance(selected_payload, Mapping)
            else None,
            f"axis.{selected_component}.frontier_star",
        )
        if selected_star != stars:
            raise ValueError(
                "selected public frontier must equal its named component"
            )
        physical_payload = _physical_payload(axis_output.get("physical_peak"))
        if stars > physical_payload["star"] + 1e-12:
            raise ValueError("public frontier cannot exceed physical peak")
        _confidence_payload(axis_output.get("evidence_confidence"))
        _frontier_payload(axis_output.get("sustain"), "sustain")
        _frontier_payload(axis_output.get("recurrence"), "recurrence")
    return axis_output


def derive_profile_summaries(axes: Mapping[str, Any]) -> dict[str, Any]:
    result = legacy.derive_profile_summaries(axes)
    result["schema_version"] = SCHEMA_VERSION
    result["public_value_semantics"] = (
        "USES_EACH_AXIS_PUBLIC_VALUE; SUPPORT_AWARE_AXES_DECLARE_SELECTION_POLICY"
    )
    return result


def classify_star_archetype(axes: Mapping[str, Any]) -> dict[str, Any]:
    result = legacy.classify_star_archetype(axes)
    result["schema_version"] = ARCHETYPE_SCHEMA_VERSION
    result["policy_id"] = "SEVEN_STAR_PUBLIC_AXIS_DOMINANCE_V03"
    result["descriptor_semantics"] = DESCRIPTOR_SEMANTICS
    result["support_aware_axes"] = [
        axis
        for axis in STAR_AXES
        if isinstance(axes.get(axis), Mapping)
        and axes[axis].get("axis_contract_version") == AXIS_CONTRACT_VERSION
    ]
    return result


__all__ = [
    "SCHEMA_VERSION",
    "ARCHETYPE_SCHEMA_VERSION",
    "AXIS_CONTRACT_VERSION",
    "PUBLIC_VALUE_SEMANTICS",
    "PHYSICAL_PEAK_SEMANTICS",
    "EVIDENCE_CONFIDENCE_SEMANTICS",
    "SCORE_SEMANTICS",
    "DESCRIPTOR_SEMANTICS",
    "MEASURE_OK",
    "INSUFFICIENT_EVIDENCE",
    "AXIS_EMITTED",
    "NOT_PUBLISHED_MIXED_UNITS",
    "STAR_AXES",
    "BOUNDED_AUXILIARY_AXES",
    "ALL_PROFILE_AXES",
    "AIM_STAR_AXES",
    "TAPPING_STAR_AXES",
    "EvidenceEnvelope",
    "AxisMeasure",
    "validate_evidence_envelope",
    "validate_axis_measure",
    "validate_supported_axis_output",
    "apply_supported_axis_measure",
    "annotate_legacy_axis",
    "derive_profile_summaries",
    "classify_star_archetype",
]
