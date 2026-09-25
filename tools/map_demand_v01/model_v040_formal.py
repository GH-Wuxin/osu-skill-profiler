"""Formal v0.40 map-demand runtime envelope.

The frozen MAP_DEMAND_V100 computation remains the numeric basis.  This
module gives the HTTP workbench a distinct release identity so `/w skill`
cannot silently report the legacy V0.95/V1.0 label after the v0.40 switch.
The Slider pressure and formal admission fields are attached by the
workbench after it has the concrete local `.osu` path.
"""

from __future__ import annotations

from typing import Any

from . import model_v100 as base
from osu_skill_profiler.formal_release import AXES


ALGORITHM_ID = "FORMAL_MAP_DEMAND_V040"
MAP_DEMAND_VERSION = "0.40.0"
SCHEMA_VERSION = "map_demand_formal_v0.40.0"
AXIS_SCHEMA_VERSION = "formal_map_demand_axes_v040"
AXIS_ORDER = AXES
EXPECTED_LOCAL_SIGNAL_VERSION = getattr(base, "EXPECTED_LOCAL_SIGNAL_VERSION", None)
SUPPORT_AWARE_AXES = getattr(base, "SUPPORT_AWARE_AXES", ())
REBUILT_LOCAL_AXES = getattr(base, "REBUILT_LOCAL_AXES", ())
INHERITED_AXIS_CONTRACTS = getattr(base, "INHERITED_AXIS_CONTRACTS", {})
REBUILT_LOCAL_AXIS_CONTRACTS = getattr(base, "REBUILT_LOCAL_AXIS_CONTRACTS", {})
ORDINARY_INPUT_ROLE = getattr(base, "ORDINARY_INPUT_ROLE", "ordinary_map_input")
AUXILIARY_HITSOUND_INPUT_ROLE = getattr(base, "AUXILIARY_HITSOUND_INPUT_ROLE", "auxiliary_hitsound_input")

RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "DEPLOYABLE_FORMAL_MAP_DEMAND",
    "label": "0.40.0 · Formal Map Demand + Slider pressure",
    "basis": "MAP_DEMAND_V100",
    "player_skill_score_admitted": False,
    "slider_pressure_scalar": "max required cursor velocity over support-gated sustained candidates",
    "known_limitations": [
        "Nine axes are map demand values and do not score player ability",
        "Slider pressure is a physical normalized velocity scalar, not a weighted star sum",
        "Per-event player Slider judgement remains a separate independent-trace contract",
    ],
}

extract_from_path = base.extract_from_path
extract_components = base.extract_components
sha256_file_bytes = base.sha256_file_bytes


def calibration_id(base_calibration_id: str) -> str:
    return "formal40:" + str(base_calibration_id)


def analyze_components(**kwargs: Any) -> dict[str, Any]:
    output = base.analyze_components(**kwargs)
    identity = dict(output.get("identity") or {})
    identity.update(
        {
            "algorithm_id": ALGORITHM_ID,
            "map_demand_version": MAP_DEMAND_VERSION,
            "calibration_id": calibration_id(
                str(kwargs["calibration"].get("calibration_id", ""))
            ),
        }
    )
    output["identity"] = identity
    output["schema_version"] = SCHEMA_VERSION
    output["release"] = {**RELEASE, "known_limitations": list(RELEASE["known_limitations"])}
    return output


__all__ = [
    "ALGORITHM_ID",
    "AXIS_ORDER",
    "AXIS_SCHEMA_VERSION",
    "MAP_DEMAND_VERSION",
    "RELEASE",
    "SCHEMA_VERSION",
    "analyze_components",
    "calibration_id",
    "extract_components",
    "extract_from_path",
    "sha256_file_bytes",
]
