"""Opt-in full-profile evidence repair on the beta.6 release envelope.

Beta.1 through beta.6 remain replayable.  This release rebuilds all nine
published axes from versioned, local evidence components while still using
beta.6 as the structural/output-envelope basis.  The total osu!.db star value
is retained as diagnostics only and is never an input to a beta.7 axis.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from typing import Any, Iterable, Mapping

from . import aim_routing_v01 as legacy_aim
from . import contract as C
from . import control_execution_v03 as legacy_control
from . import model as legacy_base
from . import model_decoupled_v01 as decoupled
from . import model_v010_beta2 as beta2
from . import model_v010_beta3 as beta3
from . import model_v010_beta6 as previous
from . import paired_transition_geometry_v01 as geometry
from . import profile_semantics_v01 as semantics
from . import reading_order_v01 as legacy_reading
from . import reading_order_v02 as reading
from . import spatial_axes_v02 as spatial
from . import tapping_axes_v02 as tapping
from .mod_context_v01 import normalize_mods
from .mod_transform_v01 import transform_beatmap
from .public_beta import promote


ALGORITHM_ID = "MAP_DEMAND_FULL_EVIDENCE_V010_BETA7"
MAP_DEMAND_VERSION = "0.10.0-beta.7"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.7"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_ORDER = previous.AXIS_ORDER
EXPECTED_LOCAL_SIGNAL_VERSION = geometry.LOCAL_SIGNAL_VERSION
sha256_file_bytes = previous.sha256_file_bytes
_LOCAL_ROWS_PROVENANCE_TOKEN = object()

RELEASE = {
    "version": MAP_DEMAND_VERSION,
    "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.7 · 九维证据闭环修正版",
    "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "All nine absolute scales remain heuristic and require wider blind validation",
        "Exact simultaneous object order is isolated or abstained rather than interpreted as ordinary standard play",
        "Stacking and full player cursor trajectories are not simulated",
        "Stamina and Endurance are bounded 0-10 traits and are not averaged into star-equivalent summaries",
        "Aspire and other adversarial maps are robustness evidence, not ordinary-distribution calibration data",
    ],
}

_METHODS = {
    "jump_aim": (
        "SECTION_LOCAL_JOINT_DISTANCE_TIME_JUMP_V02",
        "LOCAL_JOINT_DISTANCE_TIME_PHYSICAL_LOG_NO_TOTAL_SR",
    ),
    "flow_aim": (
        "CONTINUOUS_DIRECTIONAL_PATH_FLOW_V03",
        "LOCAL_DIRECTIONAL_PATH_PHYSICAL_LOG_NO_TOTAL_SR_V03",
    ),
    "aim_control": (
        "MINIMUM_PHASE_LOCAL_CONTROL_V04",
        "INDEPENDENT_PHYSICAL_SCALE_NO_TOTAL_SR",
    ),
    "spatial_precision": (
        "MINIMUM_PHASE_TARGET_TOLERANCE_V02",
        "INDEPENDENT_PHYSICAL_SCALE_NO_TOTAL_SR",
    ),
    "raw_speed": (
        "RUN_LOCAL_RAW_SPEED_V03",
        "INDEPENDENT_PHYSICAL_RATE_NO_TOTAL_SR_V03",
    ),
    "stamina": (
        "RUN_LOCAL_STAMINA_V02",
        "BOUNDED_HUMAN_STAMINA_SCALE_0_10_V02",
    ),
    "endurance": (
        "COHERENT_DURATION_ENDURANCE_V02",
        "BOUNDED_HUMAN_ENDURANCE_SCALE_0_10_V02",
    ),
    "finger_control": (
        "WINDOW_BOUND_FINGER_CONTROL_V02",
        "INDEPENDENT_LOCAL_TRANSITION_SCALE_NO_TOTAL_SR",
    ),
    "reading": (
        "LOCAL_ORDER_MEMORY_READING_V03",
        "INDEPENDENT_LOCAL_SCALE_NO_TOTAL_SR",
    ),
}


def _rows_digest(rows: Iterable[dict[str, Any]]) -> str:
    payload = json.dumps(
        list(rows),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class _Beta7LocalRows(list[dict[str, Any]]):
    """List-compatible Local 0.4 rows tied to the beta.7 extraction path."""

    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        super().__init__(rows)
        self.local_signal_version = EXPECTED_LOCAL_SIGNAL_VERSION
        self._provenance_token = _LOCAL_ROWS_PROVENANCE_TOKEN
        self._content_digest = _rows_digest(self)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def extract_from_path(
    path: str,
    requested_mods: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Extract Local 0.4 and materialise the legacy AR=OD decoder rule.

    Materialisation is local to beta.7.  Historical Local Signal artifacts and
    historical model wrappers are not changed.
    """
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src = os.path.join(root, "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    from osu_skill_profiler.features.extractor import FeatureExtractor
    from osu_skill_profiler.parser.normalized import normalize
    from osu_skill_profiler.parser.osu_parser import parse_osu_file
    from osu_skill_profiler.signals.extractor import LocalSignalExtractor

    source_beatmap = parse_osu_file(path)
    source_difficulty = dict(source_beatmap.difficulty)
    extraction_beatmap = source_beatmap
    legacy_ar_fallback = False
    if (
        "ApproachRate" not in source_difficulty
        and _finite(source_difficulty.get("OverallDifficulty")) is not None
    ):
        materialised = dict(source_difficulty)
        materialised["ApproachRate"] = float(materialised["OverallDifficulty"])
        extraction_beatmap = replace(source_beatmap, difficulty=materialised)
        legacy_ar_fallback = True

    mod_context = normalize_mods(requested_mods)
    beatmap, transform_context = transform_beatmap(extraction_beatmap, mod_context)
    transform_context = dict(transform_context)
    if legacy_ar_fallback:
        transform_context["legacy_ar_fallback_applied"] = True
        changes = dict(transform_context.get("difficulty_changes", {}))
        changes["ApproachRate"] = {
            "before": None,
            "after": beatmap.difficulty.get("ApproachRate"),
            "provenance": "LEGACY_AR_FALLBACK_TO_OD",
        }
        transform_context["difficulty_changes"] = changes

    rows = LocalSignalExtractor(EXPECTED_LOCAL_SIGNAL_VERSION).extract(beatmap)[
        "objects"
    ]
    rows = legacy_base.scale_local_difficulty_windows(
        rows,
        transform_context.get("clock_rate", 1.0),
    )
    features = FeatureExtractor(C.FEATURE_VERSION).extract(normalize(beatmap))
    if len(rows) != len(beatmap.hit_objects):
        raise ValueError("beta7 position alignment failed")
    private_rows: list[dict[str, Any]] = []
    for row, obj in zip(rows, beatmap.hit_objects):
        enriched = dict(row)
        enriched["v091.start_x_px"] = float(obj.x)
        enriched["v091.start_y_px"] = float(obj.y)
        private_rows.append(enriched)
    metadata = {
        "path": path,
        "object_count": len(private_rows),
        "feature_count": len(features),
        "local_signal_version": EXPECTED_LOCAL_SIGNAL_VERSION,
        "difficulty": dict(beatmap.difficulty),
        "effective_difficulty": dict(
            transform_context.get("effective_difficulty", beatmap.difficulty)
        ),
        "source_difficulty": source_difficulty,
        "legacy_ar_fallback_applied": legacy_ar_fallback,
        "mod_context": mod_context,
        "mod_transform_context": transform_context,
    }
    return _Beta7LocalRows(private_rows), features, metadata


def _validate_rows(
    local_rows: Iterable[dict[str, Any]],
    source_local_signal_version: str,
) -> list[dict[str, Any]]:
    if source_local_signal_version != EXPECTED_LOCAL_SIGNAL_VERSION:
        raise ValueError(
            "beta7 components require Local Signal "
            f"{EXPECTED_LOCAL_SIGNAL_VERSION}, got {source_local_signal_version!r}"
        )
    if (
        not isinstance(local_rows, _Beta7LocalRows)
        or getattr(local_rows, "_provenance_token", None)
        is not _LOCAL_ROWS_PROVENANCE_TOKEN
        or getattr(local_rows, "local_signal_version", None)
        != EXPECTED_LOCAL_SIGNAL_VERSION
    ):
        raise ValueError("beta7 components require rows returned by beta7.extract_from_path")
    if getattr(local_rows, "_content_digest", None) != _rows_digest(local_rows):
        raise ValueError("beta7 Local Signal rows changed after extraction")
    return list(local_rows)


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Mapping[str, Any] | None = None,
    difficulty: Mapping[str, Any] | None = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
    *,
    source_local_signal_version: str,
) -> tuple[dict[str, Any], list[str]]:
    """Build historical basis components plus independent beta.7 measures."""
    rows = _validate_rows(local_rows, source_local_signal_version)
    component_mod_context = normalize_mods(effective_mods)
    if component_mod_context.get("status") != "NORMALIZED":
        raise ValueError("beta7 components require canonicalizable effective mods")
    component_effective_mods = tuple(
        component_mod_context.get("effective_mods", ())
    )
    components, warnings = decoupled.extract_components(
        rows,
        dict(features) if features is not None else None,
        difficulty=dict(difficulty) if difficulty is not None else None,
        clock_rate=clock_rate,
        effective_mods=component_effective_mods,
    )

    # Reconstruct beta.2-beta.6 basis components without invoking the strict
    # historical geometry builder.  This lets equal-time maps reach beta.7's
    # structured axis-level abstention while keeping old releases unchanged.
    events = beta2._events(rows)  # noqa: SLF001 - historical basis adapter
    components["beta2_measures"] = {
        "stamina": beta2.stamina_measure(events),
        "spatial_precision": beta2.precision_measure(events),
        "finger_control": beta2.finger_measure(events),
    }
    components["beta3_precision"] = beta3.precision_measure(events)
    paired = geometry.build_transition_bundle(
        rows,
        components.get("reading_preempt_median_ms"),
    )
    objects = paired["objects"]
    novelty = geometry.predictability(objects)
    components["beta4_control"] = legacy_control.control_measure(objects, novelty)
    components["beta5_reading"] = legacy_reading.reading_measure(
        objects,
        novelty,
        component_effective_mods,
    )
    components["beta6_aim_routing"] = legacy_aim.aim_routing_measure(
        rows,
        source_local_signal_version=source_local_signal_version,
    )
    components["beta6_source_local_signal_version"] = source_local_signal_version

    components["beta7_spatial_axes"] = spatial.extract_spatial_measures(
        rows,
        resolved_preempt_ms=components.get("reading_preempt_median_ms"),
        effective_mods=component_effective_mods,
    )
    components["beta7_tapping_axes"] = tapping.extract_tapping_measures(rows)
    components["beta7_reading"] = reading.extract_reading_measure(
        paired,
        effective_mods=component_effective_mods,
    )
    components["beta7_source_local_signal_version"] = source_local_signal_version
    components["beta7_effective_mods"] = list(component_effective_mods)
    components["beta7_geometry_summary"] = {
        key: paired[key]
        for key in (
            "schema_version",
            "source_row_count",
            "object_count",
            "transition_count",
            "candidate_transition_count",
            "structural_coverage",
            "simultaneous_group_count",
            "simultaneous_object_count",
            "spinner_count",
            "separator_count",
            "channels",
        )
    }
    return components, list(warnings)


