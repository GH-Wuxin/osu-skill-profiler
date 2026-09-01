"""Shared release-envelope promotion for public beta model layers."""
from __future__ import annotations

from typing import Any


def promote(
    output: dict[str, Any],
    *,
    algorithm_id: str,
    map_demand_version: str,
    calibration_id: str,
    schema_version: str,
    release: dict[str, Any],
) -> dict[str, Any]:
    """Replace only the public release envelope and retain basis provenance."""
    original_identity = dict(output["identity"])
    output["identity"] = {
        **original_identity,
        "algorithm_id": algorithm_id,
        "map_demand_version": map_demand_version,
        "calibration_id": calibration_id,
    }
    output["schema_version"] = schema_version
    output["release"] = {
        **release,
        "known_limitations": list(release["known_limitations"]),
    }
    output["diagnostics"]["release_basis_identity"] = original_identity
    return output
