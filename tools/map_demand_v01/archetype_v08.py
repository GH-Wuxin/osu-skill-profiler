"""Nine-axis archetype policy for Map Demand V0.8."""

from __future__ import annotations

import math
from typing import Any

from .archetype_v01 import (
    BALANCED_SPREAD_MAX,
    CO_DOMINANT_GAP_MAX,
    MAX_DOMINANT_AXES,
    MIN_EMITTED_AXES,
    MIN_PROMINENCE,
    MIN_TOP_SCORE,
)

ARCHETYPE_VERSION = "0.5.0"
ARCHETYPE_SCHEMA_VERSION = "map_archetype_v0.5.0"
POLICY_ID = "HEURISTIC_ATOMIC_NINE_AXIS_DOMINANCE_V05"
AXIS_ORDER = (
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
AXIS_TYPES = {axis: f"{axis.upper()}_DOMINANT" for axis in AXIS_ORDER}
PAIR_TYPES = {
    frozenset({"jump_aim", "spatial_precision"}): "JUMP_PRECISION",
    frozenset({"flow_aim", "stamina"}): "FLOW_STAMINA",
    frozenset({"raw_speed", "stamina"}): "SPEED_STAMINA",
    frozenset({"stamina", "endurance"}): "STAMINA_ENDURANCE",
    frozenset({"finger_control", "endurance"}): "FINGER_ENDURANCE",
    frozenset({"reading", "endurance"}): "READING_ENDURANCE",
    frozenset({"raw_speed", "finger_control"}): "SPEED_FINGER_CONTROL",
    frozenset({"finger_control", "reading"}): "FINGER_CONTROL_READING",
    frozenset({"aim_control", "reading"}): "AIM_CONTROL_READING",
    frozenset({"stamina", "reading"}): "STAMINA_READING",
}


def _finite_score(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0.0 else None


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


def unavailable_archetype(reason: str) -> dict[str, Any]:
    return {
        "schema_version": ARCHETYPE_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "status": "UNAVAILABLE",
        "primary_type": None,
        "secondary_types": [],
        "dominant_axes": [],
        "confidence": "NONE",
        "uncertainty_score": 1.0,
        "demand_tier": None,
        "axis_scores": {},
        "missing_axes": list(AXIS_ORDER),
        "decision_evidence": [{"reason": reason}],
    }


def classify_axes(axes: dict[str, Any]) -> dict[str, Any]:
    scores: dict[str, float] = {}
    missing: list[str] = []
    for axis in AXIS_ORDER:
        item = axes.get(axis)
        score = _finite_score(item.get("score")) if isinstance(item, dict) else None
        if not isinstance(item, dict) or item.get("status") != "EMITTED" or score is None:
            missing.append(axis)
        else:
            scores[axis] = score
    if len(scores) < MIN_EMITTED_AXES:
        result = unavailable_archetype("INSUFFICIENT_EMITTED_AXES")
        result.update(
            status="INSUFFICIENT_EVIDENCE",
            axis_scores=scores,
            missing_axes=missing,
        )
        result["decision_evidence"][0]["emitted_axis_count"] = len(scores)
        return result

    ranked = sorted(scores.items(), key=lambda item: (-item[1], AXIS_ORDER.index(item[0])))
    top_axis, top_score = ranked[0]
    second_score = ranked[1][1]
    values = list(scores.values())
    center = _median(values)
    spread = top_score - min(values)
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
        distance = max(0.0, BALANCED_SPREAD_MAX - spread)
    elif len(dominant) == 1:
        primary = AXIS_TYPES[dominant[0]]
        secondary = []
        distance = max(0.0, (top_score - second_score) - CO_DOMINANT_GAP_MAX)
    elif len(dominant) == 2:
        primary = PAIR_TYPES.get(frozenset(dominant), "HYBRID")
        secondary = [AXIS_TYPES[axis] for axis in dominant]
        distance = max(0.0, CO_DOMINANT_GAP_MAX - (top_score - second_score))
    else:
        primary = "HYBRID"
        secondary = [AXIS_TYPES[axis] for axis in dominant]
        distance = max(
            0.0, CO_DOMINANT_GAP_MAX - (top_score - scores[dominant[2]])
        )

    completeness = len(scores) / len(AXIS_ORDER)
    if completeness == 1.0 and top_score >= 0.70 and distance >= 0.05:
        confidence = "HIGH"
    elif completeness < 1.0 or distance < 0.02 or top_score < MIN_TOP_SCORE:
        confidence = "LOW"
    else:
        confidence = "MEDIUM"
    uncertainty = max(
        0.0,
        min(1.0, 1.0 - min(1.0, distance / 0.12) + (1.0 - completeness) * 0.5),
    )
    return {
        "schema_version": ARCHETYPE_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "status": "CLASSIFIED",
        "primary_type": primary,
        "secondary_types": secondary,
        "dominant_axes": dominant,
        "confidence": confidence,
        "uncertainty_score": uncertainty,
        "demand_tier": _demand_tier(top_score),
        "axis_scores": {axis: scores[axis] for axis in AXIS_ORDER if axis in scores},
        "missing_axes": missing,
        "decision_evidence": [
            {
                "top_axis": top_axis,
                "top_score": top_score,
                "second_score": second_score,
                "median_score": center,
                "spread": spread,
                "top_prominence": prominence,
                "decision_distance": distance,
                "evidence_tag": "HEURISTIC_V08_REQUIRES_HUMAN_VALIDATION",
            }
        ],
    }
