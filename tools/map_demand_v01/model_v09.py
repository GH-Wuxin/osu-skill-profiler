"""Map Demand V0.9: local finger-pattern and structural visibility overlay.

V0.8 remains replayable.  This overlay keeps its nine-axis taxonomy and adds
three deliberately small, inspectable mechanisms identified by the first
V0.8 assisted-review round:

* Finger Control uses rhythm changes *inside fast passages*, rather than only
  map-wide interval entropy.  This avoids treating a globally varied song as
  a difficult tapping pattern while recovering slider/circle mixed bursts.
* Reading gains are conditional on an actual visibility bottleneck: low AR in
  a demanding environment, or HD applied to dense high-demand structure.
* Stamina receives a bounded dense-intensity correction; map length remains
  exclusively in Endurance.

The coefficients are versioned heuristics, not a fit to the small human set.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Optional

from . import contract as C
from . import model_v08 as v08
from .archetype_v08 import AXIS_ORDER, classify_axes

ALGORITHM_ID = "MAP_DEMAND_ATOMIC_V07"
MAP_DEMAND_VERSION = "0.9.0"
SCHEMA_VERSION = "map_demand_v0.9.0"
# V0.9 changes mechanisms, not the nine-axis human-label taxonomy.
AXIS_SCHEMA_VERSION = v08.AXIS_SCHEMA_VERSION
MECHANISM_SPEC = (
    "MAP_DEMAND_ATOMIC_V07:base=MAP_DEMAND_ATOMIC_V06;"
    "finger=fast_passage_interval_change_plus_speed_floor_recovery;"
    "reading=relative_low_ar_or_hd_dense_structure_only;"
    "stamina=dense_intensity_correction_bounded_0_10;"
    "endurance=unchanged_v08"
)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = _clamp(q, 0.0, 1.0) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def calibration_id(base_calibration_id: str) -> str:
    payload = json.dumps(
        {"base_calibration_id": base_calibration_id, "mechanism_spec": MECHANISM_SPEC},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"mdoverlay_v09:{digest}"


def extract_from_path(
    path: str, requested_mods: Iterable[str] = ()
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    return v08.extract_from_path(path, requested_mods=requested_mods)


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Optional[dict[str, Any]] = None,
    difficulty: Optional[dict[str, Any]] = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    rows = list(local_rows)
    components, warnings = v08.extract_components(
        rows,
        features,
        difficulty=difficulty,
        clock_rate=clock_rate,
        effective_mods=effective_mods,
    )

    intervals: list[float] = []
    for row in rows:
        if row.get("ls.object_type") == "spinner":
            continue
        interval = _finite(row.get("ls.adjusted_delta_time_ms"))
        if interval is not None and interval > 0.0:
            intervals.append(interval)

    fast_changes: list[float] = []
    for previous, current in zip(intervals, intervals[1:]):
        # 250 ms keeps ordinary slow spacing out while retaining doubles,
        # triples, streams, and slider/circle transition patterns.
        if max(previous, current) <= 250.0:
            fast_changes.append(abs(math.log2(previous / current)))

    components["v09_fast_object_share_250ms"] = (
        None
        if not intervals
        else sum(interval <= 250.0 for interval in intervals) / len(intervals)
    )
    components["v09_fast_interval_change_mean"] = (
        None if not fast_changes else sum(fast_changes) / len(fast_changes)
    )
    components["v09_fast_interval_change_p75"] = _quantile(fast_changes, 0.75)
    components["v09_fast_interval_pair_count"] = len(fast_changes)
    if not intervals:
        warnings.append("v09 finger pattern: no eligible non-spinner intervals")
    elif not fast_changes:
        warnings.append("v09 finger pattern: no adjacent intervals within 250ms")
    return components, warnings


def sha256_file_bytes(data: bytes) -> str:
    return v08.sha256_file_bytes(data)


def _axis_stars(axes: dict[str, Any], axis: str) -> float | None:
    item = axes.get(axis)
    if not isinstance(item, dict) or item.get("status") != "EMITTED":
        return None
    return _finite(item.get("demand_star_equivalent"))


def _set_axis_stars(
    axes: dict[str, Any],
    axis: str,
    stars: float,
    *,
    mechanism: str,
    evidence: dict[str, Any],
) -> None:
    item = axes.get(axis)
    old = _axis_stars(axes, axis)
    if not isinstance(item, dict) or old is None:
        return
    adjusted = max(0.0, float(stars))
    item["demand_star_equivalent"] = adjusted
    item["score"] = adjusted / 10.0
    item["percentile_rank"] = None
    item["scale_method"] = f"{item.get('scale_method', '')}+V09_MECHANISM_OVERLAY"
    item["method"] = f"{item.get('method', '')}+{mechanism}"
    detail = dict(evidence)
    detail.update(
        {
            "component": mechanism,
            "base_stars": old,
            "adjusted_stars": adjusted,
            "evidence_tag": "HEURISTIC_V09_REQUIRES_MORE_HUMAN_VALIDATION",
        }
    )
    item.setdefault("evidence", []).append(detail)


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
    if len(values) < 3:
        return None
    values.sort(reverse=True)
    return sum(values[:3]) / 3.0


def _finger_overlay(axes: dict[str, Any], components: dict[str, Any]) -> None:
    current = _axis_stars(axes, "finger_control")
    raw = _axis_stars(axes, "raw_speed")
    change_mean = _finite(components.get("v09_fast_interval_change_mean"))
    change_p75 = _finite(components.get("v09_fast_interval_change_p75"))
    pair_count = _finite(components.get("v09_fast_interval_pair_count"))
    burst_250 = _finite(components.get("v07_burst_longest_duration_ms_250ms"))
    density = _finite(components.get("reading_density"))
    duration_ms = _finite(components.get("v07_map_duration_ms"))
    if None in (
        current,
        raw,
        change_mean,
        change_p75,
        pair_count,
        burst_250,
        density,
        duration_ms,
    ):
        return
    if float(pair_count) < 8.0:
        return

    # P75 catches repeated short/long alternation.  The mean term activates on
    # less regular fast passages without allowing isolated transitions to
    # dominate a map.  A regular stream therefore stays on the V0.8 result.
    strong_alternation_gate = _clamp(float(change_p75), 0.0, 1.0)
    soft_variation_gate = _clamp(
        (float(change_mean) - 0.10) / 0.20, 0.0, 1.0
    )
    persistence_gate = _clamp(
        (float(burst_250) / 1000.0 - 5.0) / 7.0, 0.0, 1.0
    )
    density_gate = _clamp((float(density) - 9.0) / 3.0, 0.0, 1.0)
    short_map_gate = _clamp(
        (360000.0 - float(duration_ms)) / 160000.0, 0.0, 1.0
    )
    # A high map-wide rhythm mean is not sufficient.  Soft variation must
    # persist through a long or locally dense passage; only an unmistakable
    # repeated short/long alternation can activate by itself.
    change_gate = max(
        strong_alternation_gate,
        soft_variation_gate * persistence_gate,
        soft_variation_gate * density_gate * short_map_gate,
    )
    speed_floor_recovery = change_gate * max(0.0, float(raw) - float(current))
    coordination_bonus = 1.55 * math.sqrt(change_gate)
    sustain_bonus = 0.70 * persistence_gate * math.sqrt(change_gate)
    dense_control_bonus = 0.70 * density_gate * math.sqrt(change_gate)
    adjusted = (
        float(current)
        + speed_floor_recovery
        + coordination_bonus
        + sustain_bonus
        + dense_control_bonus
    )
    _set_axis_stars(
        axes,
        "finger_control",
        adjusted,
        mechanism="HEURISTIC_FAST_PASSAGE_FINGER_CONTROL_V09",
        evidence={
            "raw_speed_stars": raw,
            "fast_interval_pair_count": pair_count,
            "fast_interval_change_mean": change_mean,
            "fast_interval_change_p75": change_p75,
            "strong_alternation_gate": strong_alternation_gate,
            "soft_variation_gate": soft_variation_gate,
            "change_gate": change_gate,
            "speed_floor_recovery_stars": speed_floor_recovery,
            "coordination_bonus_stars": coordination_bonus,
            "burst_250_duration_ms": burst_250,
            "persistence_gate": persistence_gate,
            "sustain_bonus_stars": sustain_bonus,
            "density_objects_per_s": density,
            "density_gate": density_gate,
            "map_duration_ms": duration_ms,
            "short_map_gate": short_map_gate,
            "dense_control_bonus_stars": dense_control_bonus,
        },
    )


def _stamina_overlay(axes: dict[str, Any], components: dict[str, Any]) -> None:
    current = _axis_stars(axes, "stamina")
    density = _finite(components.get("reading_density"))
    if current is None or density is None:
        return
    density_gate = _clamp((float(density) - 9.0) / 3.0, 0.0, 1.0)
    headroom_gate = _clamp((7.2 - current) / 0.8, 0.0, 1.0)
    bonus = 0.85 * density_gate * headroom_gate
    _set_axis_stars(
        axes,
        "stamina",
        min(10.0, current + bonus),
        mechanism="HEURISTIC_DENSE_INTENSITY_STAMINA_V09",
        evidence={
            "density_objects_per_s": density,
            "dense_intensity_gate": density_gate,
            "headroom_gate": headroom_gate,
            "dense_intensity_bonus": bonus,
            "hard_ceiling": 10.0,
        },
    )


def _reading_overlay(
    axes: dict[str, Any], components: dict[str, Any], mods: set[str]
) -> dict[str, float] | None:
    current = _axis_stars(axes, "reading")
    environment = _physical_environment(axes)
    preempt = _finite(components.get("reading_preempt_median_ms"))
    density = _finite(components.get("reading_density"))
    hidden_pressure = _finite(components.get("reading_hidden_pressure"))
    if current is None or environment is None or preempt is None or density is None:
        return None

    # The correction targets the mid/high-demand region where an AR that is
    # normal in isolation becomes the bottleneck.  It fades before the extreme
    # tail, where V0.8's explicit relative-AR mechanism already applies.
    moderate_environment = _clamp((8.0 - environment) / 1.5, 0.0, 1.0)
    low_ar_gate = _clamp((preempt - 540.0) / 80.0, 0.0, 1.0)
    low_ar_bonus = 1.80 * low_ar_gate * moderate_environment

    hd_low_ar_synergy = 0.0
    hd_dense_structure = 0.0
    dense_hd_gate = 0.0
    if "HD" in mods and hidden_pressure is not None:
        pressure = _clamp(hidden_pressure, 0.0, 1.0)
        hd_low_ar_synergy = (
            2.0 * low_ar_gate * pressure * moderate_environment
        )
        dense_hd_gate = (
            _clamp((density - 9.0) / 2.5, 0.0, 1.0)
            * moderate_environment
        )
        hd_dense_structure = 2.4 * dense_hd_gate

    adjusted = current + low_ar_bonus + hd_low_ar_synergy + hd_dense_structure
    _set_axis_stars(
        axes,
        "reading",
        adjusted,
        mechanism="HEURISTIC_STRUCTURAL_VISIBILITY_READING_V09",
        evidence={
            "physical_environment_top3_stars": environment,
            "actual_preempt_ms": preempt,
            "density_objects_per_s": density,
            "moderate_environment_gate": moderate_environment,
            "low_ar_gate": low_ar_gate,
            "low_ar_bonus_stars": low_ar_bonus,
            "hidden_pressure": hidden_pressure,
            "hd_low_ar_synergy_stars": hd_low_ar_synergy,
            "dense_hd_gate": dense_hd_gate,
            "hd_dense_structure_bonus_stars": hd_dense_structure,
        },
    )
    return {
        "physical_environment_top3_stars": environment,
        "moderate_environment_gate": moderate_environment,
        "low_ar_gate": low_ar_gate,
        "low_ar_bonus_stars": low_ar_bonus,
        "hd_low_ar_synergy_stars": hd_low_ar_synergy,
        "dense_hd_gate": dense_hd_gate,
        "hd_dense_structure_bonus_stars": hd_dense_structure,
    }


def derive_summaries(axes: dict[str, Any]) -> dict[str, Any]:
    return v08.derive_summaries(axes)


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
    output = v08.analyze_components(
        checksum=checksum,
        requested_mods=requested_mods,
        components=components,
        calibration=calibration,
        reference_diagnostics=reference_diagnostics,
        applied_mod_context=applied_mod_context,
    )
    mod_context = output.get("diagnostics", {}).get("mod_context", {})
    output["schema_version"] = SCHEMA_VERSION
    output["identity"] = C.make_identity(
        beatmap_checksum=checksum,
        effective_mods=mod_context.get("effective_mods", []),
        clock_rate=mod_context.get("clock_rate", 1.0),
        calibration_id=calibration_id(str(calibration.get("calibration_id", ""))),
        algorithm_id=algorithm_id,
        map_demand_version=MAP_DEMAND_VERSION,
    )
    output["diagnostics"]["v09_base_algorithm_id"] = v08.ALGORITHM_ID
    output["diagnostics"]["v09_base_map_demand_version"] = v08.MAP_DEMAND_VERSION
    output["diagnostics"]["v09_mechanism_spec"] = MECHANISM_SPEC
    if output.get("status") != "OK":
        C.scan_finite(output, "model_v09.output")
        return output

    axes = output["axes"]
    _stamina_overlay(axes, components)
    _finger_overlay(axes, components)
    output["diagnostics"]["v09_structural_visibility"] = _reading_overlay(
        axes,
        components,
        set(mod_context.get("effective_mods", [])),
    )
    output["summaries"] = derive_summaries(axes)
    output["archetype"] = classify_axes(axes)
    C.scan_finite(output, "model_v09.output")
    return output
