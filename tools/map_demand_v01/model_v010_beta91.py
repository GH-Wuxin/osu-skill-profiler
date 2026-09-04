"""Public beta.9.1 Raw frontier objective-order repair.

Beta.9.1 preserves beta.9's rate calibration and Precision implementation.  It
changes only Raw Speed: the 1.5 partial-support exponent participates in every
candidate threshold comparison before the winning frontier is selected.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import contract as C
from . import model_v010_beta9 as previous
from . import profile_semantics_v02 as semantics
from . import tapping_axes_v05 as tapping
from .public_beta import promote


ALGORITHM_ID = "MAP_DEMAND_RAW_POWERED_FRONTIER_V010_BETA91"
MAP_DEMAND_VERSION = "0.10.0-beta.9.1"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.9.1"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_CONTRACT_VERSION = previous.AXIS_CONTRACT_VERSION
AXIS_ORDER = previous.AXIS_ORDER
EXPECTED_LOCAL_SIGNAL_VERSION = previous.EXPECTED_LOCAL_SIGNAL_VERSION
sha256_file_bytes = previous.sha256_file_bytes

SUPPORT_AWARE_AXES = previous.SUPPORT_AWARE_AXES
REBUILT_LOCAL_AXES = previous.REBUILT_LOCAL_AXES
INHERITED_AXIS_CONTRACTS = previous.INHERITED_AXIS_CONTRACTS
REBUILT_LOCAL_AXIS_CONTRACTS = previous.REBUILT_LOCAL_AXIS_CONTRACTS
CHANGED_FROM_PREVIOUS = frozenset({"raw_speed"})

ORDINARY_INPUT_ROLE = previous.ORDINARY_INPUT_ROLE
AUXILIARY_HITSOUND_INPUT_ROLE = previous.AUXILIARY_HITSOUND_INPUT_ROLE
extract_from_path = previous.extract_from_path

RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.9.1 · Raw 支撑阈值选择修正版",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Raw Speed is not clipped at 10; end-to-end physical rate is bounded by the Local Signal 25 ms execution-time floor",
        "Micro Precision retains beta.9 target-tolerance and close-landing semantics",
        "Terminal double-tap feasibility remains a versioned Local Signal limitation",
        "Score-level evidence is map-wide; it cannot prove that a player hit one exact local burst",
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
    component_mods = tuple(components.get("beta9_effective_mods", ()))
    components["beta91_tapping_axes"] = tapping.extract_tapping_measures(rows)
    components["beta91_source_local_signal_version"] = source_local_signal_version
    components["beta91_effective_mods"] = list(component_mods)
    return components, list(warnings)


def calibration_id(base_calibration_id: str) -> str:
    return (
        "md010beta91:raw_rate_5:partial_support_power_1_5_scan_v02:"
        + previous.calibration_id(base_calibration_id)
    )


def _replace_raw_axis(
    output: dict[str, Any],
    raw_measure: Mapping[str, Any],
) -> None:
    item = semantics.apply_supported_axis_measure(
        {},
        raw_measure,
        method="EXECUTION_RATE_POWERED_SUPPORT_FRONTIER_RAW_V06",
        scale_method=tapping.RAW_SPEED_SCALE,
        component="beta91_raw_speed",
        evidence_tag="PUBLIC_BETA91_POWERED_THRESHOLD_FRONTIER_EVIDENCE",
        confidence="LOW",
    )
    item["unit"] = "star_equivalent"
    item["combination_policy"] = "AXIS_SELECTED_SUPPORT_FRONTIER_PEAK_SEPARATE"
    item["signals"] = dict(raw_measure.get("signals", {}))
    item["evidence_quality"] = str(
        raw_measure.get("status") or "INSUFFICIENT"
    )
    item["warnings"] = []
    if item["status"] != semantics.AXIS_EMITTED:
        item["warnings"].append("BETA91_INSUFFICIENT_SUPPORT_EVIDENCE")
        output["warnings"].append(
            {
                "code": "BETA91_AXIS_INSUFFICIENT_SUPPORT_EVIDENCE",
                "axis": "raw_speed",
                "message": str(
                    raw_measure.get("reason") or "insufficient support evidence"
                ),
            }
        )
    elif item["evidence_quality"] == "DEGRADED":
        item["warnings"].append("BETA91_DEGRADED_COVERAGE")
    output["axes"]["raw_speed"] = item


def analyze_components(**kwargs: Any) -> dict[str, Any]:
    components = kwargs.get("components")
    if not isinstance(components, Mapping):
        raise ValueError("beta9.1 requires a components mapping")
    if (
        components.get("beta91_source_local_signal_version")
        != EXPECTED_LOCAL_SIGNAL_VERSION
    ):
        raise ValueError("beta9.1 component Local Signal provenance mismatch")
    tapping_measures = components.get("beta91_tapping_axes")
    if not isinstance(tapping_measures, Mapping):
        raise ValueError("beta9.1 requires beta91_tapping_axes")

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
        raw = tapping_measures.get("raw_speed")
        if not isinstance(raw, Mapping):
            raise ValueError("beta9.1 Raw measure is missing")
        _replace_raw_axis(output, raw)
        output["summaries"] = semantics.derive_profile_summaries(output["axes"])
        output["archetype"] = semantics.classify_star_archetype(output["axes"])
        diagnostics = output["diagnostics"]
        diagnostics["beta91_tapping_axes"] = tapping_measures
        diagnostics["beta91_changed_axes"] = sorted(CHANGED_FROM_PREVIOUS)
        diagnostics["beta91_raw_policy"] = (
            "POWERED_PARTIAL_SUPPORT_DURING_ALL_THRESHOLD_WINNER_SEARCH"
        )
        diagnostics["beta91_physical_peak_policy"] = (
            "NOT_CLIPPED_AT_TEN_BOUNDED_BY_LOCAL_SIGNAL_25MS_FLOOR"
        )

    C.scan_finite(output, "model_v010_beta91.output")
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
