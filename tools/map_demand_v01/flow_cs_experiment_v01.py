"""Isolated target-size experiment for the beta.7+ Flow Aim measure.

This module is deliberately not registered as a runtime release.  It keeps
the beta.7 flow morphology, winning window, slider-aware geometry, and log
scale, but reintroduces target-size load around a CS4 neutral point.

The correction acts on the latent ``flow_load`` rather than adding stars or
multiplying the published star value.  Consequently it cannot create Flow
from a zero-load pattern, CS4 remains unchanged, and every CS above CS4
continues to increase demand without a hard saturation point.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from . import flow_target_size_v01 as target_size


SCHEMA_VERSION = "flow_cs_experiment_v0.1.0"
ALGORITHM_ID = "EXPERIMENTAL_FLOW_TARGET_SIZE_LOAD_V01"
REFERENCE_CS = target_size.REFERENCE_CS
MAX_EXPERIMENT_CS = target_size.REVIEWED_CS_MAX
SIZE_LOAD_EXPONENT = target_size.SIZE_LOAD_EXPONENT
FLOW_LOG_COEFFICIENT = target_size.FLOW_LOG_COEFFICIENT
FLOW_LOG_GAIN = target_size.FLOW_LOG_GAIN
circle_radius_px = target_size.circle_radius_px
size_load_factor = target_size.size_load_factor
latent_flow_load = target_size.latent_flow_load
flow_star_from_load = target_size.flow_star_from_load
adjust_flow_value = target_size.adjust_flow_value


def adjust_flow_measure(
    flow_measure: Mapping[str, Any],
    circle_size: float,
) -> dict[str, Any]:
    """Return an experimental copy of a beta.7+ Flow measure.

    A constant map-level size factor is monotonic, so it cannot change which
    local window wins.  The winning window value is transformed with the same
    function for payload consistency.  Insufficient measures stay
    insufficient and never receive fabricated Flow evidence.
    """

    if not isinstance(flow_measure, Mapping):
        raise TypeError("flow_measure must be a mapping")
    result = copy.deepcopy(dict(flow_measure))
    result["experimental_schema_version"] = SCHEMA_VERSION
    result["experimental_algorithm_id"] = ALGORITHM_ID
    status = str(result.get("status") or "INSUFFICIENT").upper()
    value = result.get("value")
    if status not in {"OK", "FULL", "DEGRADED"} or value is None:
        result["experimental_adjustment"] = None
        return result

    adjustment = adjust_flow_value(value, circle_size)
    result["value"] = adjustment["adjusted_value"]
    result["scale"] = "LOCAL_FLOW_LOAD_WITH_TARGET_SIZE_REBASE_EXP_V01"
    result["experimental_adjustment"] = adjustment
    winning = result.get("winning_section")
    if isinstance(winning, Mapping) and winning.get("value") is not None:
        winning_copy = copy.deepcopy(dict(winning))
        winning_copy["base_value"] = float(winning_copy["value"])
        winning_copy["value"] = adjust_flow_value(
            winning_copy["value"], circle_size
        )["adjusted_value"]
        result["winning_section"] = winning_copy
    signals = copy.deepcopy(dict(result.get("signals", {})))
    signals.update(
        {
            "target_size_experiment": SCHEMA_VERSION,
            "target_size_neutral_cs": REFERENCE_CS,
            "target_size_load_exponent": SIZE_LOAD_EXPONENT,
            "target_size_applied_to": "LATENT_FLOW_LOAD_BEFORE_LOG_STAR_SCALE",
            "target_size_hard_saturation": False,
            "runtime_release_registered": False,
        }
    )
    result["signals"] = signals
    return result


__all__ = [
    "SCHEMA_VERSION",
    "ALGORITHM_ID",
    "REFERENCE_CS",
    "MAX_EXPERIMENT_CS",
    "SIZE_LOAD_EXPONENT",
    "FLOW_LOG_COEFFICIENT",
    "FLOW_LOG_GAIN",
    "circle_radius_px",
    "size_load_factor",
    "latent_flow_load",
    "flow_star_from_load",
    "adjust_flow_value",
    "adjust_flow_measure",
]
