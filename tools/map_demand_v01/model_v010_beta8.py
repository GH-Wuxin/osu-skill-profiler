"""Opt-in beta.8 support-frontier release.

Beta.7 remains replayable.  Beta.8 separates Jump Aim and Raw Speed physical
peaks from their axis-specific public support frontiers.  It also closes
specific zero-displacement and double-tap loopholes in Precision, Finger
Control, and Stamina.  The remaining axes are inherited unchanged and are
explicitly marked as legacy local-axis contracts rather than being given
invented frontiers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from . import contract as C
from . import model_v010_beta7 as previous
from . import profile_semantics_v01 as legacy_semantics
from . import profile_semantics_v02 as semantics
from . import spatial_axes_v03 as spatial
from . import tapping_axes_v03 as tapping
from .public_beta import promote


ALGORITHM_ID = "MAP_DEMAND_SUPPORT_FRONTIER_V010_BETA8"
MAP_DEMAND_VERSION = "0.10.0-beta.8"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.8"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_CONTRACT_VERSION = semantics.AXIS_CONTRACT_VERSION
AXIS_ORDER = previous.AXIS_ORDER
EXPECTED_LOCAL_SIGNAL_VERSION = previous.EXPECTED_LOCAL_SIGNAL_VERSION
sha256_file_bytes = previous.sha256_file_bytes

SUPPORT_AWARE_AXES = ("jump_aim", "raw_speed")
REBUILT_LOCAL_AXES = ("spatial_precision", "stamina", "finger_control")
INHERITED_AXIS_CONTRACTS = {
    "flow_aim": "beta7_spatial_axes_v02_local_value",
    "aim_control": "beta7_spatial_axes_v02_local_value",
    "endurance": "beta7_tapping_axes_v02_bounded_value",
    "reading": "beta7_reading_order_v02_local_value",
}
REBUILT_LOCAL_AXIS_CONTRACTS = {
    "spatial_precision": "beta8_spatial_axes_v03_nonzero_landing_value",
    "stamina": "beta8_tapping_axes_v03_double_tap_aware_bounded_value",
    "finger_control": "beta8_tapping_axes_v03_double_tap_aware_local_value",
}

ORDINARY_INPUT_ROLE = "ORDINARY_BEATMAP_LAYER"
AUXILIARY_HITSOUND_INPUT_ROLE = "AUXILIARY_HITSOUND_LAYER"
_AMBIGUOUS_HS_INPUT_ROLE = "AMBIGUOUS_HS_LAYER_CANDIDATE"


class _Beta8Features(dict[str, Any]):
    """Dict-compatible feature vector carrying non-numeric routing metadata."""

    def __init__(self, features: Mapping[str, Any], input_role_hint: str) -> None:
        super().__init__(features)
        self.input_role_hint = input_role_hint

RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.8 · 峰值与支持前沿分离实验版",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Jump Aim selects establishment-or-recurrence; Raw Speed selects establishment-or-sustain and excludes separated recurrence from its public value",
        "Precision requires non-zero landing displacement; Finger Control and Stamina discount feasible stacked double-taps",
        "Absolute scales remain heuristic and require wider blind validation",
        "Physical peak is observed map demand, not a verified player capability",
        "Exact simultaneous order and concurrent active-slider 2B transitions are isolated or abstained rather than interpreted as single-cursor standard play",
        "Aspire and adversarial maps are robustness evidence, never ordinary-scale calibration data",
        "Explicit Hitsound auxiliary difficulties are flagged for downstream cohort exclusion rather than silently mixed into ordinary calibration",
    ],
}


def _input_role_from_path(path: str) -> str:
    """Identify explicit auxiliary difficulty layers without inferring skill."""

    stem = Path(path).stem.casefold()
    version = stem.rsplit("[", 1)[-1].removesuffix("]").strip()
    if "hitsound" in version:
        return AUXILIARY_HITSOUND_INPUT_ROLE
    if version == "hs":
        return _AMBIGUOUS_HS_INPUT_ROLE
    return ORDINARY_INPUT_ROLE


def extract_from_path(
    path: str,
    requested_mods: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Preserve beta.7 extraction and attach an explicit input-role marker."""

    rows, features, metadata = previous.extract_from_path(path, requested_mods)
    role = _input_role_from_path(path)
    tagged_features = _Beta8Features(features, role)
    tagged_metadata = dict(metadata)
    tagged_metadata["beta8_input_role_hint"] = role
    return rows, tagged_features, tagged_metadata


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Mapping[str, Any] | None = None,
    difficulty: Mapping[str, Any] | None = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
    *,
    source_local_signal_version: str,
) -> tuple[dict[str, Any], list[str]]:
    """Build beta.7 replay components plus beta.8 support-aware measures."""

    basis_features = dict(features) if features is not None else None
    tagged_role = getattr(features, "input_role_hint", None)
    input_role_hint = (
        str(tagged_role)
        if tagged_role
        in {
            ORDINARY_INPUT_ROLE,
            AUXILIARY_HITSOUND_INPUT_ROLE,
            _AMBIGUOUS_HS_INPUT_ROLE,
        }
        else ORDINARY_INPUT_ROLE
    )
    components, warnings = previous.extract_components(
        local_rows,
        basis_features,
        difficulty,
        clock_rate,
        effective_mods,
        source_local_signal_version=source_local_signal_version,
    )
    # beta.7 already validated the private Local 0.4 row provenance and digest.
    rows = list(local_rows)
    component_mods = tuple(components.get("beta7_effective_mods", ()))
    components["beta8_spatial_axes"] = spatial.extract_spatial_measures(
        rows,
        resolved_preempt_ms=components.get("reading_preempt_median_ms"),
        effective_mods=component_mods,
    )
    components["beta8_tapping_axes"] = tapping.extract_tapping_measures(rows)
    components["beta8_source_local_signal_version"] = source_local_signal_version
    components["beta8_effective_mods"] = list(component_mods)
    object_types = [str(row.get("ls.object_type") or "") for row in rows]
    start_positions = {
        (row.get("v091.start_x_px"), row.get("v091.start_y_px"))
        for row in rows
    }
    ambiguous_hs_corroborated = (
        input_role_hint == _AMBIGUOUS_HS_INPUT_ROLE
        and bool(object_types)
        and all(kind == "circle" for kind in object_types)
        and len(start_positions) == 1
    )
    input_role = (
        AUXILIARY_HITSOUND_INPUT_ROLE
        if input_role_hint == AUXILIARY_HITSOUND_INPUT_ROLE
        or ambiguous_hs_corroborated
        else ORDINARY_INPUT_ROLE
    )
    components["beta8_input_role"] = {
        "role": input_role,
        "source": (
            "EXPLICIT_HITSOUND_DIFFICULTY_VERSION_TOKEN"
            if input_role_hint == AUXILIARY_HITSOUND_INPUT_ROLE
            else "HS_TOKEN_WITH_SINGLE_POSITION_ALL_CIRCLE_CORROBORATION"
            if ambiguous_hs_corroborated
            else "NO_AUXILIARY_LAYER_EVIDENCE"
        ),
        "profile_routing": (
            "EXCLUDE_FROM_ORDINARY_CALIBRATION"
            if input_role == AUXILIARY_HITSOUND_INPUT_ROLE
            else "ORDINARY_ELIGIBLE"
        ),
        "object_count": len(object_types),
        "circle_count": sum(kind == "circle" for kind in object_types),
        "slider_count": sum(kind == "slider" for kind in object_types),
        "spinner_count": sum(kind == "spinner" for kind in object_types),
        "unique_start_position_count": len(start_positions),
    }
    components["beta8_support_frontier_schema_version"] = (
        components["beta8_spatial_axes"]["jump_aim"].get(
            "support_frontier_schema_version"
        )
    )
    return components, list(warnings)


