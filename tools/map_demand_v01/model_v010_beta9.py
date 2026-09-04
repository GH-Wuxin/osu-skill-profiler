"""Opt-in beta.9 Raw Speed and Micro Precision calibration repair.

Beta.8 remains replayable.  Beta.9 changes only Raw Speed and Micro
Precision: Raw receives a lower physical-rate conversion and non-linear
partial-burst support, while Precision restores bounded ordinary-target,
two-dimensional small-target tolerance, and legitimate non-zero correction
demand.  Every other axis is inherited from beta.8 unchanged.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import contract as C
from . import model_v010_beta8 as previous
from . import profile_semantics_v01 as legacy_semantics
from . import profile_semantics_v02 as semantics
from . import spatial_axes_v04 as spatial
from . import tapping_axes_v04 as tapping
from .public_beta import promote


ALGORITHM_ID = "MAP_DEMAND_RATE_PRECISION_AREA_V010_BETA9"
MAP_DEMAND_VERSION = "0.10.0-beta.9"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.9"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_CONTRACT_VERSION = semantics.AXIS_CONTRACT_VERSION
AXIS_ORDER = previous.AXIS_ORDER
EXPECTED_LOCAL_SIGNAL_VERSION = previous.EXPECTED_LOCAL_SIGNAL_VERSION
sha256_file_bytes = previous.sha256_file_bytes

SUPPORT_AWARE_AXES = previous.SUPPORT_AWARE_AXES
REBUILT_LOCAL_AXES = previous.REBUILT_LOCAL_AXES
INHERITED_AXIS_CONTRACTS = previous.INHERITED_AXIS_CONTRACTS
REBUILT_LOCAL_AXIS_CONTRACTS = {
    **previous.REBUILT_LOCAL_AXIS_CONTRACTS,
    "spatial_precision": "beta9_spatial_axes_v04_target_area_tolerance_value",
}

ORDINARY_INPUT_ROLE = previous.ORDINARY_INPUT_ROLE
AUXILIARY_HITSOUND_INPUT_ROLE = previous.AUXILIARY_HITSOUND_INPUT_ROLE
extract_from_path = previous.extract_from_path

RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.9 · Raw 标尺与 Micro Precision 修正版",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Raw Speed uses a lower independent rate scale and sub-linear partial-burst support; its physical peak remains an unbounded diagnostic",
        "Micro Precision separates a bounded ordinary-target floor from two-dimensional small-target tolerance; exact same-position repeats remain excluded from micro correction",
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
    # Beta.9 was released while beta.8's Raw helper temporarily exposed these
    # three calibration fields.  Preserve that beta.9 payload explicitly while
    # allowing the standalone beta.8 implementation to replay 9a1d104 exactly.
    beta8_raw_signals = components["beta8_tapping_axes"]["raw_speed"]["signals"]
    beta8_raw_signals.update(
        {
            "rate_baseline_per_s": tapping.previous.RAW_RATE_BASELINE_PER_S,
            "rate_per_star": tapping.previous.RAW_RATE_PER_STAR,
            "partial_support_exponent": 1.0,
        }
    )
    # Keep the provenance-carrying beta.7 row container intact until the
    # inherited validator has accepted it.  Extraction returns a replayable
    # list subclass, so materialising after validation is safe.
    rows = list(local_rows)
    component_mods = tuple(components.get("beta8_effective_mods", ()))
    components["beta9_spatial_axes"] = spatial.extract_spatial_measures(
        rows,
        resolved_preempt_ms=components.get("reading_preempt_median_ms"),
        effective_mods=component_mods,
    )
    components["beta9_tapping_axes"] = tapping.extract_tapping_measures(rows)
    components["beta9_source_local_signal_version"] = source_local_signal_version
    components["beta9_effective_mods"] = list(component_mods)
    return components, list(warnings)


def calibration_id(base_calibration_id: str) -> str:
    return (
        "md010beta9:raw_rate_5:partial_support_power_1:precision_area_4:"
        + previous.calibration_id(base_calibration_id)
    )


def _replace_supported_axis(
    output: dict[str, Any],
    axis: str,
    raw_measure: Mapping[str, Any],
    *,
    method: str,
    scale_method: str,
) -> None:
    item = semantics.apply_supported_axis_measure(
        {},
        raw_measure,
        method=method,
        scale_method=scale_method,
        component=f"beta9_{axis}",
        evidence_tag="PUBLIC_BETA9_SUPPORT_FRONTIER_EVIDENCE",
        confidence="LOW",
    )
    item["unit"] = "star_equivalent"
    item["combination_policy"] = "AXIS_SELECTED_SUPPORT_FRONTIER_PEAK_SEPARATE"
    item["signals"] = dict(raw_measure.get("signals", {}))
    item["evidence_quality"] = str(raw_measure.get("status") or "INSUFFICIENT")
    item["warnings"] = []
    if item["status"] != semantics.AXIS_EMITTED:
        item["warnings"].append("BETA9_INSUFFICIENT_SUPPORT_EVIDENCE")
        output["warnings"].append(
            {
                "code": "BETA9_AXIS_INSUFFICIENT_SUPPORT_EVIDENCE",
                "axis": axis,
                "message": str(
                    raw_measure.get("reason") or "insufficient support evidence"
                ),
            }
        )
    elif item["evidence_quality"] == "DEGRADED":
        item["warnings"].append("BETA9_DEGRADED_COVERAGE")
    output["axes"][axis] = item


def _replace_local_axis(
    output: dict[str, Any],
    axis: str,
    raw_measure: Mapping[str, Any],
    *,
    method: str,
) -> None:
    measure = previous.previous._as_axis_measure(raw_measure, axis)  # noqa: SLF001
    item = legacy_semantics.apply_axis_measure(
        {},
        measure,
        method=method,
        scale_method=str(raw_measure.get("scale") or "BETA9_LOCAL_SCALE"),
        component=f"beta9_{axis}",
        evidence_tag="PUBLIC_BETA9_LOCAL_MECHANISM_EVIDENCE",
        confidence="LOW",
    )
    item["unit"] = "star_equivalent"
    item["combination_policy"] = "SAME_SECTION_MECHANISM_EVIDENCE_ONLY"
    item["signals"] = dict(raw_measure.get("signals", {}))
    item["evidence_quality"] = str(raw_measure.get("status") or "INSUFFICIENT")
    item["warnings"] = []
    if item["status"] != semantics.AXIS_EMITTED:
        item["warnings"].append("BETA9_INSUFFICIENT_LOCAL_AXIS_EVIDENCE")
        output["warnings"].append(
            {
                "code": "BETA9_AXIS_INSUFFICIENT_LOCAL_EVIDENCE",
                "axis": axis,
                "message": measure.evidence.reason,
            }
        )
    elif item["evidence_quality"] == "DEGRADED":
        item["warnings"].append("BETA9_DEGRADED_COVERAGE")
    item["axis_contract_version"] = REBUILT_LOCAL_AXIS_CONTRACTS[axis]
    item["stars"] = item.get("demand_star_equivalent")
    item["public_value_semantics"] = "BETA9_LOCAL_MECHANISM_AXIS_VALUE"
    item["support_frontiers_available"] = False
    output["axes"][axis] = item


def analyze_components(**kwargs: Any) -> dict[str, Any]:
    components = kwargs.get("components")
    if not isinstance(components, Mapping):
        raise ValueError("beta9 requires a components mapping")
    if (
        components.get("beta9_source_local_signal_version")
        != EXPECTED_LOCAL_SIGNAL_VERSION
    ):
        raise ValueError("beta9 component Local Signal provenance mismatch")
    spatial_measures = components.get("beta9_spatial_axes")
    tapping_measures = components.get("beta9_tapping_axes")
    if not isinstance(spatial_measures, Mapping):
        raise ValueError("beta9 requires beta9_spatial_axes")
    if not isinstance(tapping_measures, Mapping):
        raise ValueError("beta9 requires beta9_tapping_axes")

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
        precision = spatial_measures.get("spatial_precision")
        if not isinstance(raw, Mapping) or not isinstance(precision, Mapping):
            raise ValueError("beta9 repaired axis measures are missing")
        _replace_supported_axis(
            output,
            "raw_speed",
            raw,
            method="EXECUTION_RATE_SUPPORT_FRONTIER_RAW_V05",
            scale_method=tapping.RAW_SPEED_SCALE,
        )
        _replace_local_axis(
            output,
            "spatial_precision",
            precision,
            method="MINIMUM_PHASE_TARGET_AREA_TOLERANCE_V04",
        )
        output["summaries"] = semantics.derive_profile_summaries(output["axes"])
        output["archetype"] = semantics.classify_star_archetype(output["axes"])
        diagnostics = output["diagnostics"]
        diagnostics["beta9_spatial_axes"] = spatial_measures
        diagnostics["beta9_tapping_axes"] = tapping_measures
        diagnostics["beta9_changed_axes"] = ["raw_speed", "spatial_precision"]
        diagnostics["beta9_raw_policy"] = (
            "LOWER_RATE_SCALE_AND_SUBLINEAR_PARTIAL_BURST_SUPPORT"
        )
        diagnostics["beta9_precision_policy"] = (
            "BOUNDED_ORDINARY_TOLERANCE_TWO_DIMENSIONAL_SMALL_TARGET_"
            "AND_NARROW_REPEAT_EXCLUSION"
        )
        diagnostics["beta9_physical_peak_policy"] = (
            "UNBOUNDED_SEPARATE_DIAGNOSTIC_NOT_CONFIDENCE_SCALED"
        )

    C.scan_finite(output, "model_v010_beta9.output")
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
    "ORDINARY_INPUT_ROLE",
    "AUXILIARY_HITSOUND_INPUT_ROLE",
    "extract_from_path",
    "extract_components",
    "analyze_components",
    "calibration_id",
    "sha256_file_bytes",
]