def calibration_id(base_calibration_id: str) -> str:
    return (
        "md010beta7:paired_geometry_1:spatial_3:tapping_3:reading_3:"
        "profile_semantics_2:component_context_1:"
        + previous.calibration_id(base_calibration_id)
    )


def _coverage_eligible_count(raw: Mapping[str, Any]) -> int:
    for key in ("eligible_count", "evidence_count"):
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    coverage = raw.get("coverage")
    if isinstance(coverage, Mapping):
        channels = coverage.get("channels")
        if isinstance(channels, Mapping):
            valid = [
                int(channel.get("valid_count", 0))
                for channel in channels.values()
                if isinstance(channel, Mapping)
                and isinstance(channel.get("valid_count"), int)
            ]
            if valid:
                return max(valid)
    return 0


def _as_axis_measure(raw: Any, axis: str) -> semantics.AxisMeasure:
    if not isinstance(raw, Mapping):
        return semantics.AxisMeasure.insufficient(
            reason="MISSING_BETA7_AXIS_MEASURE",
            missing_required_fields=(f"beta7.{axis}",),
        )
    status = str(raw.get("status") or "INSUFFICIENT").upper()
    value = _finite(raw.get("value"))
    eligible = _coverage_eligible_count(raw)
    signals = dict(raw)
    if status in {"OK", "FULL", "DEGRADED"} and value is not None and value >= 0.0:
        if eligible <= 0:
            return semantics.AxisMeasure.insufficient(
                reason="NO_ELIGIBLE_OBSERVATIONS",
                eligible_count=0,
                signals=signals,
            )
        return semantics.AxisMeasure.observed(
            value,
            eligible_count=eligible,
            signals=signals,
        )
    missing = raw.get("missing_required_fields")
    missing_fields = tuple(
        str(item)
        for item in missing
        if str(item)
    ) if isinstance(missing, (list, tuple)) else ()
    return semantics.AxisMeasure.insufficient(
        reason=str(raw.get("reason") or status or "INSUFFICIENT_EVIDENCE"),
        eligible_count=max(0, eligible),
        missing_required_fields=missing_fields,
        signals=signals,
    )


