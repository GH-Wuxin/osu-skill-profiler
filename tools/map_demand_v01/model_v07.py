"""Map Demand V0.7 mechanism overlay.

V0.6 remains the frozen, replayable signal/calibration baseline.  This module
uses the same objective inputs, then applies explicit star-space mechanisms
identified by the first human review round:

* approach rate adequacy is relative to the surrounding map demand;
* HD compounds an existing visibility deficit instead of adding a flat bonus;
* visibility burden can transfer into flow aim and aim control;
* sustained clicking contributes to finger control even when rhythm is regular.

The coefficients are versioned heuristics, not a regression fitted to the
small human sample.  Human responses are evaluation anchors only.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Optional

from . import contract as C
from . import model as v06
from .archetype_v01 import classify_axes

ALGORITHM_ID = "MAP_DEMAND_ATOMIC_V05"
MAP_DEMAND_VERSION = "0.7.0"
SCHEMA_VERSION = "map_demand_v0.7.0"
AXIS_SCHEMA_VERSION = "atomic_v0.6.0"  # Taxonomy unchanged from V0.6.

MECHANISM_SPEC = (
    "MAP_DEMAND_ATOMIC_V05:base=MAP_DEMAND_ATOMIC_V04;"
    "relative_ar=required_preempt_by_physical_environment;"
    "reading=environment_floor+nonlinear_visibility_deficit;"
    "hidden=visibility_deficit_compound_only;"
    "transfer=visibility_to_flow_and_aim_control;"
    "flow=physical_environment_support;"
    "aim=high_jump_precision_control_floor;"
    "finger=pattern_control+speed_stamina+sustained_circle_clicking"
)

_EXTRA_FEATURES = {
    "v07_object_count": "temporal.object_count",
    "v07_map_duration_ms": "temporal.map_duration_ms",
    "v07_density_objects_per_s": "temporal.density_objects_per_s",
    "v07_object_rate_max_1s": "temporal.object_rate_max_1s",
    "v07_slider_ratio": "slider.slider_ratio",
    "v07_burst_longest_duration_ms_125ms": "temporal.burst_longest_duration_ms_125ms",
    "v07_burst_longest_duration_ms_250ms": "temporal.burst_longest_duration_ms_250ms",
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def _axis_stars(axes: dict[str, Any], axis: str) -> float | None:
    item = axes.get(axis)
    if not isinstance(item, dict) or item.get("status") != "EMITTED":
        return None
    return _finite(item.get("demand_star_equivalent"))


def calibration_id(base_calibration_id: str) -> str:
    payload = json.dumps(
        {"base_calibration_id": base_calibration_id, "mechanism_spec": MECHANISM_SPEC},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"mdoverlay_v07:{digest}"


def _rank(calibration: dict[str, Any], signal: str, value: Any) -> float:
    number = _finite(value)
    distribution = (calibration.get("distributions") or {}).get(signal)
    if number is None or not isinstance(distribution, list) or not distribution:
        return 0.0
    return C.quantile_rank(distribution, number)


def _set_axis_stars(
    axes: dict[str, Any],
    axis: str,
    stars: float,
    *,
    mechanism: str,
    evidence: dict[str, Any],
) -> None:
    item = axes.get(axis)
    if not isinstance(item, dict) or item.get("status") != "EMITTED":
        return
    old_stars = _finite(item.get("demand_star_equivalent"))
    if old_stars is None:
        return
    adjusted = max(0.0, float(stars))
    item["demand_star_equivalent"] = C.finite_float(
        adjusted, f"v07.{axis}.demand_star_equivalent"
    )
    item["score"] = C.finite_float(adjusted / 10.0, f"v07.{axis}.score")
    # The value is no longer a single calibrated component percentile.
    item["percentile_rank"] = None
    item["scale_method"] = (
        f"{item.get('scale_method', '')}+V07_MECHANISM_OVERLAY"
    )
    item["method"] = f"{item.get('method', '')}+{mechanism}"
    details = dict(evidence)
    details.update(
        {
            "component": mechanism,
            "base_stars": old_stars,
            "adjusted_stars": adjusted,
            "evidence_tag": "HEURISTIC_V07_HUMAN_ANCHOR_VALIDATED",
        }
    )
    item.setdefault("evidence", []).append(details)


def extract_from_path(
    path: str, requested_mods: Iterable[str] = ()
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    return v06.extract_from_path(path, requested_mods=requested_mods)


def sha256_file_bytes(data: bytes) -> str:
    return v06.sha256_file_bytes(data)


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Optional[dict[str, Any]] = None,
    difficulty: Optional[dict[str, Any]] = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    rows = list(local_rows)
    components, warnings = v06.extract_components(
        rows,
        features,
        difficulty=difficulty,
        clock_rate=clock_rate,
        effective_mods=effective_mods,
    )
    for component, feature in _EXTRA_FEATURES.items():
        raw = None if features is None else features.get(feature)
        value = _finite(raw)
        components[component] = value
        if raw is not None and value is None:
            warnings.append(f"{feature}: non-finite or non-numeric -> unavailable")
    return components, warnings


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


def _visibility_mechanism(
    axes: dict[str, Any],
    components: dict[str, Any],
    calibration: dict[str, Any],
    mods: set[str],
) -> dict[str, float] | None:
    environment = _physical_environment(axes)
    preempt = _finite(components.get("reading_preempt_median_ms"))
    old_reading = _axis_stars(axes, "reading")
    if environment is None or preempt is None or old_reading is None:
        return None

    density_rank = _rank(calibration, "reading_density", components.get("reading_density"))
    # A harder surrounding pattern needs less preempt before the AR becomes a
    # visibility bottleneck.  This intentionally makes AR relative: AR9 can be
    # adequate at 5 stars and low at 8 stars; AR10 can be low on an extreme map.
    required_preempt = _clamp(700.0 - 70.0 * (environment - 5.0), 300.0, 900.0)
    relative_deficit = max(0.0, preempt / required_preempt - 1.0)
    deficit_for_curve = min(relative_deficit, 2.0)

    environment_floor_target = environment * (0.66 + 0.16 * density_rank)
    # Do not impose a universal ~4-star Reading floor on ordinary maps.  The
    # cross-axis floor is a high-demand mechanism and fades in from 5 to 7
    # physical stars; explicit low-AR burden below remains independently active.
    high_demand_activation = _clamp((environment - 5.5) / 1.5, 0.0, 1.0)
    absolute_low_ar_activation = _clamp((preempt - 750.0) / 300.0, 0.0, 1.0)
    environment_floor_activation = max(
        high_demand_activation, absolute_low_ar_activation
    )
    environment_floor = old_reading + environment_floor_activation * max(
        0.0, environment_floor_target - old_reading
    )
    relative_bonus = (
        1.50 * math.sqrt(deficit_for_curve) * density_rank
        + 0.50 * deficit_for_curve
    )
    absolute_low_ar_bonus = _clamp((preempt - 700.0) * 0.004, 0.0, 1.5)
    nm_reading = max(old_reading, environment_floor) + relative_bonus + absolute_low_ar_bonus

    hidden_bonus = 0.0
    hidden_pressure = _finite(components.get("reading_hidden_pressure"))
    if "HD" in mods and relative_deficit > 0.0 and hidden_pressure is not None:
        hidden_strength = 0.65 + 0.35 * _clamp(hidden_pressure, 0.0, 1.0)
        hidden_bonus = min(
            2.5,
            (1.00 + 0.22 * max(0.0, environment - 5.0))
            * math.sqrt(deficit_for_curve)
            * hidden_strength,
        )

    adjusted_reading = nm_reading + hidden_bonus
    visibility_load = relative_bonus + absolute_low_ar_bonus + hidden_bonus
    _set_axis_stars(
        axes,
        "reading",
        adjusted_reading,
        mechanism="HEURISTIC_RELATIVE_AR_READING_V07",
        evidence={
            "physical_environment_stars": environment,
            "actual_preempt_ms": preempt,
            "required_preempt_ms": required_preempt,
            "relative_ar_deficit": relative_deficit,
            "density_rank": density_rank,
            "environment_floor_target_stars": environment_floor_target,
            "high_demand_activation": high_demand_activation,
            "absolute_low_ar_activation": absolute_low_ar_activation,
            "environment_floor_activation": environment_floor_activation,
            "environment_floor_stars": environment_floor,
            "relative_ar_bonus_stars": relative_bonus,
            "absolute_low_ar_bonus_stars": absolute_low_ar_bonus,
            "hidden_compound_bonus_stars": hidden_bonus,
        },
    )
    return {
        "environment": environment,
        "actual_preempt_ms": preempt,
        "required_preempt_ms": required_preempt,
        "relative_ar_deficit": relative_deficit,
        "visibility_load": visibility_load,
        "hidden_bonus": hidden_bonus,
    }


def _flow_mechanism(axes: dict[str, Any], visibility: dict[str, float] | None) -> None:
    base = _axis_stars(axes, "flow_aim")
    if base is None:
        return
    environment = (
        visibility["environment"] if visibility is not None else _physical_environment(axes)
    )
    if environment is None:
        return
    visibility_load = 0.0 if visibility is None else visibility["visibility_load"]
    environment_activation = _clamp((environment - 4.5) / 2.0, 0.0, 1.0)
    morphology_activation = _clamp((base - 1.5) / 2.0, 0.0, 1.0)
    support_activation = environment_activation * morphology_activation
    support = support_activation * (
        0.14 * environment + 0.25 * max(0.0, environment - base)
    )
    transfer = 0.12 * visibility_load
    _set_axis_stars(
        axes,
        "flow_aim",
        base + support + transfer,
        mechanism="HEURISTIC_FLOW_ENVIRONMENT_SUPPORT_V07",
        evidence={
            "physical_environment_stars": environment,
            "environment_activation": environment_activation,
            "morphology_activation": morphology_activation,
            "environment_support_stars": support,
            "visibility_transfer_stars": transfer,
        },
    )


def _aim_mechanism(axes: dict[str, Any], visibility: dict[str, float] | None) -> None:
    base = _axis_stars(axes, "aim_control")
    jump = _axis_stars(axes, "jump_aim")
    precision = _axis_stars(axes, "spatial_precision")
    if base is None or jump is None or precision is None:
        return
    floor_candidate = 0.60 * jump + 0.40 * precision
    activation = _clamp((jump - 7.0) / 2.0, 0.0, 1.0)
    high_jump_floor = base + activation * max(0.0, floor_candidate - base)
    visibility_load = 0.0 if visibility is None else visibility["visibility_load"]
    transfer = 0.06 * visibility_load
    _set_axis_stars(
        axes,
        "aim_control",
        high_jump_floor + transfer,
        mechanism="HEURISTIC_AIM_CONTROL_FLOOR_AND_VISIBILITY_V07",
        evidence={
            "jump_aim_stars": jump,
            "spatial_precision_stars": precision,
            "high_jump_floor_candidate_stars": floor_candidate,
            "high_jump_floor_activation": activation,
            "visibility_transfer_stars": transfer,
        },
    )


def _finger_mechanism(
    axes: dict[str, Any],
    components: dict[str, Any],
    visibility: dict[str, float] | None,
) -> None:
    base = _axis_stars(axes, "finger_control")
    raw = _axis_stars(axes, "raw_speed")
    stamina = _axis_stars(axes, "stamina")
    if base is None or raw is None or stamina is None:
        return
    slider_ratio = _finite(components.get("v07_slider_ratio"))
    rate = _finite(components.get("v07_object_rate_max_1s"))
    burst_125 = _finite(components.get("v07_burst_longest_duration_ms_125ms"))
    burst_250 = _finite(components.get("v07_burst_longest_duration_ms_250ms"))
    if None in (slider_ratio, rate, burst_125, burst_250):
        return

    circle_share = 1.0 - _clamp(float(slider_ratio), 0.0, 1.0)
    # Only genuinely sustained clicking enters this term.  A short ordinary
    # burst must not make every speed map a Finger Control map.
    duration_s = max(float(burst_125), float(burst_250) * 0.45) / 1000.0
    duration_gate = _clamp((math.log1p(duration_s) - math.log1p(3.0)) / 2.2, 0.0, 1.0)
    rate_gate = _clamp((float(rate) - 6.0) / 7.0, 0.0, 1.0)
    sustained_clicking = 2.0 * circle_share * duration_gate * (0.45 + 0.55 * rate_gate)

    # Circle-weighted tapping supplies a floor without declaring slider-heavy
    # speed maps Finger Control maps.  Preserve strong irregularity evidence,
    # gently extend only its upper tail, and combine (rather than add) the two
    # bottlenecks: sustained clicking and visibility-to-finger transfer.
    environment = (
        visibility["environment"] if visibility is not None else _physical_environment(axes)
    )
    environment_activation = (
        0.0 if environment is None else _clamp((environment - 4.5) / 2.0, 0.0, 1.0)
    )
    circle_speed_floor = raw * circle_share
    activated_floor = base + environment_activation * max(
        0.0, circle_speed_floor - base
    )
    pattern_extension = (
        environment_activation * 0.80 * max(0.0, base - 4.0)
    )
    visibility_load = 0.0 if visibility is None else visibility["visibility_load"]
    visibility_transfer = min(1.5, 0.60 * visibility_load)
    bottleneck_bonus = max(sustained_clicking, visibility_transfer)
    adjusted = activated_floor + pattern_extension + bottleneck_bonus
    _set_axis_stars(
        axes,
        "finger_control",
        adjusted,
        mechanism="HEURISTIC_SUSTAINED_CLICKING_FINGER_V07",
        evidence={
            "raw_speed_stars": raw,
            "stamina_stars": stamina,
            "pattern_control_stars": base,
            "circle_speed_floor_stars": circle_speed_floor,
            "environment_stars": environment,
            "environment_activation": environment_activation,
            "activated_floor_stars": activated_floor,
            "pattern_extension_stars": pattern_extension,
            "circle_share": circle_share,
            "burst_duration_proxy_s": duration_s,
            "duration_gate": duration_gate,
            "rate_gate": rate_gate,
            "sustained_clicking_bonus_stars": sustained_clicking,
            "visibility_transfer_stars": visibility_transfer,
            "bottleneck_bonus_stars": bottleneck_bonus,
        },
    )


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
    output = v06.analyze_components(
        checksum=checksum,
        requested_mods=requested_mods,
        components=components,
        calibration=calibration,
        reference_diagnostics=reference_diagnostics,
        applied_mod_context=applied_mod_context,
        algorithm_id=algorithm_id,
    )
    base_calibration_id = str(calibration.get("calibration_id", ""))
    overlay_calibration_id = calibration_id(base_calibration_id)
    mod_context = output.get("diagnostics", {}).get("mod_context", {})
    output["schema_version"] = SCHEMA_VERSION
    output["identity"] = C.make_identity(
        beatmap_checksum=checksum,
        effective_mods=mod_context.get("effective_mods", []),
        clock_rate=mod_context.get("clock_rate", 1.0),
        calibration_id=overlay_calibration_id,
        algorithm_id=algorithm_id,
        map_demand_version=MAP_DEMAND_VERSION,
    )
    output["diagnostics"]["base_algorithm_id"] = C.ALGORITHM_ID
    output["diagnostics"]["base_map_demand_version"] = C.MAP_DEMAND_VERSION
    output["diagnostics"]["base_calibration_id"] = base_calibration_id
    output["diagnostics"]["mechanism_spec"] = MECHANISM_SPEC
    if output.get("status") != "OK":
        C.scan_finite(output, "model_v07.output")
        return output

    axes = output["axes"]
    mods = set(mod_context.get("effective_mods", []))
    visibility = _visibility_mechanism(axes, components, calibration, mods)
    _flow_mechanism(axes, visibility)
    _aim_mechanism(axes, visibility)
    _finger_mechanism(axes, components, visibility)
    output["summaries"] = v06.derive_summaries(axes)
    output["archetype"] = classify_axes(axes)
    output["diagnostics"]["v07_visibility"] = visibility
    C.scan_finite(output, "model_v07.output")
    return output
