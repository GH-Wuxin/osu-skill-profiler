"""Independent post-v0.40 measurement layer.

This is the narrow public entry point for the two new measurements.  It wraps
the frozen map-demand output, adds the common-star representation, and exposes
the player evidence estimator.  Selecting this module never changes the v0.40
algorithm or its historical fields.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .player_skill_rating_v01 import estimate_player_skill_profile
from .unified_star_scale_v01 import (
    apply_unified_star_scale,
    load_calibration,
)


RELEASE_ID = "post-v040-measurements-v0.1"
SCHEMA_VERSION = "osu_skill_profiler_measurements_v0.1"


def apply_map_measurements(
    frozen_v040_output: Mapping[str, Any],
    calibration: Mapping[str, Any],
) -> dict[str, Any]:
    """Add unified-star fields without rewriting the frozen map output."""

    result = apply_unified_star_scale(frozen_v040_output, calibration)
    result["measurement_release"] = {
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "map_demand_basis": "FORMAL_MAP_DEMAND_V040_FROZEN",
        "player_skill_rating": "SEPARATE_PLAYER_EVIDENCE_LAYER",
    }
    return result


def apply_map_measurements_from_path(
    frozen_v040_output: Mapping[str, Any],
    calibration_path: str,
) -> dict[str, Any]:
    """Load a packaged calibration and attach the independent map layer."""

    return apply_map_measurements(
        frozen_v040_output,
        load_calibration(calibration_path),
    )


def estimate_player_measurements(
    records: Iterable[Mapping[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    """Estimate the player axis vector from normalized evidence records."""

    result = estimate_player_skill_profile(records, **kwargs)
    result["measurement_release"] = {
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "map_demand_basis": "UNIFIED_STAR_DEMAND_EQUIVALENCE",
        "overall_scalar": "NOT_CONTRACTED",
    }
    return result


__all__ = [
    "RELEASE_ID",
    "SCHEMA_VERSION",
    "apply_map_measurements",
    "apply_map_measurements_from_path",
    "estimate_player_measurements",
]
