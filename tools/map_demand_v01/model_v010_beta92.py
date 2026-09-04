"""Opt-in beta.9.2 Flow target-size load repair.

Beta.9.2 inherits beta.9.1 in full and changes only Flow Aim.  The existing
slider-aware path evidence and winning local window are preserved; effective
circle size modifies the latent Flow load continuously around a CS4 neutral
point before the established logarithmic star conversion.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import contract as C
from . import model_v010_beta7 as beta7
from . import model_v010_beta91 as previous
from . import profile_semantics_v01 as legacy_semantics
from . import profile_semantics_v02 as semantics
from . import spatial_axes_v05 as spatial
from .public_beta import promote


ALGORITHM_ID = "MAP_DEMAND_FLOW_TARGET_SIZE_V010_BETA92"
MAP_DEMAND_VERSION = "0.10.0-beta.9.2"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.9.2"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_CONTRACT_VERSION = previous.AXIS_CONTRACT_VERSION
AXIS_ORDER = previous.AXIS_ORDER
EXPECTED_LOCAL_SIGNAL_VERSION = previous.EXPECTED_LOCAL_SIGNAL_VERSION
sha256_file_bytes = previous.sha256_file_bytes

SUPPORT_AWARE_AXES = previous.SUPPORT_AWARE_AXES
REBUILT_LOCAL_AXES = tuple(
    dict.fromkeys((*previous.REBUILT_LOCAL_AXES, "flow_aim"))
)
INHERITED_AXIS_CONTRACTS = {
    axis: contract
    for axis, contract in previous.INHERITED_AXIS_CONTRACTS.items()
    if axis != "flow_aim"
}
REBUILT_LOCAL_AXIS_CONTRACTS = {
    **previous.REBUILT_LOCAL_AXIS_CONTRACTS,
    "flow_aim": "beta92_flow_target_size_cs4_velocity_power_070_value",
}
CHANGED_FROM_PREVIOUS = frozenset({"flow_aim"})

ORDINARY_INPUT_ROLE = previous.ORDINARY_INPUT_ROLE
AUXILIARY_HITSOUND_INPUT_ROLE = previous.AUXILIARY_HITSOUND_INPUT_ROLE
extract_from_path = previous.extract_from_path

RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.9.2 · Flow CS4 目标尺寸修正版",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Flow target-size load is calibrated relative to CS4 and reviewed over effective CS 0-12",
        "The target-size exponent matches the established Flow velocity exponent 0.70 and has no high-CS hard saturation",
        "Flow morphology, slider-aware geometry, and local winner selection remain inherited from beta.7",
        "Raw Speed and Micro Precision retain beta.9.1/beta.9 behavior respectively",
        "Aspire and adversarial maps remain robustness evidence, never ordinary-scale calibration data",
    ],
}


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Mapping[str, Any] | None = None,
    difficulty: Mapping[str, Any] | None = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
    *,
    source_local_signal_version: str,
) -> tuple[dict[str, Any], list[str]]:
    components, warnings = previous.extract_components(
        local_rows,
        features,
        difficulty,
        clock_rate,
        effective_mods,
        source_local_signal_version=source_local_signal_version,
    )
    rows = list(local_rows)
    component_mods = tuple(components.get("beta91_effective_mods", ()))
    circle_size = (
        difficulty.get("CircleSize")
        if isinstance(difficulty, Mapping)
        else None
    )
    components["beta92_spatial_axes"] = spatial.extract_spatial_measures(
        rows,
        resolved_preempt_ms=components.get("reading_preempt_median_ms"),
        effective_mods=component_mods,
        circle_size=circle_size,
    )
    components["beta92_source_local_signal_version"] = (
        source_local_signal_version
    )
    components["beta92_effective_mods"] = list(component_mods)
    components["beta92_effective_circle_size"] = circle_size
    return components, list(warnings)


def calibration_id(base_calibration_id: str) -> str:
    return (
        "md010beta92:flow_target_size_cs4:latent_load_power_0_70:"
        + previous.calibration_id(base_calibration_id)
    )


def _replace_flow_axis(
    output: dict[str, Any],
    raw_measure: Mapping[str, Any],
) -> None:
    measure = beta7._as_axis_measure(raw_measure, "flow_aim")  # noqa: SLF001
    item = legacy_semantics.apply_axis_measure(
        {},
        measure,
        method="CONTINUOUS_DIRECTIONAL_PATH_FLOW_TARGET_SIZE_V05",
        scale_method=spatial.FLOW_SCALE,
        component="beta92_flow_aim",
        evidence_tag="PUBLIC_BETA92_FLOW_TARGET_SIZE_EVIDENCE",
        confidence="LOW",
    )
    item["unit"] = "star_equivalent"
    item["combination_policy"] = "SAME_SECTION_MECHANISM_EVIDENCE_ONLY"
    item["signals"] = dict(raw_measure.get("signals", {}))
    item["evidence_quality"] = str(
        raw_measure.get("status") or "INSUFFICIENT"
    )
    item["warnings"] = []
    if item["status"] != semantics.AXIS_EMITTED:
        item["warnings"].append("BETA92_INSUFFICIENT_FLOW_EVIDENCE")
        output["warnings"].append(
            {
                "code": "BETA92_FLOW_INSUFFICIENT_EVIDENCE",
                "axis": "flow_aim",
                "message": measure.evidence.reason,
            }
        )
    elif item["evidence_quality"] == "DEGRADED":
        item["warnings"].append("BETA92_DEGRADED_COVERAGE")
    item["axis_contract_version"] = REBUILT_LOCAL_AXIS_CONTRACTS[
        "flow_aim"
    ]
    item["stars"] = item.get("demand_star_equivalent")
    item["public_value_semantics"] = "BETA92_LOCAL_MECHANISM_AXIS_VALUE"
    item["support_frontiers_available"] = False
    output["axes"]["flow_aim"] = item


def analyze_components(**kwargs: Any) -> dict[str, Any]:
    components = kwargs.get("components")
    if not isinstance(components, Mapping):
        raise ValueError("beta9.2 requires a components mapping")
    if (
        components.get("beta92_source_local_signal_version")
        != EXPECTED_LOCAL_SIGNAL_VERSION
    ):
        raise ValueError("beta9.2 component Local Signal provenance mismatch")
    spatial_measures = components.get("beta92_spatial_axes")
    if not isinstance(spatial_measures, Mapping):
        raise ValueError("beta9.2 requires beta92_spatial_axes")

    output = previous.analyze_components(**kwargs)
    promote(
        output,
        algorithm_id=ALGORITHM_ID,
        map_demand_version=MAP_DEMAND_VERSION,
        calibration_id=calibration_id(
            str(kwargs["calibration"].get("calibration_id", ""))
        ),
        schema_version=SCHEMA_VERSION,
        release=RELEASE,
    )
    if output.get("status") == "OK":
        flow = spatial_measures.get("flow_aim")
        if not isinstance(flow, Mapping):
            raise ValueError("beta9.2 Flow measure is missing")
        _replace_flow_axis(output, flow)
        output["summaries"] = semantics.derive_profile_summaries(
            output["axes"]
        )
        output["archetype"] = semantics.classify_star_archetype(
            output["axes"]
        )
        diagnostics = output["diagnostics"]
        diagnostics["beta92_spatial_axes"] = spatial_measures
        diagnostics["beta92_changed_axes"] = sorted(CHANGED_FROM_PREVIOUS)
        diagnostics["beta92_effective_circle_size"] = components.get(
            "beta92_effective_circle_size"
        )
        diagnostics["beta92_flow_target_size_policy"] = (
            "CS4_NEUTRAL_LATENT_LOAD_POWER_0_70_NO_HARD_SATURATION"
        )
        diagnostics["beta92_flow_winner_policy"] = (
            "INHERITED_WINNER_IDENTITY_CONSTANT_MAP_LEVEL_SIZE_FACTOR"
        )

    C.scan_finite(output, "model_v010_beta92.output")
    return output


__all__ = [
    "ALGORITHM_ID",
    "MAP_DEMAND_VERSION",
    "SCHEMA_VERSION",
    "AXIS_SCHEMA_VERSION",
    "AXIS_CONTRACT_VERSION",
    "AXIS_ORDER",
    "RELEASE",
    "EXPECTED_LOCAL_SIGNAL_VERSION",
    "SUPPORT_AWARE_AXES",
    "REBUILT_LOCAL_AXES",
    "INHERITED_AXIS_CONTRACTS",
    "REBUILT_LOCAL_AXIS_CONTRACTS",
    "CHANGED_FROM_PREVIOUS",
    "ORDINARY_INPUT_ROLE",
    "AUXILIARY_HITSOUND_INPUT_ROLE",
    "extract_from_path",
    "extract_components",
    "analyze_components",
    "calibration_id",
    "sha256_file_bytes",
]
