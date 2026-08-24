"""Map Demand V0.92.2: object-level movement and sustain timelines.

V0.91 remains replayable.  This revision starts the V0.92 rebuild by replacing
the old Aim Control proxy (two map-level P90 values) with one general state
transition model.  Named patterns such as spacing separation, reversals, and
continuous large angle changes are diagnostics produced by the same model;
they are not special-case score bonuses.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Optional

from . import contract as C
from . import model_v08 as v08
from . import model_v091 as v091
from .archetype_v08 import AXIS_ORDER, classify_axes as classify_v08

ALGORITHM_ID = "MAP_DEMAND_ATOMIC_V0922"
MAP_DEMAND_VERSION = "0.9.2.2"
SCHEMA_VERSION = "map_demand_v0.9.2.2"
AXIS_SCHEMA_VERSION = v091.AXIS_SCHEMA_VERSION
MECHANISM_SPEC = (
    "MAP_DEMAND_ATOMIC_V0922:base=v091_replay;"
    "jump=raw_distance_velocity_mild_cs_with_persistent_high_jump_tail;"
    "aim_control=unified_object_movement_state_change_timeline;"
    "state=velocity_direction_spacing_cadence_tolerance;"
    "aggregation=peak_repeat_chain_window;"
    "stamina=continuous_plus_repeated_section_pressure_burden;"
    "endurance=section_aggregated_pressure_time_recovery_diminishing_duration;"
    "archetype=star_axes_primary_bounded_sustain_auxiliary"
)

_STAR_AXES = v091._STAR_AXES
_BOUNDED_AUXILIARY_AXES = ("stamina", "endurance")

extract_from_path = v091.extract_from_path
sha256_file_bytes = v091.sha256_file_bytes


def _finite(value: Any) -> float | None:
    return v091._finite(value)


def _clamp(value: float, low: float, high: float) -> float:
    return v091._clamp(value, low, high)


def _quantile(values: list[float], q: float) -> float | None:
    return v091._quantile(values, q)


def calibration_id(base_calibration_id: str) -> str:
    payload = json.dumps(
        {"base_calibration_id": base_calibration_id, "mechanism_spec": MECHANISM_SPEC},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"mdoverlay_v0922:{digest}"


def _jump_movement_components(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure Jump Aim from distance/time with only a mild CS influence.

    The high-difficulty tail requires repeated simultaneous distance and speed
    demand.  Direction changes are deliberately absent: they belong to Aim
    Control, while target tolerance and settling belong to Spatial Precision.
    """

    distances: list[float] = []
    velocities: list[float] = []
    joint_loads: list[float] = []
    high_threshold = 0.55
    high_count = 0
    longest_chain_count = 0
    longest_chain_duration_ms = 0.0
    chain_count = 0
    chain_start_ms = 0.0

    for row in rows:
        if row.get("ls.object_type") == "spinner":
            chain_count = 0
            continue
        time_ms = _finite(row.get("ls.start_time_ms"))
        jump_time = _finite(row.get("ls.minimum_jump_time_ms"))
        distance = _finite(row.get("ls.jump_distance_raw_px"))
        cs_scale = _finite(row.get("ls.cs_scale"))
        if (
            time_ms is None
            or jump_time is None
            or distance is None
            or jump_time <= 0.0
            or distance < 0.0
        ):
            chain_count = 0
            continue

        velocity = distance / max(jump_time, C.MIN_TIME_MS)
        distance_gate = _clamp((distance - 100.0) / 220.0, 0.0, 1.5)
        velocity_gate = _clamp((velocity - 0.70) / 2.0, 0.0, 1.5)
        mild_cs = (
            _clamp(float(cs_scale), 0.5, 2.0) ** 0.08
            if cs_scale is not None and cs_scale > 0.0
            else 1.0
        )
        joint = math.sqrt(distance_gate * velocity_gate) * mild_cs
        distances.append(distance)
        velocities.append(velocity)
        joint_loads.append(joint)

        if joint >= high_threshold and jump_time <= 250.0:
            high_count += 1
            if chain_count == 0:
                chain_start_ms = time_ms
            chain_count += 1
            longest_chain_count = max(longest_chain_count, chain_count)
            longest_chain_duration_ms = max(
                longest_chain_duration_ms, time_ms - chain_start_ms
            )
        else:
            chain_count = 0

    high_share = None if not joint_loads else high_count / len(joint_loads)
    joint_p95 = _quantile(joint_loads, 0.95)
    joint_p99 = _quantile(joint_loads, 0.99)
    severity_gate = _clamp(((joint_p95 or 0.0) - 0.50) / 0.70, 0.0, 1.0)
    extreme_gate = _clamp(((joint_p99 or 0.0) - 0.65) / 0.75, 0.0, 1.0)
    share_gate = _clamp((high_share or 0.0) / 0.25, 0.0, 1.0)
    chain_gate = _clamp((longest_chain_count - 4.0) / 24.0, 0.0, 1.0)
    persistence_gate = 0.40 * share_gate + 0.60 * chain_gate
    tail_gate = _clamp(
        (0.72 * severity_gate + 0.28 * extreme_gate) * persistence_gate,
        0.0,
        1.0,
    )
    tail_activation = _clamp((tail_gate - 0.25) / 0.65, 0.0, 1.0)
    return {
        "v092_jump_transition_count": len(joint_loads),
        "v092_jump_distance_raw_p95_px": _quantile(distances, 0.95),
        "v092_jump_distance_raw_p99_px": _quantile(distances, 0.99),
        "v092_jump_velocity_raw_p95_px_per_ms": _quantile(velocities, 0.95),
        "v092_jump_velocity_raw_p99_px_per_ms": _quantile(velocities, 0.99),
        "v092_jump_joint_load_p95": joint_p95,
        "v092_jump_joint_load_p99": joint_p99,
        "v092_jump_high_threshold": high_threshold,
        "v092_jump_high_transition_share": high_share,
        "v092_jump_longest_chain_count": longest_chain_count,
        "v092_jump_longest_chain_duration_ms": longest_chain_duration_ms,
        "v092_jump_severity_gate": severity_gate,
        "v092_jump_extreme_gate": extreme_gate,
        "v092_jump_persistence_gate": persistence_gate,
        "v092_jump_tail_gate": tail_gate,
        "v092_jump_tail_activation": tail_activation,
    }


