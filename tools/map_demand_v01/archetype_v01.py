"""Deterministic multi-label atomic map-demand archetypes.

This policy converts eight continuous atomic Map Demand axes into a reviewable type
proposal.  It is a heuristic decision contract, not human ground truth.
Overall demand and relative shape are deliberately reported separately.
"""

from __future__ import annotations

import math
from typing import Any

ARCHETYPE_VERSION = "0.4.0"
ARCHETYPE_SCHEMA_VERSION = "map_archetype_v0.4.0"
POLICY_ID = "HEURISTIC_ATOMIC_STAR_SCALED_DOMINANCE_V04"

AXIS_SCHEMA_VERSION = "atomic_v0.6.0"
PREVIOUS_ATOMIC_AXIS_SCHEMA_VERSION = "atomic_v0.5.0"
OLDER_ATOMIC_AXIS_SCHEMA_VERSION = "atomic_v0.4.0"
PREVIOUS_ATOMIC_AXIS_ORDER = (
    "jump_aim", "flow_aim", "aim_control", "spatial_precision", "raw_speed",
    "stamina", "finger_control", "timing_precision", "reading",
)
LEGACY_AXIS_SCHEMA_VERSION = "broad_v0.3.0"
LEGACY_AXIS_ORDER = ("aim", "precision", "speed", "stamina", "rhythm", "reading")
AXIS_ORDER = (
    "jump_aim",
    "flow_aim",
    "aim_control",
    "spatial_precision",
    "raw_speed",
    "stamina",
    "finger_control",
    "reading",
)
AXIS_TYPES = {axis: f"{axis.upper()}_DOMINANT" for axis in AXIS_ORDER}
PAIR_TYPES = {
    frozenset({"jump_aim", "spatial_precision"}): "JUMP_PRECISION",
    frozenset({"flow_aim", "stamina"}): "FLOW_STAMINA",
    frozenset({"raw_speed", "stamina"}): "SPEED_STAMINA",
    frozenset({"raw_speed", "finger_control"}): "SPEED_FINGER_CONTROL",
    frozenset({"finger_control", "reading"}): "FINGER_CONTROL_READING",
    frozenset({"aim_control", "reading"}): "AIM_CONTROL_READING",
    frozenset({"stamina", "reading"}): "STAMINA_READING",
}

MIN_EMITTED_AXES = 6
BALANCED_SPREAD_MAX = 0.14
MIN_TOP_SCORE = 0.50
MIN_PROMINENCE = 0.07
CO_DOMINANT_GAP_MAX = 0.08
MAX_DOMINANT_AXES = 3


def _finite_score(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0.0:
        return None
    return number


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


def unavailable_archetype(reason: str, axes: dict[str, Any] | None = None) -> dict[str, Any]:
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
    """Classify a Map Demand axis object into a deterministic archetype."""
    scores: dict[str, float] = {}
    missing: list[str] = []
    for axis in AXIS_ORDER:
        axis_obj = axes.get(axis)
        value = _finite_score(axis_obj.get("score")) if isinstance(axis_obj, dict) else None
        if not isinstance(axis_obj, dict) or axis_obj.get("status") != "EMITTED" or value is None:
            missing.append(axis)
        else:
            scores[axis] = value

    if len(scores) < MIN_EMITTED_AXES:
        result = unavailable_archetype("INSUFFICIENT_EMITTED_AXES", axes)
        result["status"] = "INSUFFICIENT_EVIDENCE"
        result["axis_scores"] = scores
        result["missing_axes"] = missing
        result["decision_evidence"][0]["emitted_axis_count"] = len(scores)
        return result

    ranked = sorted(scores.items(), key=lambda item: (-item[1], AXIS_ORDER.index(item[0])))
    top_axis, top_score = ranked[0]
    second_score = ranked[1][1]
    values = list(scores.values())
    center = _median(values)
    low = min(values)
    spread = top_score - low
    prominence = top_score - center

    balanced = spread <= BALANCED_SPREAD_MAX or (
        top_score < MIN_TOP_SCORE and prominence < MIN_PROMINENCE
    )
    dominant_axes: list[str] = []
    if not balanced:
        dominant_axes.append(top_axis)
        for axis, score in ranked[1:]:
            if len(dominant_axes) >= MAX_DOMINANT_AXES:
                break
            if (
                top_score - score <= CO_DOMINANT_GAP_MAX
                and score >= MIN_TOP_SCORE
                and score - center >= MIN_PROMINENCE
            ):
                dominant_axes.append(axis)

    if balanced:
        primary = "BALANCED"
        secondary: list[str] = []
        decision_distance = max(0.0, BALANCED_SPREAD_MAX - spread)
    elif len(dominant_axes) == 1:
        primary = AXIS_TYPES[dominant_axes[0]]
        secondary = []
        decision_distance = max(0.0, (top_score - second_score) - CO_DOMINANT_GAP_MAX)
    elif len(dominant_axes) == 2:
        primary = PAIR_TYPES.get(frozenset(dominant_axes), "HYBRID")
        secondary = [AXIS_TYPES[axis] for axis in dominant_axes]
        decision_distance = max(0.0, CO_DOMINANT_GAP_MAX - (top_score - second_score))
    else:
        primary = "HYBRID"
        secondary = [AXIS_TYPES[axis] for axis in dominant_axes]
        third_score = scores[dominant_axes[2]]
        decision_distance = max(0.0, CO_DOMINANT_GAP_MAX - (top_score - third_score))

    completeness = len(scores) / len(AXIS_ORDER)
    if completeness == 1.0 and top_score >= 0.70 and decision_distance >= 0.05:
        confidence = "HIGH"
    elif completeness < 1.0 or decision_distance < 0.02 or top_score < MIN_TOP_SCORE:
        confidence = "LOW"
    else:
        confidence = "MEDIUM"

    boundary_uncertainty = 1.0 - min(1.0, decision_distance / 0.12)
    missing_penalty = (1.0 - completeness) * 0.5
    uncertainty = max(0.0, min(1.0, boundary_uncertainty + missing_penalty))

    return {
        "schema_version": ARCHETYPE_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "status": "CLASSIFIED",
        "primary_type": primary,
        "secondary_types": secondary,
        "dominant_axes": dominant_axes,
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
                "decision_distance": decision_distance,
                "thresholds": {
                    "balanced_spread_max": BALANCED_SPREAD_MAX,
                    "min_top_score": MIN_TOP_SCORE,
                    "min_prominence": MIN_PROMINENCE,
                    "co_dominant_gap_max": CO_DOMINANT_GAP_MAX,
                },
                "evidence_tag": "HEURISTIC_V01_REQUIRES_HUMAN_VALIDATION",
            }
        ],
    }