def _replace_beta7_axis(
    output: dict[str, Any],
    axis: str,
    raw_measure: Mapping[str, Any],
) -> None:
    method, scale_method = _METHODS[axis]
    measure = _as_axis_measure(raw_measure, axis)
    item = semantics.apply_axis_measure(
        {},
        measure,
        method=method,
        scale_method=scale_method,
        component=f"beta7_{axis}",
        evidence_tag="PUBLIC_BETA7_INDEPENDENT_EVIDENCE",
        confidence="LOW",
    )
    item["unit"] = (
        "bounded_0_10"
        if axis in semantics.BOUNDED_AUXILIARY_AXES
        else "star_equivalent"
    )
    item["combination_policy"] = "SAME_SECTION_MECHANISM_EVIDENCE_ONLY"
    item["signals"] = dict(raw_measure.get("signals", {}))
    item["evidence_quality"] = str(raw_measure.get("status") or "INSUFFICIENT")
    item["warnings"] = []
    if item["status"] != semantics.AXIS_EMITTED:
        item["warnings"].append("BETA7_INSUFFICIENT_EVIDENCE")
        output["warnings"].append(
            {
                "code": "BETA7_AXIS_INSUFFICIENT_EVIDENCE",
                "axis": axis,
                "message": measure.evidence.reason,
            }
        )
    elif item["evidence_quality"] == "DEGRADED":
        item["warnings"].append("BETA7_DEGRADED_COVERAGE")
        output["warnings"].append(
            {
                "code": "BETA7_AXIS_DEGRADED_COVERAGE",
                "axis": axis,
                "message": "Axis emitted from at least 80% but less than 95% coverage",
            }
        )
    output["axes"][axis] = item


