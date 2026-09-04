"""CS4-relative target-size load for the beta.7+ Flow Aim scale.

The transform operates on the latent flow load, before the established
logarithmic star conversion.  It is therefore neutral at CS4, cannot create
Flow from a zero-load pattern, and has no hard high-CS saturation.
"""

from __future__ import annotations

import math
from typing import Any


SCHEMA_VERSION = "flow_target_size_v0.1.0"
REFERENCE_CS = 4.0
REVIEWED_CS_MIN = 0.0
REVIEWED_CS_MAX = 12.0
SIZE_LOAD_EXPONENT = 0.70
FLOW_LOG_COEFFICIENT = 3.5
FLOW_LOG_GAIN = 1.55
BROKEN_GAMEFIELD_ROUNDING_ALLOWANCE = 1.00041
OBJECT_RADIUS_PX = 64.0


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def circle_radius_px(circle_size: float) -> float:
    """Return the stable/lazer-compatible osu! object radius."""

    cs = _finite(circle_size, "circle_size")
    if not REVIEWED_CS_MIN <= cs <= REVIEWED_CS_MAX:
        raise ValueError("Flow target-size policy covers CS [0, 12]")
    scale = (
        (1.0 - 0.7 * ((cs - 5.0) / 5.0))
        / 2.0
        * BROKEN_GAMEFIELD_ROUNDING_ALLOWANCE
    )
    radius = OBJECT_RADIUS_PX * scale
    if radius <= 0.0 or not math.isfinite(radius):
        raise ValueError("circle_size produced a nonpositive radius")
    return radius


def size_load_factor(circle_size: float) -> float:
    """Return continuous target-size load relative to CS4."""

    reference_radius = circle_radius_px(REFERENCE_CS)
    radius = circle_radius_px(circle_size)
    return (reference_radius / radius) ** SIZE_LOAD_EXPONENT


def latent_flow_load(flow_star: float) -> float:
    """Invert the beta.7 Flow logarithmic star scale."""

    value = _finite(flow_star, "flow_star")
    if value < 0.0:
        raise ValueError("flow_star must be nonnegative")
    return math.expm1(
        value * math.log(2.0) / FLOW_LOG_COEFFICIENT
    ) / FLOW_LOG_GAIN


def flow_star_from_load(flow_load: float) -> float:
    """Apply the beta.7 Flow logarithmic star scale."""

    load = _finite(flow_load, "flow_load")
    if load < 0.0:
        raise ValueError("flow_load must be nonnegative")
    return (
        FLOW_LOG_COEFFICIENT
        * math.log1p(FLOW_LOG_GAIN * load)
        / math.log(2.0)
    )


def adjust_flow_value(flow_star: float, circle_size: float) -> dict[str, float]:
    """Rebase one established Flow value through target-size load."""

    base_value = _finite(flow_star, "flow_star")
    base_load = latent_flow_load(base_value)
    factor = size_load_factor(circle_size)
    adjusted_load = base_load * factor
    adjusted_value = flow_star_from_load(adjusted_load)
    return {
        "base_value": base_value,
        "adjusted_value": adjusted_value,
        "delta": adjusted_value - base_value,
        "base_flow_load": base_load,
        "adjusted_flow_load": adjusted_load,
        "size_load_factor": factor,
        "circle_size": float(circle_size),
        "circle_radius_px": circle_radius_px(circle_size),
        "reference_circle_size": REFERENCE_CS,
        "reference_radius_px": circle_radius_px(REFERENCE_CS),
        "size_load_exponent": SIZE_LOAD_EXPONENT,
    }


__all__ = [
    "SCHEMA_VERSION",
    "REFERENCE_CS",
    "REVIEWED_CS_MIN",
    "REVIEWED_CS_MAX",
    "SIZE_LOAD_EXPONENT",
    "FLOW_LOG_COEFFICIENT",
    "FLOW_LOG_GAIN",
    "circle_radius_px",
    "size_load_factor",
    "latent_flow_load",
    "flow_star_from_load",
    "adjust_flow_value",
]
