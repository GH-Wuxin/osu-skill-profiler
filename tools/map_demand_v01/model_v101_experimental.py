"""Opt-in Flow and Aim Control experiment on the frozen v100 envelope.

Historical extraction and seven other axis payloads remain unchanged.
Revision .11 uses actual turn sharpness without discounting repeated turns.
Flow and Control target-size/deadline responses are unchanged; absolute calibration remains provisional.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import contract as C
from . import flow_execution_v02 as flow
from . import control_vector_v01 as control
from . import model_v010_beta7 as beta7
from . import model_v100 as previous
from . import profile_semantics_v01 as legacy_semantics
from . import profile_semantics_v02 as semantics
from .public_beta import promote

ALGORITHM_ID = "MAP_DEMAND_V101_EXPERIMENTAL"
MAP_DEMAND_VERSION = "1.0.1-experimental.11"
SCHEMA_VERSION = "map_demand_v1.0.1-experimental.11"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_CONTRACT_VERSION = previous.AXIS_CONTRACT_VERSION
AXIS_ORDER = previous.AXIS_ORDER
EXPECTED_LOCAL_SIGNAL_VERSION = previous.EXPECTED_LOCAL_SIGNAL_VERSION
SUPPORT_AWARE_AXES = previous.SUPPORT_AWARE_AXES
REBUILT_LOCAL_AXES = previous.REBUILT_LOCAL_AXES
INHERITED_AXIS_CONTRACTS = {
    axis: value for axis, value in previous.INHERITED_AXIS_CONTRACTS.items()
    if axis not in {"flow_aim", "aim_control"}
}
REBUILT_LOCAL_AXIS_CONTRACTS = {
    **previous.REBUILT_LOCAL_AXIS_CONTRACTS,
    "flow_aim": "v101_experimental_local_and_sustained_flow_v05",
    "aim_control": "v101_experimental_sharp_turn_control_vector_v05",
}
CHANGED_FROM_PREVIOUS = frozenset({"flow_aim", "aim_control"})
ORDINARY_INPUT_ROLE = previous.ORDINARY_INPUT_ROLE
AUXILIARY_HITSOUND_INPUT_ROLE = previous.AUXILIARY_HITSOUND_INPUT_ROLE
extract_from_path = previous.extract_from_path
sha256_file_bytes = previous.sha256_file_bytes

RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "EXPERIMENTAL",
    "label": "1.0.1-experimental.11 · Aim Control 锐角与频率候选",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Opt-in experiment; absolute Flow star-equivalent scale still needs independent human validation",
        "Seven axes other than Flow and Aim Control are frozen v100 payloads and retain their existing limitations",
        "Aim Control adds verified circle velocity vectors; slider direction remains uncovered and is explicitly reported",
        "Aim Control measures the hardest locally supported execution demand, not typical map demand or FC probability",
        "Control uses whole-transition scalar averages; slider-internal velocity changes remain uncovered",
        "Per-axis experimental star scales do not establish a common human-calibrated scale",
        "Flow uses lazy execution geometry, not an observed player cursor trajectory",
        "Slider-internal tangent curvature and client stacking are not reconstructed",
        "Local turn adjustment and circle-only spatial reentry are uncalibrated hypotheses, not observed coordination errors",
        "Spatial reentry uses short local phrase contexts and bounded bridge interaction; its absolute weight requires independent validation",
        "Short execution peaks and sustained evidence are reported separately; this is not a whole-map average",
        "Sustained Flow grows with credited movement time; its growth, ownership and recovery parameters remain uncalibrated",
        "The shared cross-axis human difficulty scale remains unresolved",
        "Spacing/time relief from repeated direction loss is an uncalibrated continuity hypothesis",
    ],
}


def calibration_id(base_calibration_id: str) -> str:
    return "md101exp11:local_sustained_flow_v052_gain2:control_sharp_turn_v05:" + previous.calibration_id(base_calibration_id)


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Mapping[str, Any] | None = None,
    difficulty: Mapping[str, Any] | None = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
    *,
    source_local_signal_version: str,
) -> tuple[dict[str, Any], list[str]]:
    # The inherited call validates private extraction provenance and its digest.
    # Do not re-wrap arbitrary rows or change the frozen rows in place.
    components, warnings = previous.extract_components(
        local_rows, features, difficulty, clock_rate, effective_mods,
        source_local_signal_version=source_local_signal_version,
    )
    mods = tuple(components["beta92_effective_mods"])
    components["v101_flow_measure"] = flow.extract_flow_measure(
        local_rows, mods,
        circle_size=difficulty.get("CircleSize") if isinstance(difficulty, Mapping) else None,
        resolved_preempt_ms=components.get("reading_preempt_median_ms"),
    )
    components["v101_source_local_signal_version"] = source_local_signal_version
    components["v101_flow_schema_version"] = flow.SCHEMA_VERSION
    components["v101_control_measure"] = control.extract_control_measure(
        local_rows, mods, resolved_preempt_ms=components.get("reading_preempt_median_ms"),
    )
    components["v101_control_schema_version"] = control.SCHEMA_VERSION
    return components, list(warnings)


def analyze_components(**kwargs: Any) -> dict[str, Any]:
    components = kwargs.get("components")
    if not isinstance(components, Mapping):
        raise ValueError("v101 experimental requires a components mapping")
    if components.get("v101_source_local_signal_version") != EXPECTED_LOCAL_SIGNAL_VERSION:
        raise ValueError("v101 experimental component Local Signal provenance mismatch")
    if components.get("v101_flow_schema_version") != flow.SCHEMA_VERSION:
        raise ValueError("v101 experimental Flow component schema mismatch")
    raw = components.get("v101_flow_measure")
    if not isinstance(raw, Mapping):
        raise ValueError("v101 experimental Flow measure is missing")
    if components.get("v101_control_schema_version") != control.SCHEMA_VERSION:
        raise ValueError("v101 experimental Control component schema mismatch")
    control_raw = components.get("v101_control_measure")
    if not isinstance(control_raw, Mapping):
        raise ValueError("v101 experimental Control measure is missing")

    output = previous.analyze_components(**kwargs)
    promote(
        output, algorithm_id=ALGORITHM_ID,
        map_demand_version=MAP_DEMAND_VERSION,
        calibration_id=calibration_id(str(kwargs["calibration"].get("calibration_id", ""))),
        schema_version=SCHEMA_VERSION, release=RELEASE,
    )
    if output.get("status") == "OK":
        measure = beta7._as_axis_measure(raw, "flow_aim")
        item = legacy_semantics.apply_axis_measure(
            {}, measure,
            method="LOCAL_OR_SUSTAINED_FLOW_WITH_CIRCLE_REENTRY_V05",
            scale_method=flow.SCALE,
            component="v101_flow_execution",
            evidence_tag="EXPERIMENTAL_FLOW_EXECUTION_V02",
            confidence="LOW",
        )
        item.update(
            unit="star_equivalent",
            combination_policy="MAX_LOCAL_AND_SUSTAINED_OWNED_FLOW_LOAD",
            signals=dict(raw.get("signals", {})),
            evidence_quality=str(raw.get("status") or "INSUFFICIENT"),
            axis_contract_version=REBUILT_LOCAL_AXIS_CONTRACTS["flow_aim"],
            public_value_semantics="EXPERIMENTAL_LOCAL_OR_SUSTAINED_FLOW_EXECUTION",
            support_frontiers_available=False,
            warnings=[],
        )
        item["stars"] = item.get("demand_star_equivalent")
        # Old Flow warnings describe the superseded measure; retain other axes.
        output["warnings"] = [
            warning for warning in output.get("warnings", [])
            if not isinstance(warning, Mapping) or warning.get("axis") != "flow_aim"
        ]
        if item["status"] != semantics.AXIS_EMITTED:
            item["warnings"].append("V101_INSUFFICIENT_FLOW_EVIDENCE")
            output["warnings"].append({
                "code": "V101_FLOW_INSUFFICIENT_EVIDENCE", "axis": "flow_aim",
                "message": measure.evidence.reason,
            })
        elif item["evidence_quality"] == "DEGRADED":
            item["warnings"].append("V101_DEGRADED_FLOW_COVERAGE")
        output["axes"]["flow_aim"] = item
        control_measure = beta7._as_axis_measure(control_raw, "aim_control")
        control_item = legacy_semantics.apply_axis_measure(
            {}, control_measure, method="SHARP_TURN_CONTROL_VECTOR_WITH_LOCAL_LAYER_SUPPORT_V05",
            scale_method=control.SCALE, component="v101_control_vector",
            evidence_tag="EXPERIMENTAL_CONTROL_VECTOR_V05", confidence="LOW",
        )
        control_item.update(
            unit="star_equivalent", combination_policy="SAME_LOCAL_EFFORT_LAYER_SUPPORT",
            signals=dict(control_raw.get("signals", {})),
            evidence_quality=str(control_raw.get("status") or "INSUFFICIENT"),
            axis_contract_version=REBUILT_LOCAL_AXIS_CONTRACTS["aim_control"],
            public_value_semantics="EXPERIMENTAL_ESTABLISHED_LOCAL_CONTROL_EXECUTION",
            support_frontiers_available=False, warnings=[],
        )
        control_item["stars"] = control_item.get("demand_star_equivalent")
        output["warnings"] = [warning for warning in output.get("warnings", [])
                              if not isinstance(warning, Mapping) or warning.get("axis") != "aim_control"]
        if control_item["status"] != semantics.AXIS_EMITTED:
            code = "V101_INSUFFICIENT_CONTROL_EVIDENCE"
        elif control_item["evidence_quality"] == "DEGRADED":
            code = "V101_PARTIAL_CONTROL_MECHANISMS"
        else:
            code = None
        if code:
            control_item["warnings"].append(code)
            output["warnings"].append({"code": code, "axis": "aim_control", "message": control_raw["reason"]})
        output["axes"]["aim_control"] = control_item
        output["summaries"] = semantics.derive_profile_summaries(output["axes"])
        output["archetype"] = semantics.classify_star_archetype(output["axes"])
        output["diagnostics"]["v101_flow_execution"] = raw
        output["diagnostics"]["v101_control_vector"] = control_raw
        output["diagnostics"]["v101_changed_axes"] = sorted(CHANGED_FROM_PREVIOUS)
    C.scan_finite(output, "model_v101_experimental.output")
    return output
