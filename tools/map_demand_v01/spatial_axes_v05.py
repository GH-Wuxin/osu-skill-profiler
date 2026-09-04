"""Beta.9.2 Flow target-size load over beta.9 spatial evidence.

All geometry, morphology, local-window selection, and Micro Precision are
delegated unchanged to ``spatial_axes_v04``.  Only the winning Flow value is
rebased through the effective circle size around a CS4 neutral point.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping

from . import flow_target_size_v01 as target_size
from . import spatial_axes_v04 as previous


SCHEMA_VERSION = "spatial_axes_v0.6.0"
LOCAL_SIGNAL_VERSION = previous.LOCAL_SIGNAL_VERSION
REFERENCE_RADIUS_PX = previous.REFERENCE_RADIUS_PX
FULL_COVERAGE = previous.FULL_COVERAGE
DEGRADED_COVERAGE = previous.DEGRADED_COVERAGE

JUMP_SCALE = previous.JUMP_SCALE
JUMP_SUPPORT_POLICY_ID = previous.JUMP_SUPPORT_POLICY_ID
JUMP_PUBLIC_FRONTIER_POLICY_ID = previous.JUMP_PUBLIC_FRONTIER_POLICY_ID
PRECISION_SCALE = previous.PRECISION_SCALE
FLOW_SCALE = "LOCAL_FLOW_LATENT_LOAD_TARGET_SIZE_CS4_V05"


def _target_size_signals(
    signals: Mapping[str, Any] | None,
    adjustment: Mapping[str, float] | None,
) -> dict[str, Any]:
    result = copy.deepcopy(dict(signals or {}))
    result.update(
        {
            "target_size_schema_version": target_size.SCHEMA_VERSION,
            "target_size_reference_cs": target_size.REFERENCE_CS,
            "target_size_load_exponent": target_size.SIZE_LOAD_EXPONENT,
            "target_size_applied_to": (
                "LATENT_FLOW_LOAD_BEFORE_LOG_STAR_SCALE"
            ),
            "target_size_hard_saturation": False,
            "target_size_reviewed_cs_range": [
                target_size.REVIEWED_CS_MIN,
                target_size.REVIEWED_CS_MAX,
            ],
        }
    )
    if adjustment is not None:
        result["target_size_adjustment"] = dict(adjustment)
    return result


def apply_flow_target_size(
    flow_measure: Mapping[str, Any],
    circle_size: Any,
) -> dict[str, Any]:
    """Return a production Flow measure with CS4-relative target load."""

    if not isinstance(flow_measure, Mapping):
        raise TypeError("flow_measure must be a mapping")
    result = copy.deepcopy(dict(flow_measure))
    result["scale"] = FLOW_SCALE
    status = str(result.get("status") or "INSUFFICIENT").upper()
    value = result.get("value")
    if status not in {"OK", "FULL", "DEGRADED"} or value is None:
        result["signals"] = _target_size_signals(
            result.get("signals"), None
        )
        return result

    try:
        adjustment = target_size.adjust_flow_value(value, circle_size)
    except ValueError:
        missing = list(result.get("missing_required_fields") or [])
        if "effective_circle_size" not in missing:
            missing.append("effective_circle_size")
        result.update(
            status="INSUFFICIENT",
            value=None,
            reason="EFFECTIVE_CIRCLE_SIZE_OUTSIDE_REVIEWED_RANGE",
            missing_required_fields=missing,
            winning_section=None,
        )
        result["signals"] = _target_size_signals(
            result.get("signals"), None
        )
        return result

    result["value"] = adjustment["adjusted_value"]
    winning = result.get("winning_section")
    if isinstance(winning, Mapping) and winning.get("value") is not None:
        winning_copy = copy.deepcopy(dict(winning))
        winning_adjustment = target_size.adjust_flow_value(
            winning_copy["value"], circle_size
        )
        winning_copy["base_value"] = winning_adjustment["base_value"]
        winning_copy["value"] = winning_adjustment["adjusted_value"]
        result["winning_section"] = winning_copy
    result["signals"] = _target_size_signals(
        result.get("signals"), adjustment
    )
    return result


def extract_spatial_measures(
    rows: Iterable[dict[str, Any]],
    resolved_preempt_ms: float | None = None,
    effective_mods: Iterable[str] = (),
    *,
    circle_size: Any,
) -> dict[str, Any]:
    """Return beta.9 spatial measures with only Flow target-size-adjusted."""

    source = list(rows)
    delegated = previous.extract_spatial_measures(
        source,
        resolved_preempt_ms=resolved_preempt_ms,
        effective_mods=effective_mods,
    )
    result = dict(delegated)
    result.update(
        schema_version=SCHEMA_VERSION,
        flow_aim=apply_flow_target_size(
            delegated["flow_aim"], circle_size
        ),
    )
    return result


__all__ = [
    "SCHEMA_VERSION",
    "LOCAL_SIGNAL_VERSION",
    "REFERENCE_RADIUS_PX",
    "FULL_COVERAGE",
    "DEGRADED_COVERAGE",
    "JUMP_SCALE",
    "JUMP_SUPPORT_POLICY_ID",
    "JUMP_PUBLIC_FRONTIER_POLICY_ID",
    "PRECISION_SCALE",
    "FLOW_SCALE",
    "apply_flow_target_size",
    "extract_spatial_measures",
]
