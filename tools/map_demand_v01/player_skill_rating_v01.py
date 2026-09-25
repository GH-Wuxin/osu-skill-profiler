"""Evidence-first player Skill Rating over the unified axis star scale.

The module consumes *normalized axis outcomes* from score/replay adapters.  It
does not turn a raw score into a skill number, and it never changes v0.40 map
demand.  A demonstrated result gives a lower bound on the player's capacity;
an explicitly normalized non-demonstration gives an upper bound.  The result
is therefore an interval with visible evidence and coverage rather than a
weighted average of heterogeneous scores.
"""

from __future__ import annotations

import copy
import datetime as _dt
import math
from collections import defaultdict
from typing import Any, Iterable, Mapping

from .unified_star_scale_v01 import AXIS_ORDER, SCALE_ID


SCHEMA_VERSION = "player_skill_rating_v0.1"
RATING_ID = "player-skill-rating-v0.1"
DEMONSTRATED = "DEMONSTRATED"
NOT_DEMONSTRATED = "NOT_DEMONSTRATED"
VALID_OUTCOMES = frozenset({DEMONSTRATED, NOT_DEMONSTRATED})


class PlayerEvidenceError(ValueError):
    """Raised when normalized player evidence violates the contract."""


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise PlayerEvidenceError(f"{label} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PlayerEvidenceError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise PlayerEvidenceError(f"{label} must be finite")
    return number


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlayerEvidenceError(f"{label} must be a non-empty ISO timestamp")
    text = value.strip()
    try:
        _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PlayerEvidenceError(f"{label} must be an ISO timestamp") from exc
    return text


def _axis_payload(axis_demand: Mapping[str, Any], axis: str) -> tuple[float | None, str]:
    raw = axis_demand.get(axis)
    demand_status = "CANDIDATE"
    if isinstance(raw, Mapping):
        demand_status = str(
            raw.get("unified_star_status", raw.get("status", "UNKNOWN"))
        ).upper()
        raw = raw.get("unified_star_equivalent", raw.get("value"))
    if raw is None:
        return None, demand_status
    value = _finite(raw, f"map_demand.{axis}")
    if value < 0.0:
        raise PlayerEvidenceError(f"map_demand.{axis} must be non-negative")
    if demand_status not in {"ADMITTED", "CANDIDATE"}:
        raise PlayerEvidenceError(
            f"map_demand.{axis} must carry an ADMITTED or CANDIDATE unified-star status"
        )
    return value, demand_status


def make_evidence_record(
    *,
    player_id: str,
    map_id: str,
    timestamp: str,
    source: str,
    map_demand: Mapping[str, Any],
    axis_outcomes: Mapping[str, Mapping[str, Any]],
    score_id: str | None = None,
    mods: Iterable[str] = (),
    mod_context: str = "NM",
    normalization_id: str,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and package one already-normalized performance evidence row."""

    if not str(player_id).strip() or not str(map_id).strip():
        raise PlayerEvidenceError("player_id and map_id are required")
    if not str(source).strip():
        raise PlayerEvidenceError("source is required")
    if not str(normalization_id).strip():
        raise PlayerEvidenceError("normalization_id is required")
    if not str(mod_context).strip():
        raise PlayerEvidenceError("mod_context is required")
    if not isinstance(map_demand, Mapping):
        raise PlayerEvidenceError("map_demand must be an object")
    if not isinstance(axis_outcomes, Mapping):
        raise PlayerEvidenceError("axis_outcomes must be an object")

    normalized_axes: dict[str, dict[str, Any]] = {}
    for axis in AXIS_ORDER:
        demand, demand_status = _axis_payload(map_demand, axis)
        outcome = axis_outcomes.get(axis)
        if demand is None or not isinstance(outcome, Mapping):
            continue
        status = str(outcome.get("status", "")).upper()
        if status not in VALID_OUTCOMES:
            raise PlayerEvidenceError(
                f"axis_outcomes.{axis}.status must be DEMONSTRATED or NOT_DEMONSTRATED"
            )
        evidence_count = outcome.get("evidence_count", 1)
        try:
            evidence_count_number = int(evidence_count)
        except (TypeError, ValueError, OverflowError) as exc:
            raise PlayerEvidenceError(
                f"axis_outcomes.{axis}.evidence_count must be positive"
            ) from exc
        if isinstance(evidence_count, bool) or evidence_count_number < 1:
            raise PlayerEvidenceError(f"axis_outcomes.{axis}.evidence_count must be positive")
        normalized_axes[axis] = {
            "status": status,
            "demand_star": demand,
            "demand_status": demand_status,
            "evidence_count": evidence_count_number,
            "source_detail": outcome.get("source_detail"),
            "quality": outcome.get("quality"),
        }
    if not normalized_axes:
        raise PlayerEvidenceError("at least one axis outcome with map demand is required")

    return {
        "schema_version": SCHEMA_VERSION,
        "player_id": str(player_id),
        "map_id": str(map_id),
        "score_id": None if score_id is None else str(score_id),
        "timestamp": _timestamp(timestamp, "timestamp"),
        "source": str(source),
        "mods": sorted({str(mod).upper() for mod in mods}),
        "mod_context": str(mod_context).upper(),
        "normalization_id": str(normalization_id),
        "axis_outcomes": normalized_axes,
        "metadata": copy.deepcopy(dict(metadata or {})),
    }


def _coverage(values: list[float], reference_range: tuple[float, float] | None) -> float | None:
    if not values or reference_range is None:
        return None
    low, high = reference_range
    if not (math.isfinite(low) and math.isfinite(high) and high > low):
        return None
    return max(0.0, min(1.0, (max(values) - min(values)) / (high - low)))


def _axis_estimate(
    records: list[Mapping[str, Any]],
    axis: str,
    *,
    reference_range: tuple[float, float] | None,
    min_evidence: int,
    min_maps: int,
    min_timepoints: int,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for record in records:
        outcome = (record.get("axis_outcomes") or {}).get(axis)
        if not isinstance(outcome, Mapping):
            continue
        demand = outcome.get("demand_star")
        status = str(outcome.get("status", "")).upper()
        if demand is None or status not in VALID_OUTCOMES:
            continue
        observations.append(
            {
                "demand": _finite(demand, f"{axis}.demand_star"),
                "demand_status": str(outcome.get("demand_status", "CANDIDATE")),
                "status": status,
                "map_id": str(record.get("map_id")),
                "timestamp": str(record.get("timestamp")),
                "source": str(record.get("source")),
                "evidence_count": int(outcome.get("evidence_count", 1)),
            }
        )

    evidence_count = sum(item["evidence_count"] for item in observations)
    distinct_maps = {item["map_id"] for item in observations}
    distinct_timepoints = {item["timestamp"] for item in observations}
    observed_demands = [item["demand"] for item in observations]
    demand_statuses = {item["demand_status"] for item in observations}
    base = {
        "rating": None,
        "uncertainty": {"lower": None, "upper": None},
        "evidence_count": evidence_count,
        "coverage": _coverage(observed_demands, reference_range),
        "status": "UNKNOWN",
        "axis": axis,
        "sample_map_count": len(distinct_maps),
        "sample_timepoint_count": len(distinct_timepoints),
        "sources": sorted({item["source"] for item in observations}),
        "demand_statuses": sorted(demand_statuses),
        "evidence": observations,
        "reason": None,
    }
    if evidence_count < min_evidence or len(distinct_maps) < min_maps or len(distinct_timepoints) < min_timepoints:
        base["reason"] = "insufficient_multi_map_multi_time_evidence"
        return base

    demonstrated = [item["demand"] for item in observations if item["status"] == DEMONSTRATED]
    not_demonstrated = [item["demand"] for item in observations if item["status"] == NOT_DEMONSTRATED]
    if not demonstrated:
        # Failures alone cannot distinguish low ability from a missing or
        # mismatched sample, so this intentionally remains UNKNOWN.
        base["reason"] = "no_demonstrated_capacity_evidence"
        return base

    lower = max(demonstrated)
    upper = min(not_demonstrated) if not_demonstrated else None
    if upper is not None and lower > upper:
        base["reason"] = "contradictory_capacity_bounds"
        return base

    base["uncertainty"] = {"lower": lower, "upper": upper}
    base["rating"] = lower if upper is None else (lower + upper) / 2.0
    base["status"] = (
        "ADMITTED"
        if upper is not None and demand_statuses == {"ADMITTED"}
        else "CANDIDATE"
    )
    base["reason"] = (
        "interval_censored_multi_map_evidence"
        if upper is not None
        else "lower_bound_only_capacity_evidence"
    )
    return base


def estimate_player_skill_profile(
    records: Iterable[Mapping[str, Any]],
    *,
    player_id: str | None = None,
    normalization_id: str | None = None,
    reference_range: tuple[float, float] | None = None,
    min_evidence: int = 3,
    min_maps: int = 3,
    min_timepoints: int = 2,
    mod_context: str | None = None,
) -> dict[str, Any]:
    """Estimate axis capacities from normalized interval evidence.

    The function does not aggregate across axes.  `overall` stays explicitly
    unissued because the cross-axis Skill Rating contract is separate.
    """

    if min_evidence <= 0 or min_maps <= 0 or min_timepoints <= 0:
        raise PlayerEvidenceError("minimum evidence gates must be positive")
    materialized = [dict(record) for record in records]
    if player_id is None and not materialized:
        raise PlayerEvidenceError("at least one evidence record is required")
    if player_id is None:
        player_ids = {str(record.get("player_id")) for record in materialized}
        if len(player_ids) != 1 or "None" in player_ids:
            raise PlayerEvidenceError("records must identify exactly one player")
        player_id = next(iter(player_ids))
    materialized = [record for record in materialized if str(record.get("player_id")) == str(player_id)]
    contexts = {
        str(record.get("mod_context") or "NM").upper()
        for record in materialized
    }
    if mod_context is None and len(contexts) > 1:
        raise PlayerEvidenceError(
            "records contain multiple mod_context values; estimate each context separately"
        )
    resolved_mod_context = str(mod_context or next(iter(contexts), "NM")).upper()
    materialized = [
        record
        for record in materialized
        if str(record.get("mod_context") or "NM").upper() == resolved_mod_context
    ]
    if normalization_id is not None:
        materialized = [
            record
            for record in materialized
            if str(record.get("normalization_id")) == str(normalization_id)
        ]

    axes = {
        axis: _axis_estimate(
            materialized,
            axis,
            reference_range=reference_range,
            min_evidence=min_evidence,
            min_maps=min_maps,
            min_timepoints=min_timepoints,
        )
        for axis in AXIS_ORDER
    }
    statuses = {item["status"] for item in axes.values()}
    profile_status = (
        "ADMITTED"
        if statuses == {"ADMITTED"}
        else "CANDIDATE"
        if statuses - {"UNKNOWN"}
        else "UNKNOWN"
    )
    timestamps = sorted(str(record.get("timestamp")) for record in materialized if record.get("timestamp"))
    return {
        "schema_version": SCHEMA_VERSION,
        "rating_id": RATING_ID,
        "player_id": str(player_id),
        "status": profile_status,
        "scale_id": SCALE_ID,
        "mod_context": resolved_mod_context,
        "normalization_id": normalization_id,
        "axes": axes,
        "overall": {
            "status": "NOT_EMITTED",
            "rating": None,
            "reason": "cross_axis_aggregation_contract_not_defined",
        },
        "source_window": {
            "from": timestamps[0] if timestamps else None,
            "to": timestamps[-1] if timestamps else None,
        },
        "evidence_count": len(materialized),
        "coverage": {
            axis: item["coverage"] for axis, item in axes.items()
        },
        "provenance": [
            "normalized_multi_map_player_evidence",
            "interval_censored_capacity_estimation",
            "no_cross_axis_aggregation",
            "single_score_is_not_player_skill_rating",
        ],
    }


__all__ = [
    "DEMONSTRATED",
    "NOT_DEMONSTRATED",
    "PlayerEvidenceError",
    "RATING_ID",
    "SCHEMA_VERSION",
    "estimate_player_skill_profile",
    "make_evidence_record",
]