def validate_human_response(response: dict[str, Any], task_ids: set[str]) -> None:
    """Fail-closed validator for the bounded archetype review package."""
    allowed_fields = {
        "task_id",
        "reviewer_id",
        "primary_axis",
        "secondary_axes",
        "axis_ratings",
        "review_mode",
        "axis_schema_version",
        "balanced",
        "cannot_judge",
        "confidence",
        "notes",
    }
    unknown = sorted(set(response) - allowed_fields)
    if unknown:
        raise ValueError(f"unknown response fields: {unknown}")
    task_id = response.get("task_id")
    if task_id not in task_ids:
        raise ValueError(f"unknown task_id: {task_id!r}")
    reviewer_id = response.get("reviewer_id")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise ValueError("reviewer_id is required")
    review_mode = response.get("review_mode")
    if review_mode is not None and review_mode not in {
        "BLIND",
        "ASSISTED_ALGORITHM_VISIBLE",
    }:
        raise ValueError("review_mode must be BLIND or ASSISTED_ALGORITHM_VISIBLE")
    cannot_judge = response.get("cannot_judge") is True
    primary_axis = response.get("primary_axis")
    secondary_axes = response.get("secondary_axes", [])
    axis_ratings = response.get("axis_ratings")
    response_axis_schema = response.get("axis_schema_version")
    if response_axis_schema not in {
        None,
        AXIS_SCHEMA_VERSION,
        PREVIOUS_ATOMIC_AXIS_SCHEMA_VERSION,
        OLDER_ATOMIC_AXIS_SCHEMA_VERSION,
        LEGACY_AXIS_SCHEMA_VERSION,
    }:
        raise ValueError("unknown axis_schema_version")
    response_axes = (
        LEGACY_AXIS_ORDER
        if response_axis_schema == LEGACY_AXIS_SCHEMA_VERSION
        else PREVIOUS_ATOMIC_AXIS_ORDER
        if response_axis_schema == OLDER_ATOMIC_AXIS_SCHEMA_VERSION
        else AXIS_ORDER
    )
    if response_axis_schema is None and isinstance(axis_ratings, dict):
        if set(axis_ratings) == set(LEGACY_AXIS_ORDER):
            response_axes = LEGACY_AXIS_ORDER
        elif set(axis_ratings) == set(PREVIOUS_ATOMIC_AXIS_ORDER):
            response_axes = PREVIOUS_ATOMIC_AXIS_ORDER
    if response_axis_schema is None and primary_axis in LEGACY_AXIS_ORDER:
        response_axes = LEGACY_AXIS_ORDER
    balanced = response.get("balanced") is True
    if not isinstance(secondary_axes, list) or any(axis not in response_axes for axis in secondary_axes):
        raise ValueError("secondary_axes must contain known axes")
    confidence = response.get("confidence")
    if confidence is not None and confidence not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("confidence must be LOW, MEDIUM, or HIGH")
    notes = response.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise ValueError("notes must be a string")
    if cannot_judge:
        if primary_axis is not None or secondary_axes or balanced or axis_ratings is not None:
            raise ValueError("cannot_judge is exclusive with type labels")
        return
    if axis_ratings is not None:
        if primary_axis is not None or secondary_axes or balanced:
            raise ValueError("axis_ratings is exclusive with categorical labels")
        if not isinstance(axis_ratings, dict) or set(axis_ratings) != set(response_axes):
            raise ValueError(f"axis_ratings must contain exactly all {len(response_axes)} axes")
        for axis, value in axis_ratings.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"axis_ratings.{axis} must be a finite non-negative number")
            number = float(value)
            if not math.isfinite(number) or number < 0.0:
                raise ValueError(f"axis_ratings.{axis} must be a finite non-negative number")
            if response_axis_schema in {
                PREVIOUS_ATOMIC_AXIS_SCHEMA_VERSION,
                OLDER_ATOMIC_AXIS_SCHEMA_VERSION,
                LEGACY_AXIS_SCHEMA_VERSION,
            } and (not isinstance(value, int) or value > 10):
                raise ValueError(f"legacy axis_ratings.{axis} must be an integer from 0 to 10")
        return
    if balanced:
        if primary_axis is not None or secondary_axes:
            raise ValueError("balanced is exclusive with axis labels")
        return
    if primary_axis not in response_axes:
        raise ValueError("primary_axis must be a known axis")
    if primary_axis in secondary_axes or len(secondary_axes) != len(set(secondary_axes)):
        raise ValueError("secondary_axes must be unique and exclude primary_axis")