def _movement_control_components(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build one general movement-state shock timeline.

    Every valid transition is represented by movement magnitude, available
    time, turn severity, spacing change, cadence change, and target tolerance.
    A spacing separation therefore appears as two state shocks (leave and
    recover), while repeated large turns naturally form a long control chain.
    """

    shocks: list[tuple[float, float]] = []
    turn_terms: list[float] = []
    speed_terms: list[float] = []
    spacing_terms: list[float] = []
    cadence_terms: list[float] = []
    coupling_terms: list[float] = []
    stable_spacing_terms: list[float] = []

    previous_velocity: float | None = None
    previous_distance: float | None = None
    previous_interval: float | None = None

    for row in rows:
        if row.get("ls.object_type") == "spinner":
            previous_velocity = None
            previous_distance = None
            previous_interval = None
            continue

        time_ms = _finite(row.get("ls.start_time_ms"))
        jump_time = _finite(row.get("ls.minimum_jump_time_ms"))
        interval = _finite(row.get("ls.adjusted_delta_time_ms"))
        distance = _finite(row.get("ls.jump_distance_raw_px"))
        radius = _finite(row.get("ls.radius_px"))
        angle = _finite(row.get("ls.slider_aware_angle_rad"))
        if (
            time_ms is None
            or jump_time is None
            or interval is None
            or distance is None
            or jump_time <= 0.0
            or interval <= 0.0
            or distance < 0.0
        ):
            continue

        velocity = distance / max(jump_time, C.MIN_TIME_MS)
        if previous_velocity is None or previous_distance is None or previous_interval is None:
            previous_velocity = velocity
            previous_distance = distance
            previous_interval = interval
            continue

        turn = 0.0 if angle is None else _clamp(1.0 - angle / math.pi, 0.0, 1.0)
        speed_change = _clamp(
            abs(math.log2((velocity + 0.12) / (previous_velocity + 0.12))) / 1.35,
            0.0,
            1.5,
        )
        spacing_change = _clamp(
            abs(math.log2((distance + 16.0) / (previous_distance + 16.0))) / 1.35,
            0.0,
            1.5,
        )
        cadence_change = _clamp(
            abs(math.log2(interval / previous_interval)) / 1.20,
            0.0,
            1.5,
        )
        cadence_stability = math.exp(-2.6 * cadence_change)
        stable_spacing = spacing_change * cadence_stability
        movement_coupling = cadence_change * max(turn, speed_change, spacing_change)

        speed_gate = _clamp((velocity - 0.28) / 1.65, 0.0, 1.25)
        distance_gate = _clamp((distance - 32.0) / 220.0, 0.0, 1.20)
        movement_gate = _clamp(0.18 + 0.56 * speed_gate + 0.26 * distance_gate, 0.18, 1.25)
        tolerance_gate = 0.0
        if radius is not None and radius > 0.0:
            tolerance_gate = _clamp((distance / (2.0 * radius) - 1.5) / 5.0, 0.0, 1.0)

        state_change = (
            0.45 * turn**0.70
            + 0.27 * speed_change
            + 0.20 * stable_spacing
            + 0.06 * movement_coupling
            + 0.02 * tolerance_gate
        )
        shock = movement_gate * state_change
        shocks.append((time_ms, shock))
        turn_terms.append(turn)
        speed_terms.append(speed_change)
        spacing_terms.append(spacing_change)
        cadence_terms.append(cadence_change)
        coupling_terms.append(movement_coupling)
        stable_spacing_terms.append(stable_spacing)

        previous_velocity = velocity
        previous_distance = distance
        previous_interval = interval

    shock_values = [shock for _, shock in shocks]
    high_threshold = 0.22
    high = [(time_ms, shock) for time_ms, shock in shocks if shock >= high_threshold]
    high_share = None if not shocks else len(high) / len(shocks)

    longest_chain_count = 0
    longest_chain_duration_ms = 0.0
    chain_count = 0
    chain_start = 0.0
    previous_high_time: float | None = None
    for time_ms, _ in high:
        if previous_high_time is None or time_ms - previous_high_time > 450.0:
            chain_count = 1
            chain_start = time_ms
        else:
            chain_count += 1
        longest_chain_count = max(longest_chain_count, chain_count)
        longest_chain_duration_ms = max(longest_chain_duration_ms, time_ms - chain_start)
        previous_high_time = time_ms

    window_loads: list[float] = []
    left = 0
    running = 0.0
    for right, (time_ms, shock) in enumerate(shocks):
        running += shock
        while left <= right and time_ms - shocks[left][0] > 5000.0:
            running -= shocks[left][1]
            left += 1
        window_loads.append(running)

    active_duration_s = 0.0
    if len(shocks) >= 2:
        active_duration_s = max(0.0, shocks[-1][0] - shocks[0][0]) / 1000.0
    high_density_per_min = (
        0.0 if active_duration_s <= 0.0 else len(high) * 60.0 / active_duration_s
    )
    top_count = max(1, int(math.ceil(len(shock_values) * 0.10))) if shock_values else 0
    top_mean = (
        None
        if top_count == 0
        else sum(sorted(shock_values, reverse=True)[:top_count]) / top_count
    )

    peak = _quantile(shock_values, 0.95)
    peak_gate = _clamp((peak or 0.0) / 0.62, 0.0, 1.20)
    top_gate = _clamp((top_mean or 0.0) / 0.58, 0.0, 1.20)
    repeat_gate = _clamp(high_density_per_min / 24.0, 0.0, 1.0)
    share_gate = _clamp((high_share or 0.0) / 0.24, 0.0, 1.0)
    chain_gate = _clamp((longest_chain_count - 1.0) / 8.0, 0.0, 1.0)
    window_p90 = _quantile(window_loads, 0.90)
    window_gate = _clamp((window_p90 or 0.0) / 4.2, 0.0, 1.0)
    control_index = _clamp(
        0.34 * peak_gate
        + 0.20 * top_gate
        + 0.14 * repeat_gate
        + 0.12 * share_gate
        + 0.10 * chain_gate
        + 0.10 * window_gate,
        0.0,
        1.20,
    )

    return {
        "v092_control_transition_count": len(shocks),
        "v092_control_shock_p95": peak,
        "v092_control_shock_top10_mean": top_mean,
        "v092_control_high_threshold": high_threshold,
        "v092_control_high_transition_share": high_share,
        "v092_control_high_density_per_min": high_density_per_min,
        "v092_control_longest_chain_count": longest_chain_count,
        "v092_control_longest_chain_duration_ms": longest_chain_duration_ms,
        "v092_control_window_5s_load_p90": window_p90,
        "v092_control_turn_severity_p95": _quantile(turn_terms, 0.95),
        "v092_control_velocity_change_p95": _quantile(speed_terms, 0.95),
        "v092_control_spacing_change_p95": _quantile(spacing_terms, 0.95),
        "v092_control_stable_cadence_spacing_p95": _quantile(stable_spacing_terms, 0.95),
        "v092_control_cadence_change_p95": _quantile(cadence_terms, 0.95),
        "v092_control_rhythm_movement_coupling_p95": _quantile(coupling_terms, 0.95),
        "v092_control_index": control_index,
    }


def _sustain_pressure_components(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the shared pressure timeline for Stamina and Endurance."""

    first_time_ms: float | None = None
    last_time_ms: float | None = None
    pressures: list[float] = []
    circle_tapping_pressures: list[float] = []
    effective_pressure_ms = 0.0
    high_pressure_ms = 0.0
    recovery_ms = 0.0
    longest_effective_ms = 0.0
    current_effective_ms = 0.0
    longest_circle_tapping_ms = 0.0
    current_circle_tapping_ms = 0.0
    circle_pair_effective_ms = 0.0
    circle_count = 0
    transition_count = 0
    segment_effective_values: list[float] = []
    segment_wall_values: list[float] = []
    segment_high_values: list[float] = []
    current_segment_effective_ms = 0.0
    current_segment_wall_ms = 0.0
    current_segment_high_ms = 0.0
    in_pressure_segment = False
    previous_circle = False

    def finish_segment() -> None:
        nonlocal current_segment_effective_ms
        nonlocal current_segment_wall_ms
        nonlocal current_segment_high_ms
        if current_segment_effective_ms > 0.0:
            segment_effective_values.append(current_segment_effective_ms)
            segment_wall_values.append(current_segment_wall_ms)
            segment_high_values.append(current_segment_high_ms)
        current_segment_effective_ms = 0.0
        current_segment_wall_ms = 0.0
        current_segment_high_ms = 0.0

    for row in rows:
        object_type = row.get("ls.object_type")
        if object_type == "spinner":
            finish_segment()
            current_effective_ms = 0.0
            current_circle_tapping_ms = 0.0
            in_pressure_segment = False
            previous_circle = False
            continue
        time_ms = _finite(row.get("ls.start_time_ms"))
        if time_ms is not None:
            first_time_ms = time_ms if first_time_ms is None else min(first_time_ms, time_ms)
            last_time_ms = time_ms if last_time_ms is None else max(last_time_ms, time_ms)
        is_circle = object_type == "circle"
        circle_count += int(is_circle)

        interval = _finite(row.get("ls.adjusted_delta_time_ms"))
        jump_time = _finite(row.get("ls.minimum_jump_time_ms"))
        distance = _finite(row.get("ls.jump_distance_raw_px"))
        angle = _finite(row.get("ls.slider_aware_angle_rad"))
        if (
            interval is None
            or jump_time is None
            or distance is None
            or interval <= 0.0
            or jump_time <= 0.0
            or distance < 0.0
        ):
            finish_segment()
            current_effective_ms = 0.0
            current_circle_tapping_ms = 0.0
            in_pressure_segment = False
            previous_circle = is_circle
            continue

        transition_count += 1
        tapping_rate = 1000.0 / max(interval, C.MIN_TIME_MS)
        tapping = _clamp((tapping_rate - 2.5) / 7.5, 0.0, 1.25)
        velocity = distance / max(jump_time, C.MIN_TIME_MS)
        movement_speed = _clamp((velocity - 0.25) / 2.5, 0.0, 1.25)
        movement_spacing = _clamp((distance - 50.0) / 250.0, 0.0, 1.20)
        movement = 0.68 * movement_speed + 0.32 * movement_spacing
        turn = 0.0 if angle is None else _clamp(1.0 - angle / math.pi, 0.0, 1.0)
        control = movement * (0.35 + 0.65 * turn)
        pressure = max(
            tapping,
            0.72 * movement + 0.28 * control,
            0.55 * tapping + 0.45 * movement,
        )
        pressure_gate = _clamp((pressure - 0.20) / 0.75, 0.0, 1.0)
        support_ms = min(interval, 500.0)
        effective_pressure_ms += support_ms * pressure_gate
        if pressure_gate >= 0.40:
            high_pressure_ms += support_ms
        pressures.append(pressure)

        continuous = interval <= 650.0 and pressure_gate >= 0.12
        if continuous:
            in_pressure_segment = True
            weighted_support_ms = support_ms * pressure_gate
            current_effective_ms += weighted_support_ms
            current_segment_effective_ms += weighted_support_ms
            current_segment_wall_ms += support_ms
            if pressure_gate >= 0.40:
                current_segment_high_ms += support_ms
            longest_effective_ms = max(longest_effective_ms, current_effective_ms)
        else:
            finish_segment()
            recovery_ms += interval
            current_effective_ms = 0.0
            in_pressure_segment = False

        if is_circle and previous_circle:
            circle_tapping_gate = _clamp((tapping - 0.10) / 0.90, 0.0, 1.0)
            circle_tapping_pressures.append(tapping)
            circle_pair_effective_ms += support_ms * pressure_gate
            if interval <= 350.0 and circle_tapping_gate >= 0.15:
                current_circle_tapping_ms += support_ms * circle_tapping_gate
                longest_circle_tapping_ms = max(
                    longest_circle_tapping_ms, current_circle_tapping_ms
                )
            else:
                current_circle_tapping_ms = 0.0
        else:
            current_circle_tapping_ms = 0.0
        previous_circle = is_circle

    finish_segment()

    active_duration_ms = (
        0.0
        if first_time_ms is None or last_time_ms is None
        else max(0.0, last_time_ms - first_time_ms)
    )
    coverage = (
        None
        if active_duration_ms <= 0.0
        else _clamp(effective_pressure_ms / active_duration_ms, 0.0, 1.0)
    )
    recovery_ratio = (
        None
        if active_duration_ms <= 0.0
        else _clamp(recovery_ms / active_duration_ms, 0.0, 1.0)
    )
    qualifying_segments = [value for value in segment_effective_values if value >= 750.0]
    repeated_section_effective_ms = sum(min(value, 12_000.0) for value in qualifying_segments)
    ordered_segments = sorted(segment_effective_values, reverse=True)
    return {
        "v092_pressure_transition_count": transition_count,
        "v092_pressure_active_duration_ms": active_duration_ms,
        "v092_pressure_effective_duration_ms": effective_pressure_ms,
        "v092_pressure_high_duration_ms": high_pressure_ms,
        "v092_pressure_coverage": coverage,
        "v092_pressure_recovery_duration_ms": recovery_ms,
        "v092_pressure_recovery_ratio": recovery_ratio,
        "v092_pressure_segment_count": len(segment_effective_values),
        "v092_pressure_qualifying_segment_count": len(qualifying_segments),
        "v092_pressure_repeated_section_effective_ms": repeated_section_effective_ms,
        "v092_pressure_top3_segment_effective_ms": sum(ordered_segments[:3]),
        "v092_pressure_segment_effective_p75_ms": _quantile(segment_effective_values, 0.75),
        "v092_pressure_segment_effective_p90_ms": _quantile(segment_effective_values, 0.90),
        "v092_pressure_longest_segment_wall_ms": max(segment_wall_values, default=0.0),
        "v092_pressure_segment_high_total_ms": sum(segment_high_values),
        "v092_pressure_longest_continuous_effective_ms": longest_effective_ms,
        "v092_pressure_p90": _quantile(pressures, 0.90),
        "v092_pressure_p95": _quantile(pressures, 0.95),
        "v092_pressure_circle_share": None if not rows else circle_count / len(rows),
        "v092_pressure_circle_pair_effective_ms": circle_pair_effective_ms,
        "v092_pressure_longest_circle_tapping_effective_ms": longest_circle_tapping_ms,
        "v092_pressure_circle_tapping_p90": _quantile(circle_tapping_pressures, 0.90),
    }


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Optional[dict[str, Any]] = None,
    difficulty: Optional[dict[str, Any]] = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    rows = list(local_rows)
    components, warnings = v091.extract_components(
        rows,
        features,
        difficulty=difficulty,
        clock_rate=clock_rate,
        effective_mods=effective_mods,
    )
    jump = _jump_movement_components(rows)
    movement = _movement_control_components(rows)
    sustain = _sustain_pressure_components(rows)
    components.update(jump)
    components.update(movement)
    components.update(sustain)
    if jump["v092_jump_transition_count"] < 3:
        warnings.append("v092 jump: fewer than three valid movement transitions")
    if movement["v092_control_transition_count"] < 3:
        warnings.append("v092 aim control: fewer than three valid movement transitions")
    if sustain["v092_pressure_transition_count"] < 3:
        warnings.append("v092 sustain: fewer than three valid pressure transitions")
    return components, warnings


def _axis_stars(axes: dict[str, Any], axis: str) -> float | None:
    return v091._axis_stars(axes, axis)


def _apply_jump_movement_tail(
    axes: dict[str, Any], components: dict[str, Any], anchor: float | None
) -> None:
    item = axes.get("jump_aim")
    incoming = _axis_stars(axes, "jump_aim")
    tail_gate = _finite(components.get("v092_jump_tail_gate"))
    tail_activation = _finite(components.get("v092_jump_tail_activation"))
    transitions = _finite(components.get("v092_jump_transition_count"))
    if (
        not isinstance(item, dict)
        or incoming is None
        or tail_gate is None
        or tail_activation is None
        or transitions is None
        or transitions < 3
    ):
        return
    scale_anchor = anchor if anchor is not None else v091._estimate_anchor(axes)
    if scale_anchor is None:
        return

    # Ordinary or isolated jumps retain V0.91.  A persistent high-distance,
    # high-speed chain can recover the otherwise saturated NM tail up to a
    # small specialist margin around total SR.
    floor_multiplier = (
        0.0
        if tail_activation <= 0.05
        else 0.75 + 0.27 * _clamp(tail_activation, 0.0, 1.0)
    )
    mechanic_floor = scale_anchor * floor_multiplier
    anchored_floor = (
        0.0
        if floor_multiplier == 0.0
        else v091._soft_anchor(mechanic_floor, scale_anchor)
    )
    adjusted = max(incoming, anchored_floor)
    item["demand_star_equivalent"] = adjusted
    item["score"] = adjusted / 10.0
    item["percentile_rank"] = None
    item["scale_method"] = "SOFT_TOTAL_SR_ANCHOR_AFTER_JUMP_TAIL_V092"
    item["method"] = "DISTANCE_SPEED_PERSISTENT_JUMP_TAIL_V092"
    item.setdefault("evidence", []).append(
        {
            "component": "v092_distance_speed_persistent_jump_tail",
            "incoming_v091_stars": incoming,
            "scale_anchor_stars": scale_anchor,
            "tail_gate": tail_gate,
            "tail_activation": tail_activation,
            "floor_multiplier": floor_multiplier,
            "mechanic_floor_before_anchor": mechanic_floor,
            "anchored_mechanic_floor_stars": anchored_floor,
            "adjusted_stars": adjusted,
            "transition_count": int(transitions),
            "distance_p95_px": components.get("v092_jump_distance_raw_p95_px"),
            "distance_p99_px": components.get("v092_jump_distance_raw_p99_px"),
            "velocity_p95_px_per_ms": components.get(
                "v092_jump_velocity_raw_p95_px_per_ms"
            ),
            "velocity_p99_px_per_ms": components.get(
                "v092_jump_velocity_raw_p99_px_per_ms"
            ),
            "joint_load_p95": components.get("v092_jump_joint_load_p95"),
            "joint_load_p99": components.get("v092_jump_joint_load_p99"),
            "high_transition_share": components.get(
                "v092_jump_high_transition_share"
            ),
            "longest_chain_count": components.get("v092_jump_longest_chain_count"),
            "longest_chain_duration_ms": components.get(
                "v092_jump_longest_chain_duration_ms"
            ),
            "evidence_tag": "HEURISTIC_V092_REQUIRES_HUMAN_VALIDATION",
        }
    )


def _apply_movement_control_state(
    axes: dict[str, Any], components: dict[str, Any], anchor: float | None
) -> None:
    item = axes.get("aim_control")
    incoming = _axis_stars(axes, "aim_control")
    index = _finite(components.get("v092_control_index"))
    transitions = _finite(components.get("v092_control_transition_count"))
    if (
        not isinstance(item, dict)
        or incoming is None
        or index is None
        or transitions is None
        or transitions < 3
    ):
        return

    scale_anchor = anchor if anchor is not None else v091._estimate_anchor(axes)
    if scale_anchor is None:
        return
    # Control evidence establishes how much of the map's total difficulty may
    # legitimately be attributed to Aim Control.  It does not multiply total
    # SR into an automatic specialist score: a strong, persistent control
    # timeline approaches the map anchor, while only exceptionally large
    # spacing-state shocks receive a small amount of specialist headroom.
    control_gate = _clamp((index - 0.45) / 0.55, 0.0, 1.0)
    stable_spacing = _finite(
        components.get("v092_control_stable_cadence_spacing_p95")
    ) or 0.0
    high_share = _finite(components.get("v092_control_high_transition_share")) or 0.0
    spacing_specialist = (
        _clamp((stable_spacing - 0.80) / 0.80, 0.0, 1.0)
        * _clamp(high_share / 0.30, 0.0, 1.0)
    )
    jump_tail_activation = _finite(
        components.get("v092_jump_tail_activation")
    ) or 0.0
    jump_separation = (
        0.10
        * _clamp(jump_tail_activation, 0.0, 1.0)
        * (1.0 - spacing_specialist)
    )
    floor_multiplier = (
        0.70 + 0.26 * control_gate + 0.08 * spacing_specialist - jump_separation
    )
    mechanic_floor = scale_anchor * floor_multiplier
    anchored_floor = v091._soft_anchor(mechanic_floor, scale_anchor)
    # ``incoming`` has already passed V0.91's anchor.  Anchor only the new
    # floor, otherwise applying the same saturating transform twice would
    # silently lower valid V0.91 values.
    adjusted = max(incoming, anchored_floor)
    item["demand_star_equivalent"] = adjusted
    item["score"] = adjusted / 10.0
    item["percentile_rank"] = None
    item["scale_method"] = "SOFT_TOTAL_SR_ANCHOR_AFTER_MOVEMENT_STATE_V092"
    item["method"] = "UNIFIED_MOVEMENT_CONTROL_STATE_V092"
    item.setdefault("evidence", []).append(
        {
            "component": "v092_unified_movement_control_state",
            "incoming_v091_stars": incoming,
            "scale_anchor_stars": scale_anchor,
            "control_index": index,
            "control_gate": control_gate,
            "spacing_specialist_gate": spacing_specialist,
            "jump_tail_separation": jump_separation,
            "floor_multiplier": floor_multiplier,
            "mechanic_floor_before_anchor": mechanic_floor,
            "anchored_mechanic_floor_stars": anchored_floor,
            "adjusted_stars": adjusted,
            "transition_count": int(transitions),
            "shock_p95": components.get("v092_control_shock_p95"),
            "shock_top10_mean": components.get("v092_control_shock_top10_mean"),
            "high_transition_share": components.get("v092_control_high_transition_share"),
            "high_density_per_min": components.get("v092_control_high_density_per_min"),
            "longest_chain_count": components.get("v092_control_longest_chain_count"),
            "longest_chain_duration_ms": components.get("v092_control_longest_chain_duration_ms"),
            "window_5s_load_p90": components.get("v092_control_window_5s_load_p90"),
            "turn_severity_p95": components.get("v092_control_turn_severity_p95"),
            "velocity_change_p95": components.get("v092_control_velocity_change_p95"),
            "spacing_change_p95": components.get("v092_control_spacing_change_p95"),
            "stable_cadence_spacing_p95": components.get("v092_control_stable_cadence_spacing_p95"),
            "cadence_change_p95": components.get("v092_control_cadence_change_p95"),
            "rhythm_movement_coupling_p95": components.get(
                "v092_control_rhythm_movement_coupling_p95"
            ),
            "evidence_tag": "HEURISTIC_V092_REQUIRES_HUMAN_VALIDATION",
        }
    )


def _physical_intensity(axes: dict[str, Any]) -> float | None:
    values = sorted(
        (
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
        ),
        reverse=True,
    )
    return None if len(values) < 2 else (values[0] + values[1]) / 2.0


def _diminishing_duration_load(duration_s: float, half_s: float) -> float:
    duration = max(0.0, float(duration_s))
    half = max(1.0, float(half_s))
    return duration / (duration + half)


def _apply_stamina_timeline(axes: dict[str, Any], components: dict[str, Any]) -> None:
    item = axes.get("stamina")
    incoming = _axis_stars(axes, "stamina")
    intensity = _physical_intensity(axes)
    longest_ms = _finite(components.get("v092_pressure_longest_continuous_effective_ms"))
    tapping_ms = _finite(
        components.get("v092_pressure_longest_circle_tapping_effective_ms")
    )
    coverage = _finite(components.get("v092_pressure_coverage"))
    pressure_p90 = _finite(components.get("v092_pressure_p90"))
    effective_ms = _finite(components.get("v092_pressure_effective_duration_ms"))
    repeated_ms = _finite(
        components.get("v092_pressure_repeated_section_effective_ms")
    )
    qualifying_segments = _finite(
        components.get("v092_pressure_qualifying_segment_count")
    )
    if (
        not isinstance(item, dict)
        or incoming is None
        or intensity is None
        or None
        in (
            longest_ms,
            tapping_ms,
            coverage,
            pressure_p90,
            effective_ms,
            repeated_ms,
            qualifying_segments,
        )
    ):
        return

    longest_s = max(0.0, float(longest_ms)) / 1000.0
    tapping_s = max(0.0, float(tapping_ms)) / 1000.0
    effective_s = max(0.0, float(effective_ms)) / 1000.0
    repeated_s = max(0.0, float(repeated_ms)) / 1000.0
    continuous_load = _diminishing_duration_load(longest_s, 6.0)
    tapping_chain_load = _diminishing_duration_load(tapping_s, 4.0)
    effective_load = _diminishing_duration_load(effective_s, 60.0)
    repeated_duration_load = _diminishing_duration_load(repeated_s, 30.0)
    repetition_gate = 1.0 - math.exp(-max(0.0, float(qualifying_segments)) / 8.0)
    repeated_section_load = repeated_duration_load * (0.65 + 0.35 * repetition_gate)
    coverage_load = math.sqrt(_clamp(float(coverage), 0.0, 1.0))
    sustain_load = _clamp(
        0.34 * continuous_load
        + 0.20 * tapping_chain_load
        + 0.28 * repeated_section_load
        + 0.10 * coverage_load
        + 0.08 * effective_load,
        0.0,
        1.0,
    )
    activity_floor = 0.44 + 0.06 * max(repeated_section_load, coverage_load)
    sustain_multiplier = activity_floor + 0.48 * sustain_load
    peak_gate = _clamp(float(pressure_p90), 0.0, 1.0)
    value = min(
        10.0,
        intensity * sustain_multiplier
        + 0.55 * peak_gate * math.sqrt(repeated_section_load),
    )
    item["demand_star_equivalent"] = value
    item["score"] = value / 10.0
    item["percentile_rank"] = None
    item["scale_method"] = "BOUNDED_PRESSURE_TIMELINE_STAMINA_0_10_V0922"
    item["method"] = "CONTINUOUS_AND_REPEATED_PRESSURE_STAMINA_V0922"
    item["combination_policy"] = "INTENSITY_X_CONTINUOUS_PLUS_REPEATED_SECTION_BURDEN_V0922"
    item.setdefault("evidence", []).append(
        {
            "component": "v0922_stamina_pressure_timeline",
            "incoming_v091_value_diagnostic_only": incoming,
            "physical_intensity_stars": intensity,
            "longest_continuous_effective_s": longest_s,
            "longest_circle_tapping_effective_s": tapping_s,
            "effective_pressure_s": effective_s,
            "repeated_section_effective_s": repeated_s,
            "qualifying_segment_count": int(float(qualifying_segments)),
            "pressure_coverage": coverage,
            "pressure_p90": pressure_p90,
            "continuous_load": continuous_load,
            "tapping_chain_load": tapping_chain_load,
            "effective_load": effective_load,
            "repeated_duration_load": repeated_duration_load,
            "repetition_gate": repetition_gate,
            "repeated_section_load": repeated_section_load,
            "coverage_load": coverage_load,
            "sustain_load": sustain_load,
            "activity_floor": activity_floor,
            "sustain_multiplier": sustain_multiplier,
            "adjusted_value": value,
            "evidence_tag": "HEURISTIC_V0922_REQUIRES_HUMAN_VALIDATION",
        }
    )


def _endurance_timeline_axis(
    axes: dict[str, Any], components: dict[str, Any]
) -> dict[str, Any]:
    intensity = _physical_intensity(axes)
    active_ms = _finite(components.get("v092_pressure_active_duration_ms"))
    effective_ms = _finite(components.get("v092_pressure_effective_duration_ms"))
    longest_ms = _finite(components.get("v092_pressure_longest_continuous_effective_ms"))
    coverage = _finite(components.get("v092_pressure_coverage"))
    recovery_ratio = _finite(components.get("v092_pressure_recovery_ratio"))
    segment_count = _finite(components.get("v092_pressure_segment_count"))
    qualifying_segments = _finite(
        components.get("v092_pressure_qualifying_segment_count")
    )
    repeated_ms = _finite(
        components.get("v092_pressure_repeated_section_effective_ms")
    )
    top3_ms = _finite(components.get("v092_pressure_top3_segment_effective_ms"))
    high_ms = _finite(components.get("v092_pressure_high_duration_ms"))
    missing = [
        name
        for name, value in (
            ("physical_intensity", intensity),
            ("active_duration_ms", active_ms),
            ("effective_pressure_ms", effective_ms),
            ("longest_continuous_effective_ms", longest_ms),
            ("pressure_coverage", coverage),
            ("recovery_ratio", recovery_ratio),
            ("pressure_segment_count", segment_count),
            ("qualifying_pressure_segment_count", qualifying_segments),
            ("repeated_section_effective_ms", repeated_ms),
            ("top3_segment_effective_ms", top3_ms),
            ("high_pressure_ms", high_ms),
        )
        if value is None
    ]
    if missing:
        return {
            "score": None,
            "status": "INSUFFICIENT_EVIDENCE",
            "confidence": "LOW",
            "method": "SECTION_AGGREGATED_PRESSURE_ENDURANCE_V0922",
            "combination_policy": "DURATION_COVERAGE_REPEATED_SECTIONS_RECOVERY_V0922",
            "signals": {},
            "warnings": [f"missing_signal:{name}" for name in missing],
            "evidence": [],
        }

    active_s = max(0.0, float(active_ms)) / 1000.0
    effective_s = max(0.0, float(effective_ms)) / 1000.0
    longest_s = max(0.0, float(longest_ms)) / 1000.0
    repeated_s = max(0.0, float(repeated_ms)) / 1000.0
    top3_s = max(0.0, float(top3_ms)) / 1000.0
    high_s = max(0.0, float(high_ms)) / 1000.0
    coverage_value = _clamp(float(coverage), 0.0, 1.0)
    effective_load = _diminishing_duration_load(effective_s, 120.0)
    length_load = _diminishing_duration_load(active_s, 180.0)
    continuous_segment_load = _diminishing_duration_load(longest_s, 20.0)
    repeated_section_load = _diminishing_duration_load(repeated_s, 75.0)
    top3_section_load = _diminishing_duration_load(top3_s, 45.0)
    high_pressure_load = _diminishing_duration_load(high_s, 120.0)
    repetition_gate = 1.0 - math.exp(-max(0.0, float(qualifying_segments)) / 10.0)
    section_burden = (
        0.65 * top3_section_load
        + 0.35 * repeated_section_load * (0.70 + 0.30 * repetition_gate)
    )
    recovery_relief = _clamp(float(recovery_ratio) / 0.45, 0.0, 1.0)
    uniform_specialisation = coverage_value * _clamp(longest_s / 120.0, 0.0, 1.0)
    base_load = (
        0.32 * effective_load
        + 0.18 * length_load * math.sqrt(coverage_value)
        + 0.14 * coverage_value
        + 0.22 * section_burden
        + 0.08 * continuous_segment_load
        + 0.06 * high_pressure_load
    )
    recovery_adjusted_load = base_load * (1.0 - 0.05 * recovery_relief)
    intensity_gate = _clamp((float(intensity) - 3.0) / 5.0, 0.0, 1.0)
    pressure_burden = effective_load * (0.55 + 0.45 * intensity_gate)
    endurance_load = _clamp(
        recovery_adjusted_load
        + 0.18 * pressure_burden
        + 0.30 * uniform_specialisation,
        0.0,
        1.0,
    )
    value = 10.0 * _clamp(
        endurance_load * (0.82 + 0.18 * intensity_gate)
        + 0.08 * uniform_specialisation,
        0.0,
        1.0,
    )
    return {
        "score": value / 10.0,
        "demand_star_equivalent": value,
        "percentile_rank": None,
        "scale_method": "BOUNDED_SECTION_PRESSURE_ENDURANCE_0_10_V0922",
        "status": "EMITTED",
        "confidence": "LOW",
        "method": "SECTION_AGGREGATED_PRESSURE_ENDURANCE_V0922",
        "combination_policy": "DURATION_COVERAGE_REPEATED_SECTIONS_RECOVERY_V0922",
        "signals": {
            "physical_intensity_stars": intensity,
            "active_duration_ms": active_ms,
            "effective_pressure_duration_ms": effective_ms,
            "longest_continuous_effective_ms": longest_ms,
            "pressure_coverage": coverage,
            "recovery_ratio": recovery_ratio,
            "pressure_segment_count": int(float(segment_count)),
            "qualifying_pressure_segment_count": int(float(qualifying_segments)),
            "repeated_section_effective_ms": repeated_ms,
            "top3_segment_effective_ms": top3_ms,
            "high_pressure_duration_ms": high_ms,
        },
        "warnings": [],
        "evidence": [
            {
                "component": "v0922_endurance_pressure_timeline",
                "active_duration_s": active_s,
                "effective_pressure_s": effective_s,
                "longest_continuous_effective_s": longest_s,
                "effective_pressure_load": effective_load,
                "diminishing_length_load": length_load,
                "coverage": coverage_value,
                "continuous_segment_load": continuous_segment_load,
                "repeated_section_load": repeated_section_load,
                "top3_section_load": top3_section_load,
                "high_pressure_load": high_pressure_load,
                "repetition_gate": repetition_gate,
                "section_burden": section_burden,
                "recovery_relief": recovery_relief,
                "uniform_specialisation": uniform_specialisation,
                "base_load": base_load,
                "recovery_adjusted_load": recovery_adjusted_load,
                "pressure_burden": pressure_burden,
                "endurance_load": endurance_load,
                "intensity_gate": intensity_gate,
                "adjusted_value": value,
                "evidence_tag": "HEURISTIC_V0922_REQUIRES_HUMAN_VALIDATION",
            }
        ],
    }


def classify_axes(axes: dict[str, Any]) -> dict[str, Any]:
    """Classify star-equivalent skills; expose bounded sustain as auxiliary."""

    primary_axes = dict(axes)
    for axis in _BOUNDED_AUXILIARY_AXES:
        primary_axes[axis] = {"status": "SCALE_EXCLUDED_FROM_PRIMARY_DOMINANCE"}
    result = classify_v08(primary_axes)
    result["policy_id"] = "HEURISTIC_STAR_AXIS_DOMINANCE_WITH_BOUNDED_AUXILIARY_V092"
    result["scale_policy"] = {
        "primary_competition": list(_STAR_AXES),
        "auxiliary_bounded_axes": list(_BOUNDED_AUXILIARY_AXES),
    }
    result["auxiliary_traits"] = {
        axis: _axis_stars(axes, axis) for axis in _BOUNDED_AUXILIARY_AXES
    }
    return result


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
    output = v091.analyze_components(
        checksum=checksum,
        requested_mods=requested_mods,
        components=components,
        calibration=calibration,
        reference_diagnostics=reference_diagnostics,
        applied_mod_context=applied_mod_context,
        algorithm_id=algorithm_id,
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
    output.setdefault("diagnostics", {})["v092_base_map_demand_version"] = (
        v091.MAP_DEMAND_VERSION
    )
    output["diagnostics"]["v092_mechanism_spec"] = MECHANISM_SPEC
    if output.get("status") == "OK":
        anchor_data = output["diagnostics"].get("v091_star_anchor", {})
        anchor = _finite(anchor_data.get("stars")) if isinstance(anchor_data, dict) else None
        _apply_jump_movement_tail(output["axes"], components, anchor)
        _apply_movement_control_state(output["axes"], components, anchor)
        _apply_stamina_timeline(output["axes"], components)
        output["axes"]["endurance"] = _endurance_timeline_axis(
            output["axes"], components
        )
        output["summaries"] = derive_summaries(output["axes"])
        output["archetype"] = classify_axes(output["axes"])
    C.scan_finite(output, "model_v092.output")
    return output