def analyze_components(**kwargs: Any) -> dict[str, Any]:
    components = kwargs.get("components")
    if not isinstance(components, Mapping):
        raise ValueError("beta7 requires a components mapping")
    source_version = components.get("beta7_source_local_signal_version")
    if source_version != EXPECTED_LOCAL_SIGNAL_VERSION:
        raise ValueError(
            "beta7 component provenance mismatch: "
            f"expected {EXPECTED_LOCAL_SIGNAL_VERSION}, got {source_version!r}"
        )
    component_mods_raw = components.get("beta7_effective_mods")
    if not isinstance(component_mods_raw, (list, tuple)):
        raise ValueError("beta7 requires beta7_effective_mods provenance")
    component_mod_context = normalize_mods(component_mods_raw)
    if component_mod_context.get("status") != "NORMALIZED":
        raise ValueError("beta7 component mod provenance is invalid")
    component_mods = tuple(component_mod_context.get("effective_mods", ()))

    requested_mod_context = normalize_mods(kwargs.get("requested_mods", ()))
    if requested_mod_context.get("status") == "NORMALIZED":
        requested_effective = tuple(
            requested_mod_context.get("effective_mods", ())
        )
        if component_mods != requested_effective:
            raise ValueError(
                "beta7 component mod provenance mismatch: "
                f"components={component_mods!r}, requested={requested_effective!r}"
            )

    applied_context = kwargs.get("applied_mod_context")
    if isinstance(applied_context, Mapping) and "effective_mods" in applied_context:
        applied_mod_context = normalize_mods(
            applied_context.get("effective_mods", ())
        )
        if applied_mod_context.get("status") != "NORMALIZED":
            raise ValueError("beta7 applied mod provenance is invalid")
        applied_effective = tuple(
            applied_mod_context.get("effective_mods", ())
        )
        if component_mods != applied_effective:
            raise ValueError(
                "beta7 component/applied mod provenance mismatch: "
                f"components={component_mods!r}, applied={applied_effective!r}"
            )
    spatial_measures = components.get("beta7_spatial_axes")
    tapping_measures = components.get("beta7_tapping_axes")
    reading_measure = components.get("beta7_reading")
    if not isinstance(spatial_measures, Mapping):
        raise ValueError("beta7 requires beta7_spatial_axes")
    if not isinstance(tapping_measures, Mapping):
        raise ValueError("beta7 requires beta7_tapping_axes")
    if not isinstance(reading_measure, Mapping):
        raise ValueError("beta7 requires beta7_reading")

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
        for axis in ("jump_aim", "flow_aim", "aim_control", "spatial_precision"):
            _replace_beta7_axis(output, axis, spatial_measures.get(axis, {}))
        for axis in ("raw_speed", "stamina", "endurance", "finger_control"):
            _replace_beta7_axis(output, axis, tapping_measures.get(axis, {}))
        _replace_beta7_axis(output, "reading", reading_measure)

        output["summaries"] = semantics.derive_profile_summaries(output["axes"])
        output["archetype"] = semantics.classify_star_archetype(output["axes"])
        output["diagnostics"]["beta7_spatial_axes"] = spatial_measures
        output["diagnostics"]["beta7_tapping_axes"] = tapping_measures
        output["diagnostics"]["beta7_reading"] = reading_measure
        output["diagnostics"]["beta7_geometry"] = components.get(
            "beta7_geometry_summary"
        )
        output["diagnostics"]["beta7_total_sr_role"] = (
            "DIAGNOSTIC_ONLY_NOT_AN_AXIS_INPUT"
        )
        output["diagnostics"]["beta7_axis_dependencies"] = {
            axis: ["BEATMAP_LOCAL_EVIDENCE_ONLY"]
            for axis in semantics.ALL_PROFILE_AXES
        }
        output["diagnostics"]["beta7_summary_unit_policy"] = (
            "NO_MIXED_STAR_AND_BOUNDED_OVERALL_SCALAR"
        )
        output["diagnostics"]["beta7_component_effective_mods"] = list(
            component_mods
        )

    C.scan_finite(output, "model_v010_beta7.output")
    return output


__all__ = [
    "ALGORITHM_ID",
    "MAP_DEMAND_VERSION",
    "SCHEMA_VERSION",
    "AXIS_SCHEMA_VERSION",
    "AXIS_ORDER",
    "RELEASE",
    "EXPECTED_LOCAL_SIGNAL_VERSION",
    "extract_from_path",
    "extract_components",
    "analyze_components",
    "calibration_id",
    "sha256_file_bytes",
]