def calibration_id(base_calibration_id: str) -> str:
    return (
        "md010beta8:support_frontier_1:jump_5:raw_4:precision_3:"
        "stamina_3:finger_3:input_routing_1:profile_semantics_4:"
        "public_frontier_selection_1:mixed_axis_contract_2:"
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
        component=f"beta8_{axis}",
        evidence_tag="PUBLIC_BETA8_SUPPORT_FRONTIER_EVIDENCE",
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
        item["warnings"].append("BETA8_INSUFFICIENT_SUPPORT_EVIDENCE")
        output["warnings"].append(
            {
                "code": "BETA8_AXIS_INSUFFICIENT_SUPPORT_EVIDENCE",
                "axis": axis,
                "message": str(
                    raw_measure.get("reason") or "insufficient support evidence"
                ),
            }
        )
    elif item["evidence_quality"] == "DEGRADED":
        item["warnings"].append("BETA8_DEGRADED_COVERAGE")
    output["axes"][axis] = item


def _replace_local_axis(
    output: dict[str, Any],
    axis: str,
    raw_measure: Mapping[str, Any],
    *,
    method: str,
) -> None:
    """Publish a rebuilt local axis without inventing support frontiers."""

    measure = previous._as_axis_measure(raw_measure, axis)  # noqa: SLF001
    item = legacy_semantics.apply_axis_measure(
        {},
        measure,
        method=method,
        scale_method=str(raw_measure.get("scale") or "BETA8_LOCAL_SCALE"),
        component=f"beta8_{axis}",
        evidence_tag="PUBLIC_BETA8_LOCAL_MECHANISM_EVIDENCE",
        confidence="LOW",
    )
    item["unit"] = (
        "bounded_0_10"
        if axis in semantics.BOUNDED_AUXILIARY_AXES
        else "star_equivalent"
    )
    item["combination_policy"] = "SAME_SECTION_MECHANISM_EVIDENCE_ONLY"
    item["signals"] = dict(raw_measure.get("signals", {}))
    item["evidence_quality"] = str(
        raw_measure.get("status") or "INSUFFICIENT"
    )
    item["warnings"] = []
    if item["status"] != semantics.AXIS_EMITTED:
        item["warnings"].append("BETA8_INSUFFICIENT_LOCAL_AXIS_EVIDENCE")
        output["warnings"].append(
            {
                "code": "BETA8_AXIS_INSUFFICIENT_LOCAL_EVIDENCE",
                "axis": axis,
                "message": measure.evidence.reason,
            }
        )
    elif item["evidence_quality"] == "DEGRADED":
        item["warnings"].append("BETA8_DEGRADED_COVERAGE")
    item["axis_contract_version"] = REBUILT_LOCAL_AXIS_CONTRACTS[axis]
    item["stars"] = item.get("demand_star_equivalent")
    item["public_value_semantics"] = "BETA8_LOCAL_MECHANISM_AXIS_VALUE"
    item["support_frontiers_available"] = False
    output["axes"][axis] = item


def analyze_components(**kwargs: Any) -> dict[str, Any]:
    components = kwargs.get("components")
    if not isinstance(components, Mapping):
        raise ValueError("beta8 requires a components mapping")
    if (
        components.get("beta8_source_local_signal_version")
        != EXPECTED_LOCAL_SIGNAL_VERSION
    ):
        raise ValueError("beta8 component Local Signal provenance mismatch")
    spatial_measures = components.get("beta8_spatial_axes")
    tapping_measures = components.get("beta8_tapping_axes")
    input_role = components.get("beta8_input_role")
    if not isinstance(spatial_measures, Mapping):
        raise ValueError("beta8 requires beta8_spatial_axes")
    if not isinstance(tapping_measures, Mapping):
        raise ValueError("beta8 requires beta8_tapping_axes")
    if not isinstance(input_role, Mapping):
        raise ValueError("beta8 requires beta8_input_role")

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
        jump = spatial_measures.get("jump_aim")
        raw = tapping_measures.get("raw_speed")
        if not isinstance(jump, Mapping) or not isinstance(raw, Mapping):
            raise ValueError("beta8 support-aware measures are missing")
        alternative_mechanism = (
            jump.get("signals", {}).get("alternative_mechanism")
            if isinstance(jump.get("signals"), Mapping)
            else None
        )
        if isinstance(alternative_mechanism, Mapping) and int(
            alternative_mechanism.get("excluded_transition_count", 0) or 0
        ) > 0:
            output["warnings"].append(
                {
                    "code": "BETA8_CONCURRENT_ACTIVE_SLIDER_ALTERNATIVE_MECHANISM",
                    "axis": "jump_aim",
                    "message": (
                        "Concurrent active-slider transitions were excluded "
                        "from the single-cursor Jump construct"
                    ),
                    "excluded_transition_count": int(
                        alternative_mechanism.get(
                            "excluded_transition_count", 0
                        )
                        or 0
                    ),
                    "max_concurrent_active_sliders": int(
                        alternative_mechanism.get(
                            "max_concurrent_active_sliders", 0
                        )
                        or 0
                    ),
                }
            )
        if isinstance(alternative_mechanism, Mapping) and int(
            alternative_mechanism.get(
                "invalid_single_cursor_geometry_count", 0
            )
            or 0
        ) > 0:
            output["warnings"].append(
                {
                    "code": "BETA8_INVALID_SINGLE_CURSOR_GEOMETRY_EXCLUDED",
                    "axis": "jump_aim",
                    "message": (
                        "Implausible minimum-phase slider geometry was "
                        "excluded from the single-cursor Jump construct"
                    ),
                    "excluded_transition_count": int(
                        alternative_mechanism.get(
                            "invalid_single_cursor_geometry_count", 0
                        )
                        or 0
                    ),
                }
            )
        _replace_supported_axis(
            output,
            "jump_aim",
            jump,
            method="JOINT_DISTANCE_TIME_SUPPORT_FRONTIER_JUMP_V03",
            scale_method=spatial.JUMP_SCALE,
        )
        _replace_supported_axis(
            output,
            "raw_speed",
            raw,
            method="EXECUTION_RATE_SUPPORT_FRONTIER_RAW_V04",
            scale_method=tapping.RAW_SPEED_SCALE,
        )
        _replace_local_axis(
            output,
            "spatial_precision",
            spatial_measures.get("spatial_precision", {}),
            method="MINIMUM_PHASE_NONZERO_TARGET_TOLERANCE_V03",
        )
        _replace_local_axis(
            output,
            "stamina",
            tapping_measures.get("stamina", {}),
            method="DOUBLE_TAP_AWARE_RUN_LOCAL_STAMINA_V03",
        )
        _replace_local_axis(
            output,
            "finger_control",
            tapping_measures.get("finger_control", {}),
            method="DOUBLE_TAP_AWARE_WINDOW_FINGER_CONTROL_V03",
        )
        for axis, source_contract in INHERITED_AXIS_CONTRACTS.items():
            output["axes"][axis] = semantics.annotate_legacy_axis(
                output["axes"][axis],
                source_contract=source_contract,
            )

        output["summaries"] = semantics.derive_profile_summaries(output["axes"])
        output["archetype"] = semantics.classify_star_archetype(output["axes"])
        output["diagnostics"]["beta8_spatial_axes"] = spatial_measures
        output["diagnostics"]["beta8_tapping_axes"] = tapping_measures
        output["diagnostics"]["beta8_support_aware_axes"] = list(
            SUPPORT_AWARE_AXES
        )
        output["diagnostics"]["beta8_inherited_axis_contracts"] = dict(
            INHERITED_AXIS_CONTRACTS
        )
        output["diagnostics"]["beta8_rebuilt_local_axis_contracts"] = dict(
            REBUILT_LOCAL_AXIS_CONTRACTS
        )
        output["diagnostics"]["beta8_input_role"] = dict(input_role)
        if input_role.get("role") == AUXILIARY_HITSOUND_INPUT_ROLE:
            output["warnings"].append(
                {
                    "code": "BETA8_AUXILIARY_HITSOUND_LAYER",
                    "message": (
                        "Explicit Hitsound auxiliary difficulty: keep its "
                        "mechanic evidence separate from ordinary calibration"
                    ),
                    "profile_routing": "EXCLUDE_FROM_ORDINARY_CALIBRATION",
                }
            )
        output["diagnostics"]["beta8_public_star_policy"] = (
            "JUMP_USES_MAX_ESTABLISHMENT_RECURRENCE;"
            "RAW_USES_MAX_ESTABLISHMENT_SUSTAIN_WITHOUT_RECURRENCE;"
            "PRECISION_FINGER_STAMINA_USE_REBUILT_LOCAL_CONTRACTS;"
            "INHERITED_AXES_RETAIN_EXPLICIT_BETA7_VALUE_CONTRACT"
        )
        output["diagnostics"]["beta8_physical_peak_policy"] = (
            "UNBOUNDED_SEPARATE_DIAGNOSTIC_NOT_CONFIDENCE_SCALED"
        )
        output["diagnostics"]["beta8_total_sr_role"] = (
            "DIAGNOSTIC_ONLY_NOT_AN_AXIS_INPUT"
        )

    C.scan_finite(output, "model_v010_beta8.output")
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
