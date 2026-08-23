"""Map Demand V0.8: split intensity Stamina from whole-map Endurance."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Optional

from . import contract as C
from . import model as v06
from . import model_v07 as v07
from .archetype_v08 import AXIS_ORDER, classify_axes

ALGORITHM_ID = "MAP_DEMAND_ATOMIC_V06"
MAP_DEMAND_VERSION = "0.8.0"
SCHEMA_VERSION = "map_demand_v0.8.0"
AXIS_SCHEMA_VERSION = "atomic_v0.8.0"
MECHANISM_SPEC = (
    "MAP_DEMAND_ATOMIC_V06:base=MAP_DEMAND_ATOMIC_V05;"
    "taxonomy=split_stamina_intensity_from_whole_map_endurance;"
    "stamina=non_duration_physical_intensity_times_short_sustain_saturating_at_20s;"
    "endurance=duration_volume_difficulty_gate_dense_coverage_bounded_0_10"
)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def calibration_id(base_calibration_id: str) -> str:
    payload = json.dumps(
        {"base_calibration_id": base_calibration_id, "mechanism_spec": MECHANISM_SPEC},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"mdoverlay_v08:{digest}"


def extract_from_path(
    path: str, requested_mods: Iterable[str] = ()
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    return v07.extract_from_path(path, requested_mods=requested_mods)


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Optional[dict[str, Any]] = None,
    difficulty: Optional[dict[str, Any]] = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    return v07.extract_components(
        local_rows,
        features,
        difficulty=difficulty,
        clock_rate=clock_rate,
        effective_mods=effective_mods,
    )


def sha256_file_bytes(data: bytes) -> str:
    return v07.sha256_file_bytes(data)


def _axis_stars(axes: dict[str, Any], axis: str) -> float | None:
    item = axes.get(axis)
    if not isinstance(item, dict) or item.get("status") != "EMITTED":
        return None
    return _finite(item.get("demand_star_equivalent"))


def _physical_environment(axes: dict[str, Any]) -> float | None:
    values = [
        value
        for axis in (
            "jump_aim",
            "flow_aim",
            "aim_control",
            "spatial_precision",
            "raw_speed",
            "stamina",
        )
        if (value := _axis_stars(axes, axis)) is not None
    ]
    if len(values) < 2:
        return None
    values.sort(reverse=True)
    return (values[0] + values[1]) / 2.0


def _bounded_stamina(axes: dict[str, Any], components: dict[str, Any]) -> None:
    item = axes.get("stamina")
    base = _axis_stars(axes, "stamina")
    candidates = [
        value
        for axis in (
            "jump_aim",
            "flow_aim",
            "aim_control",
            "spatial_precision",
            "raw_speed",
            "finger_control",
        )
        if (value := _axis_stars(axes, axis)) is not None
    ]
    burst_125 = _finite(components.get("v07_burst_longest_duration_ms_125ms"))
    burst_250 = _finite(components.get("v07_burst_longest_duration_ms_250ms"))
    density = _finite(components.get("v07_density_objects_per_s"))
    if (
        not isinstance(item, dict)
        or base is None
        or len(candidates) < 2
        or burst_125 is None
        or burst_250 is None
        or density is None
    ):
        return
    candidates.sort(reverse=True)
    intensity = (candidates[0] + candidates[1]) / 2.0
    burst_s = max(float(burst_125), 0.45 * float(burst_250)) / 1000.0
    short_sustain = _clamp(math.log1p(max(0.0, burst_s)) / math.log1p(20.0), 0.0, 1.0)
    sustain_multiplier = 0.70 + 0.30 * short_sustain
    density_gate = _clamp((float(density) - 3.0) / 7.0, 0.0, 1.0)
    adjusted = min(10.0, intensity * sustain_multiplier + 0.50 * density_gate)
    item["demand_star_equivalent"] = adjusted
    item["score"] = adjusted / 10.0
    item["percentile_rank"] = None
    item["scale_method"] = "BOUNDED_HUMAN_STAMINA_SCALE_0_10_V08"
    item["method"] = "HEURISTIC_SHORT_HORIZON_STAMINA_V08"
    item["combination_policy"] = "PHYSICAL_INTENSITY_X_SHORT_SUSTAIN_V08"
    item.setdefault("evidence", []).append(
        {
            "component": "short_horizon_stamina",
            "legacy_stamina_stars_diagnostic_only": base,
            "physical_intensity_stars": intensity,
            "burst_duration_proxy_s": burst_s,
            "short_sustain": short_sustain,
            "sustain_multiplier": sustain_multiplier,
            "density_gate": density_gate,
            "adjusted_value": adjusted,
            "hard_ceiling": 10.0,
            "evidence_tag": "HEURISTIC_V08_REQUIRES_HUMAN_VALIDATION",
        }
    )


def _endurance_axis(
    axes: dict[str, Any], components: dict[str, Any]
) -> dict[str, Any]:
    duration_ms = _finite(components.get("v07_map_duration_ms"))
    object_count = _finite(components.get("v07_object_count"))
    density = _finite(components.get("v07_density_objects_per_s"))
    dense_share = _finite(components.get("stamina_duration_share"))
    environment = _physical_environment(axes)
    missing = [
        name
        for name, value in (
            ("map_duration_ms", duration_ms),
            ("object_count", object_count),
            ("density_objects_per_s", density),
            ("dense_duration_share", dense_share),
            ("physical_environment", environment),
        )
        if value is None
    ]
    if missing:
        return {
            "score": None,
            "status": "INSUFFICIENT_EVIDENCE",
            "confidence": "LOW",
            "method": "HEURISTIC_WHOLE_MAP_ENDURANCE_V08",
            "combination_policy": "DURATION_VOLUME_DIFFICULTY_COVERAGE_V08",
            "signals": {},
            "warnings": [f"missing_signal:{name}" for name in missing],
            "evidence": [],
        }

    duration_s = max(0.0, float(duration_ms)) / 1000.0
    duration_load = _clamp(math.log1p(duration_s) / math.log1p(600.0), 0.0, 1.0)
    volume_load = _clamp(math.log1p(max(0.0, float(object_count))) / math.log1p(4000.0), 0.0, 1.0)
    whole_map_load = 0.55 * duration_load + 0.45 * volume_load
    difficulty_gate = _clamp(0.35 + 0.65 * (float(environment) - 3.0) / 5.0, 0.35, 1.0)
    coverage = _clamp(float(dense_share), 0.0, 1.0)
    density_gate = _clamp((float(density) - 2.0) / 8.0, 0.0, 1.0)
    coverage_bonus = 0.18 * math.sqrt(coverage) * density_gate
    value = 10.0 * _clamp(whole_map_load * difficulty_gate + coverage_bonus, 0.0, 1.0)
    return {
        "score": value / 10.0,
        "demand_star_equivalent": value,
        "percentile_rank": None,
        "scale_method": "BOUNDED_HUMAN_ENDURANCE_SCALE_0_10_V08",
        "status": "EMITTED",
        "confidence": "LOW",
        "method": "HEURISTIC_WHOLE_MAP_ENDURANCE_V08",
        "combination_policy": "DURATION_VOLUME_DIFFICULTY_COVERAGE_V08",
        "signals": {
            "map_duration_ms": duration_ms,
            "object_count": object_count,
            "density_objects_per_s": density,
            "dense_duration_share": dense_share,
            "physical_environment_stars": environment,
        },
        "warnings": [],
        "evidence": [
            {
                "component": "whole_map_endurance",
                "duration_load": duration_load,
                "volume_load": volume_load,
                "whole_map_load": whole_map_load,
                "difficulty_gate": difficulty_gate,
                "coverage": coverage,
                "density_gate": density_gate,
                "coverage_bonus": coverage_bonus,
                "evidence_tag": "HEURISTIC_V08_REQUIRES_HUMAN_VALIDATION",
            }
        ],
    }


def derive_summaries(axes: dict[str, Any]) -> dict[str, Any]:
    groups = {
        "aim_summary": ("jump_aim", "flow_aim", "aim_control", "spatial_precision"),
        "tapping_summary": ("raw_speed", "stamina", "finger_control"),
        "endurance_summary": ("endurance",),
        "overall_demand": AXIS_ORDER,
    }
    result: dict[str, Any] = {}
    for name, source_axes in groups.items():
        values: list[float] = []
        missing: list[str] = []
        for axis in source_axes:
            item = axes.get(axis)
            score = _finite(item.get("score")) if isinstance(item, dict) else None
            if not isinstance(item, dict) or item.get("status") != "EMITTED" or score is None:
                missing.append(axis)
            else:
                values.append(score)
        result[name] = {
            "score": None if missing else sum(values) / len(values),
            "status": "INSUFFICIENT_EVIDENCE" if missing else "EMITTED",
            "source_axes": list(source_axes),
            "missing_axes": missing,
            "policy": "DERIVED_DISPLAY_ONLY_ARITHMETIC_MEAN_V08",
        }
    return result


def analyze_components(
    *,
    checksum: str,
    requested_mods: Iterable[str] = (),
    components: dict[str, Any],
    calibration: dict[str, Any],
    reference_diagnostics: Optional[dict[str, Any]] = None,
    applied_mod_context: Optional[dict[str, Any]] = None,
    algorithm_id: str = ALGORITHM_ID,
) -> dict[str, Any]:
    output = v07.analyze_components(
        checksum=checksum,
        requested_mods=requested_mods,
        components=components,
        calibration=calibration,
        reference_diagnostics=reference_diagnostics,
        applied_mod_context=applied_mod_context,
    )
    base_calibration_id = str(calibration.get("calibration_id", ""))
    mod_context = output.get("diagnostics", {}).get("mod_context", {})
    output["schema_version"] = SCHEMA_VERSION
    output["identity"] = C.make_identity(
        beatmap_checksum=checksum,
        effective_mods=mod_context.get("effective_mods", []),
        clock_rate=mod_context.get("clock_rate", 1.0),
        calibration_id=calibration_id(base_calibration_id),
        algorithm_id=algorithm_id,
        map_demand_version=MAP_DEMAND_VERSION,
    )
    output["diagnostics"]["v08_base_algorithm_id"] = v07.ALGORITHM_ID
    output["diagnostics"]["v08_base_map_demand_version"] = v07.MAP_DEMAND_VERSION
    output["diagnostics"]["v08_mechanism_spec"] = MECHANISM_SPEC
    if output.get("status") != "OK":
        output["axes"]["endurance"] = {
            "score": None,
            "status": output.get("status"),
            "confidence": "LOW",
            "method": "HEURISTIC_WHOLE_MAP_ENDURANCE_V08",
            "combination_policy": "DURATION_VOLUME_DIFFICULTY_COVERAGE_V08",
            "signals": {},
            "warnings": ["analysis unavailable"],
            "evidence": [],
        }
        output["summaries"] = derive_summaries(output["axes"])
        C.scan_finite(output, "model_v08.output")
        return output

    _bounded_stamina(output["axes"], components)
    output["axes"]["endurance"] = _endurance_axis(output["axes"], components)
    output["summaries"] = derive_summaries(output["axes"])
    output["archetype"] = classify_axes(output["axes"])
    C.scan_finite(output, "model_v08.output")
    return output
