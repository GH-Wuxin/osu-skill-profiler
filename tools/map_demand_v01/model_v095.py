"""Map Demand V0.95: evidence-separated reading, tapping, aim, and precision.

V0.92.2 remains replayable.  This revision rebuilds four axes whose inherited
calibration tails still confused correlated mechanics:

* high AR is not positive Reading evidence by itself;
* Raw Speed requires compact, repeated fast tapping rather than map BPM or
  large-jump cadence;
* Aim Control measures changes in movement state and explicitly yields stable
  large-jump demand to Jump Aim;
* Spatial Precision measures target tolerance, settling, and micro-correction,
  never raw jump distance alone.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Optional

from . import contract as C
from . import model_v091 as v091
from . import model_v092 as v092

ALGORITHM_ID = "MAP_DEMAND_ATOMIC_V095"
MAP_DEMAND_VERSION = "0.9.5.0"
SCHEMA_VERSION = "map_demand_v0.9.5.0"
AXIS_SCHEMA_VERSION = v092.AXIS_SCHEMA_VERSION
AXIS_ORDER = v092.AXIS_ORDER
MECHANISM_SPEC = (
    "MAP_DEMAND_ATOMIC_V095:base=v0922_replay;"
    "reading=visibility_evidence_relative_low_ar_hd_no_high_ar_bonus;"
    "raw_speed=compact_repeated_fast_tapping_not_large_jump_cadence;"
    "aim_control=movement_state_change_with_stable_jump_separation;"
    "spatial_precision=target_tolerance_settling_micro_correction;"
    "sustain=recomputed_after_physical_axis_separation"
)

extract_from_path = v092.extract_from_path
sha256_file_bytes = v092.sha256_file_bytes


def _finite(value: Any) -> float | None:
    return v092._finite(value)


def _clamp(value: float, low: float, high: float) -> float:
    return v092._clamp(value, low, high)


def _quantile(values: list[float], q: float) -> float | None:
    return v092._quantile(values, q)


def calibration_id(base_calibration_id: str) -> str:
    payload = json.dumps(
        {"base_calibration_id": base_calibration_id, "mechanism_spec": MECHANISM_SPEC},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"mdoverlay_v095:{digest}"


def _compact_tapping_components(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Separate fast tapping from the cadence of large aim jumps.

    Raw Speed is a peak-capacity axis, so a short burst can qualify, but one
    isolated short interval cannot.  Distance is used only as a routing signal:
    compact circle-to-circle chains belong to tapping while large transitions
    belong primarily to Jump Aim.
    """

    loads: list[float] = []
    rates: list[float] = []
    compactness_values: list[float] = []
    fast_count = 0
    large_jump_count = 0
    eligible_count = 0
    longest_chain_count = 0
    longest_chain_duration_ms = 0.0
    chain_count = 0
    chain_start_ms = 0.0
    previous_circle = False

    for row in rows:
        is_circle = row.get("ls.object_type") == "circle"
        if not is_circle or not previous_circle:
            chain_count = 0
            previous_circle = is_circle
            continue
        time_ms = _finite(row.get("ls.start_time_ms"))
        interval = _finite(row.get("ls.adjusted_delta_time_ms"))
        distance = _finite(row.get("ls.jump_distance_raw_px"))
        radius = _finite(row.get("ls.radius_px"))
        if (
            time_ms is None
            or interval is None
            or distance is None
            or radius is None
            or interval <= 0.0
            or distance < 0.0
            or radius <= 0.0
        ):
            chain_count = 0
            previous_circle = is_circle
            continue

        eligible_count += 1
        distance_in_radii = distance / radius
        rate = 1000.0 / max(interval, C.MIN_TIME_MS)
        speed_gate = _clamp((rate - 3.25) / 7.0, 0.0, 1.25)
        compactness = _clamp((3.75 - distance_in_radii) / 2.75, 0.0, 1.0)
        load = speed_gate * compactness
        loads.append(load)
        rates.append(rate)
        compactness_values.append(compactness)
        if distance_in_radii >= 3.75:
            large_jump_count += 1

        fast = interval <= 220.0 and load >= 0.14
        if fast:
            fast_count += 1
            if chain_count == 0:
                chain_start_ms = time_ms
            chain_count += 1
            longest_chain_count = max(longest_chain_count, chain_count)
            longest_chain_duration_ms = max(
                longest_chain_duration_ms, time_ms - chain_start_ms
            )
        else:
            chain_count = 0
        previous_circle = is_circle

    severity = _clamp(((_quantile(loads, 0.90) or 0.0) - 0.08) / 0.72, 0.0, 1.0)
    chain_gate = _clamp((longest_chain_count - 2.0) / 10.0, 0.0, 1.0)
    count_gate = _clamp((fast_count - 2.0) / 20.0, 0.0, 1.0)
    persistence = 0.72 * chain_gate + 0.28 * count_gate
    evidence_gate = math.sqrt(severity * persistence)
    return {
        "v095_tapping_eligible_pair_count": eligible_count,
        "v095_tapping_fast_compact_pair_count": fast_count,
        "v095_tapping_compact_load_p90": _quantile(loads, 0.90),
        "v095_tapping_rate_p90_per_s": _quantile(rates, 0.90),
        "v095_tapping_compactness_p50": _quantile(compactness_values, 0.50),
        "v095_tapping_large_jump_pair_share": (
            None if eligible_count == 0 else large_jump_count / eligible_count
        ),
        "v095_tapping_longest_fast_chain_count": longest_chain_count,
        "v095_tapping_longest_fast_chain_duration_ms": longest_chain_duration_ms,
        "v095_tapping_severity_gate": severity,
        "v095_tapping_persistence_gate": persistence,
        "v095_tapping_evidence_gate": evidence_gate,
    }


def _control_state_components(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure changes in movement state, not absolute jump direction alone."""

    shocks: list[tuple[float, float]] = []
    spacing_terms: list[float] = []
    speed_terms: list[float] = []
    turn_change_terms: list[float] = []
    complex_turn_terms: list[float] = []
    large_jump_count = 0
    valid_count = 0
    previous_velocity: float | None = None
    previous_distance: float | None = None
    previous_interval: float | None = None
    previous_turn: float | None = None

    for row in rows:
        if row.get("ls.object_type") == "spinner":
            previous_velocity = previous_distance = previous_interval = previous_turn = None
            continue
        time_ms = _finite(row.get("ls.start_time_ms"))
        interval = _finite(row.get("ls.adjusted_delta_time_ms"))
        jump_time = _finite(row.get("ls.minimum_jump_time_ms"))
        distance = _finite(row.get("ls.jump_distance_raw_px"))
        angle = _finite(row.get("ls.slider_aware_angle_rad"))
        if (
            time_ms is None
            or interval is None
            or jump_time is None
            or distance is None
            or interval <= 0.0
            or jump_time <= 0.0
            or distance < 0.0
        ):
            continue
        velocity = distance / max(jump_time, C.MIN_TIME_MS)
        turn = 0.0 if angle is None else _clamp(1.0 - angle / math.pi, 0.0, 1.0)
        if None in (previous_velocity, previous_distance, previous_interval, previous_turn):
            previous_velocity = velocity
            previous_distance = distance
            previous_interval = interval
            previous_turn = turn
            continue

        valid_count += 1
        speed_change = _clamp(
            abs(math.log2((velocity + 0.12) / (float(previous_velocity) + 0.12))) / 1.35,
            0.0,
            1.5,
        )
        spacing_change = _clamp(
            abs(math.log2((distance + 16.0) / (float(previous_distance) + 16.0))) / 1.35,
            0.0,
            1.5,
        )
        cadence_change = _clamp(
            abs(math.log2(interval / float(previous_interval))) / 1.20,
            0.0,
            1.5,
        )
        stable_spacing = spacing_change * math.exp(-2.6 * cadence_change)
        turn_change = abs(turn - float(previous_turn))
        coupled_change = cadence_change * max(turn_change, speed_change, spacing_change)
        complex_turn = turn * (
            0.20 + 0.80 * max(turn_change, speed_change, stable_spacing)
        )
        movement_gate = _clamp(
            0.18
            + 0.52 * _clamp((velocity - 0.28) / 1.65, 0.0, 1.25)
            + 0.30 * _clamp((distance - 32.0) / 220.0, 0.0, 1.20),
            0.18,
            1.25,
        )
        state_change = (
            0.28 * speed_change
            + 0.30 * stable_spacing
            + 0.20 * turn_change
            + 0.14 * complex_turn
            + 0.08 * coupled_change
        )
        shock = movement_gate * state_change
        shocks.append((time_ms, shock))
        spacing_terms.append(stable_spacing)
        speed_terms.append(speed_change)
        turn_change_terms.append(turn_change)
        complex_turn_terms.append(complex_turn)
        if distance >= 120.0 and velocity >= 0.70:
            large_jump_count += 1

        previous_velocity = velocity
        previous_distance = distance
        previous_interval = interval
        previous_turn = turn

    values = [value for _, value in shocks]
    high = [(time_ms, value) for time_ms, value in shocks if value >= 0.18]
    longest_chain = 0
    chain = 0
    previous_time: float | None = None
    for time_ms, _ in high:
        chain = 1 if previous_time is None or time_ms - previous_time > 450.0 else chain + 1
        longest_chain = max(longest_chain, chain)
        previous_time = time_ms
    duration_s = (
        0.0
        if len(shocks) < 2
        else max(0.0, shocks[-1][0] - shocks[0][0]) / 1000.0
    )
    density = 0.0 if duration_s <= 0.0 else len(high) * 60.0 / duration_s
    top_count = max(1, int(math.ceil(len(values) * 0.10))) if values else 0
    top_mean = (
        None if top_count == 0 else sum(sorted(values, reverse=True)[:top_count]) / top_count
    )
    window_loads: list[float] = []
    left = 0
    running = 0.0
    for right, (time_ms, shock) in enumerate(shocks):
        running += shock
        while left <= right and time_ms - shocks[left][0] > 5000.0:
            running -= shocks[left][1]
            left += 1
        window_loads.append(running)
    peak_gate = _clamp(((_quantile(values, 0.95) or 0.0) - 0.08) / 0.62, 0.0, 1.2)
    top_gate = _clamp(((top_mean or 0.0) - 0.08) / 0.58, 0.0, 1.2)
    repeat_gate = _clamp(density / 24.0, 0.0, 1.0)
    chain_gate = _clamp((longest_chain - 1.0) / 8.0, 0.0, 1.0)
    window_gate = _clamp(((_quantile(window_loads, 0.90) or 0.0) - 0.4) / 3.8, 0.0, 1.0)
    index = _clamp(
        0.38 * peak_gate
        + 0.22 * top_gate
        + 0.15 * repeat_gate
        + 0.15 * chain_gate
        + 0.10 * window_gate,
        0.0,
        1.20,
    )
    return {
        "v095_control_transition_count": valid_count,
        "v095_control_shock_p95": _quantile(values, 0.95),
        "v095_control_top10_mean": top_mean,
        "v095_control_stable_spacing_p95": _quantile(spacing_terms, 0.95),
        "v095_control_speed_change_p95": _quantile(speed_terms, 0.95),
        "v095_control_turn_change_p95": _quantile(turn_change_terms, 0.95),
        "v095_control_complex_turn_p95": _quantile(complex_turn_terms, 0.95),
        "v095_control_high_density_per_min": density,
        "v095_control_longest_chain_count": longest_chain,
        "v095_control_window_5s_load_p90": _quantile(window_loads, 0.90),
        "v095_control_large_jump_share": (
            None if valid_count == 0 else large_jump_count / valid_count
        ),
        "v095_control_index": index,
    }


def _precision_components(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure small-target tolerance and explicit post-jump correction."""

    target_gates: list[float] = []
    settling_terms: list[float] = []
    micro_terms: list[float] = []
    valid = 0
    previous_distance: float | None = None
    previous_radius: float | None = None

    for row in rows:
        if row.get("ls.object_type") == "spinner":
            previous_distance = previous_radius = None
            continue
        dt = _finite(row.get("ls.minimum_jump_time_ms"))
        distance = _finite(row.get("ls.jump_distance_raw_px"))
        radius = _finite(row.get("ls.radius_px"))
        angle = _finite(row.get("ls.slider_aware_angle_rad"))
        if dt is None or distance is None or radius is None or dt <= 0.0 or radius <= 0.0:
            continue
        valid += 1
        target_gate = _clamp((36.5 - radius) / 15.0, 0.0, 1.20)
        velocity = distance / max(dt, C.MIN_TIME_MS)
        settling = target_gate * _clamp((velocity - 0.55) / 2.0, 0.0, 1.0)
        target_gates.append(target_gate)
        settling_terms.append(settling)

        if previous_distance is not None and previous_radius is not None:
            prior_radii = previous_distance / max(previous_radius, 1.0)
            correction_radii = distance / radius
            if (
                prior_radii >= 4.0
                and correction_radii <= 2.5
                and dt <= 250.0
                and (angle is None or angle <= math.pi / 2.0)
            ):
                micro_terms.append(
                    _clamp((prior_radii - 4.0) / 5.0, 0.0, 1.0)
                    * _clamp((2.5 - correction_radii) / 2.0, 0.0, 1.0)
                    * _clamp((250.0 - dt) / 170.0, 0.0, 1.0)
                )
        previous_distance = distance
        previous_radius = radius

    target = _quantile(target_gates, 0.75) or 0.0
    settling = _quantile(settling_terms, 0.90) or 0.0
    micro_severity = _quantile(micro_terms, 0.90) or 0.0
    micro_repeat = _clamp(len(micro_terms) / 12.0, 0.0, 1.0)
    micro_gate = math.sqrt(micro_severity * micro_repeat)
    index = _clamp(0.52 * target + 0.20 * settling + 0.28 * micro_gate, 0.0, 1.20)
    return {
        "v095_precision_transition_count": valid,
        "v095_precision_target_tolerance_p75": target,
        "v095_precision_settling_p90": settling,
        "v095_precision_micro_correction_count": len(micro_terms),
        "v095_precision_micro_correction_p90": micro_severity,
        "v095_precision_micro_repeat_gate": micro_repeat,
        "v095_precision_micro_gate": micro_gate,
        "v095_precision_index": index,
    }


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Optional[dict[str, Any]] = None,
    difficulty: Optional[dict[str, Any]] = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    rows = list(local_rows)
    components, warnings = v092.extract_components(
        rows,
        features,
        difficulty=difficulty,
        clock_rate=clock_rate,
        effective_mods=effective_mods,
    )
    tapping = _compact_tapping_components(rows)
    control = _control_state_components(rows)
    precision = _precision_components(rows)
    components.update(tapping)
    components.update(control)
    components.update(precision)
    if tapping["v095_tapping_eligible_pair_count"] < 3:
        warnings.append("v095 raw speed: fewer than three eligible circle pairs")
    if control["v095_control_transition_count"] < 3:
        warnings.append("v095 aim control: fewer than three state transitions")
    if precision["v095_precision_transition_count"] < 3:
        warnings.append("v095 spatial precision: fewer than three valid transitions")
    return components, warnings


def _axis_stars(axes: dict[str, Any], axis: str) -> float | None:
    return v092._axis_stars(axes, axis)


def _set_axis(
    axes: dict[str, Any], axis: str, stars: float, method: str, evidence: dict[str, Any]
) -> None:
    item = axes.get(axis)
    incoming = _axis_stars(axes, axis)
    if not isinstance(item, dict) or incoming is None:
        return
    value = max(0.0, float(stars))
    item["demand_star_equivalent"] = value
    item["score"] = value / 10.0
    item["percentile_rank"] = None
    item["scale_method"] = "V095_EVIDENCE_SEPARATED_STAR_SCALE"
    item["method"] = method
    item.setdefault("evidence", []).append(
        {
            "component": method,
            "incoming_v0922_stars": incoming,
            "adjusted_stars": value,
            **evidence,
            "evidence_tag": "HEURISTIC_V095_REQUIRES_HUMAN_VALIDATION",
        }
    )


def _apply_raw_speed(axes: dict[str, Any], components: dict[str, Any]) -> None:
    incoming = _axis_stars(axes, "raw_speed")
    evidence_gate = _finite(components.get("v095_tapping_evidence_gate"))
    if incoming is None or evidence_gate is None:
        return
    large_jump_share = _finite(
        components.get("v095_tapping_large_jump_pair_share")
    ) or 0.0
    # Keep the calibrated peak ordering and apply a bounded correction only
    # when its compact/repeated tapping evidence is absent.  V0.95 must not
    # turn an aim-heavy speed map's moderate tapping demand into near-zero.
    unsupported_jump_cadence = (
        (1.0 - _clamp(evidence_gate, 0.0, 1.0))
        * _clamp(large_jump_share / 0.75, 0.0, 1.0)
    )
    retention = 1.0 - 0.15 * unsupported_jump_cadence
    adjusted = incoming * retention
    _set_axis(
        axes,
        "raw_speed",
        adjusted,
        "COMPACT_REPEATED_FAST_TAPPING_V095",
        {
            "evidence_gate": evidence_gate,
            "unsupported_jump_cadence_gate": unsupported_jump_cadence,
            "retention_multiplier": retention,
            "compact_load_p90": components.get("v095_tapping_compact_load_p90"),
            "tapping_rate_p90_per_s": components.get("v095_tapping_rate_p90_per_s"),
            "compactness_p50": components.get("v095_tapping_compactness_p50"),
            "large_jump_pair_share": large_jump_share,
            "fast_compact_pair_count": components.get("v095_tapping_fast_compact_pair_count"),
            "longest_fast_chain_count": components.get("v095_tapping_longest_fast_chain_count"),
            "longest_fast_chain_duration_ms": components.get(
                "v095_tapping_longest_fast_chain_duration_ms"
            ),
        },
    )


def _apply_aim_control(
    axes: dict[str, Any], components: dict[str, Any], anchor: float | None
) -> None:
    incoming = _axis_stars(axes, "aim_control")
    index = _finite(components.get("v095_control_index"))
    if incoming is None or index is None or anchor is None:
        return
    control_gate = _clamp((index - 0.18) / 0.72, 0.0, 1.0)
    spacing = _finite(components.get("v095_control_stable_spacing_p95")) or 0.0
    spacing_specialist = _clamp((spacing - 0.65) / 0.75, 0.0, 1.0)
    large_jump_share = _finite(components.get("v095_control_large_jump_share")) or 0.0
    jump_tail = _finite(components.get("v092_jump_tail_activation")) or 0.0
    jump_specialist = (
        _clamp(large_jump_share / 0.65, 0.0, 1.0)
        * _clamp(jump_tail, 0.0, 1.0)
        * (1.0 - 0.70 * spacing_specialist)
    )
    effective_control_gate = control_gate * (1.0 - 0.32 * jump_specialist)
    stable_jump_separation = jump_specialist * (1.0 - 0.35 * control_gate)
    target_multiplier = (
        0.48
        + 0.58 * effective_control_gate
        + 0.10 * spacing_specialist
        - 0.08 * stable_jump_separation
    )
    target = anchor * target_multiplier
    inherited = min(incoming, anchor * (0.72 + 0.48 * effective_control_gate))
    # Only decisive evidence may substantially move the human-checked V0.92.2
    # ordering. Pure jump specialisation gets a strong downward separation;
    # strong spacing/state-change tech gets a moderate recovery; ambiguous maps
    # stay close to the inherited value.
    if jump_specialist >= 0.70 and spacing_specialist < 0.35:
        inherited_weight = 0.72
    elif control_gate >= 0.80 and spacing_specialist >= 0.35:
        inherited_weight = 0.90
    else:
        inherited_weight = 1.0
    adjusted = inherited_weight * inherited + (1.0 - inherited_weight) * target
    _set_axis(
        axes,
        "aim_control",
        adjusted,
        "MOVEMENT_STATE_CHANGE_JUMP_SEPARATED_CONTROL_V095",
        {
            "scale_anchor_stars": anchor,
            "control_index": index,
            "control_gate": control_gate,
            "effective_control_gate": effective_control_gate,
            "spacing_specialist_gate": spacing_specialist,
            "large_jump_share": large_jump_share,
            "jump_tail_activation": jump_tail,
            "jump_specialist_gate": jump_specialist,
            "stable_jump_separation_gate": stable_jump_separation,
            "target_multiplier": target_multiplier,
            "target_stars": target,
            "inherited_clipped_stars": inherited,
            "inherited_weight": inherited_weight,
            "shock_p95": components.get("v095_control_shock_p95"),
            "speed_change_p95": components.get("v095_control_speed_change_p95"),
            "turn_change_p95": components.get("v095_control_turn_change_p95"),
            "complex_turn_p95": components.get("v095_control_complex_turn_p95"),
            "stable_spacing_p95": spacing,
            "longest_chain_count": components.get("v095_control_longest_chain_count"),
        },
    )


def _apply_spatial_precision(
    axes: dict[str, Any], components: dict[str, Any], anchor: float | None
) -> None:
    incoming = _axis_stars(axes, "spatial_precision")
    index = _finite(components.get("v095_precision_index"))
    if incoming is None or index is None or anchor is None:
        return
    target_gate = _finite(
        components.get("v095_precision_target_tolerance_p75")
    ) or 0.0
    settling_gate = _finite(components.get("v095_precision_settling_p90")) or 0.0
    micro_gate = _finite(components.get("v095_precision_micro_gate")) or 0.0
    evidence_gate = _clamp(max(target_gate, settling_gate, micro_gate), 0.0, 1.0)
    # Precision already had useful human-checked ordering in V0.92.2. Apply a
    # maximum 8% correction when target/micro evidence is weak, and preserve
    # it almost entirely when either small targets or repeated corrections are
    # visible. V0.95 never creates a new total-SR floor for Precision: the
    # evidence gate may preserve an inherited value, not inflate it.
    retention = 0.92 + 0.08 * evidence_gate
    retained = incoming * retention
    adjusted = retained
    _set_axis(
        axes,
        "spatial_precision",
        adjusted,
        "TARGET_TOLERANCE_SETTLING_MICRO_CORRECTION_PRECISION_V095",
        {
            "scale_anchor_stars": anchor,
            "precision_index": index,
            "precision_evidence_gate": evidence_gate,
            "retention_multiplier": retention,
            "retained_stars": retained,
            "target_tolerance_p75": components.get(
                "v095_precision_target_tolerance_p75"
            ),
            "settling_p90": components.get("v095_precision_settling_p90"),
            "micro_correction_count": components.get(
                "v095_precision_micro_correction_count"
            ),
            "micro_correction_p90": components.get(
                "v095_precision_micro_correction_p90"
            ),
            "micro_repeat_gate": components.get("v095_precision_micro_repeat_gate"),
        },
    )


def _apply_reading(
    axes: dict[str, Any], components: dict[str, Any], mods: set[str]
) -> None:
    incoming = _axis_stars(axes, "reading")
    if incoming is None:
        return
    physical = sorted(
        (
            value
            for axis in (
                "jump_aim",
                "flow_aim",
                "aim_control",
                "spatial_precision",
                "raw_speed",
            )
            if (value := _axis_stars(axes, axis)) is not None
        ),
        reverse=True,
    )
    preempt = _finite(components.get("reading_preempt_median_ms"))
    overlap = _finite(components.get("v091_visible_overlap_load_p90"))
    cluster = _finite(components.get("v091_visible_cluster_load_p90"))
    stack_share = _finite(components.get("v091_visible_stack_object_share"))
    if len(physical) < 3 or None in (preempt, overlap, cluster, stack_share):
        return
    environment = sum(physical[:3]) / 3.0
    spatial_load = (
        0.55 * _clamp(float(overlap) / 1.8, 0.0, 1.0)
        + 0.25 * _clamp((float(cluster) - 1.0) / 5.0, 0.0, 1.0)
        + 0.20 * _clamp(float(stack_share) / 0.18, 0.0, 1.0)
    )
    required_preempt = _clamp(720.0 - 48.0 * (environment - 5.0), 320.0, 900.0)
    relative_low_ar = _clamp((float(preempt) / required_preempt - 1.0) / 0.65, 0.0, 1.0)
    high_ar_gate = _clamp((500.0 - float(preempt)) / 180.0, 0.0, 1.0)
    low_ar_gain = 1.05 * relative_low_ar * (0.30 + 0.70 * spatial_load)
    hd_gain = 0.0
    if "HD" in mods:
        hd_gain = 1.55 * (0.22 + 0.78 * spatial_load) * (
            0.30 + 0.70 * relative_low_ar
        )
    target = environment * (0.46 + 0.28 * spatial_load) + low_ar_gain + hd_gain
    visibility_gate = _clamp(
        max(spatial_load, relative_low_ar, 0.35 if "HD" in mods else 0.0),
        0.0,
        1.0,
    )
    # Preserve the evidence-backed baseline and attenuate only the unexplained
    # excess above it. This leaves ordinary 4-6 star Reading values alone while
    # preventing a high inherited calibration tail from treating high AR as a
    # specialist mechanic. HD, low AR, and dense visibility evidence retain
    # that excess progressively.
    evidence_baseline = max(target, 0.65 * environment)
    unexplained_excess = max(0.0, incoming - evidence_baseline)
    excess_retention = 0.35 + 0.65 * visibility_gate
    adjusted = min(incoming, evidence_baseline + unexplained_excess * excess_retention)
    _set_axis(
        axes,
        "reading",
        adjusted,
        "VISIBILITY_EVIDENCE_RELATIVE_LOW_AR_READING_V095",
        {
            "physical_environment_stars": environment,
            "actual_preempt_ms": preempt,
            "required_preempt_ms": required_preempt,
            "high_ar_gate_diagnostic_only": high_ar_gate,
            "spatial_visibility_load": spatial_load,
            "relative_low_ar_gate": relative_low_ar,
            "visibility_evidence_gate": visibility_gate,
            "evidence_baseline_stars": evidence_baseline,
            "unexplained_excess_stars": unexplained_excess,
            "excess_retention_multiplier": excess_retention,
            "low_ar_gain_stars": low_ar_gain,
            "hd_visibility_gain_stars": hd_gain,
            "evidence_target_stars": target,
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
    output = v092.analyze_components(
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
    output.setdefault("diagnostics", {})["v095_base_map_demand_version"] = (
        v092.MAP_DEMAND_VERSION
    )
    output["diagnostics"]["v095_mechanism_spec"] = MECHANISM_SPEC
    if output.get("status") == "OK":
        anchor_data = output["diagnostics"].get("v091_star_anchor", {})
        anchor = _finite(anchor_data.get("stars")) if isinstance(anchor_data, dict) else None
        if anchor is None:
            anchor = v091._estimate_anchor(output["axes"])
        _apply_raw_speed(output["axes"], components)
        _apply_aim_control(output["axes"], components, anchor)
        _apply_spatial_precision(output["axes"], components, anchor)
        # Stamina/Endurance depend on the physical axes. Recompute after Raw
        # Speed, Aim Control, and Precision have been separated.
        v092._apply_stamina_timeline(output["axes"], components)
        output["axes"]["endurance"] = v092._endurance_timeline_axis(
            output["axes"], components
        )
        _apply_reading(
            output["axes"], components, set(mod_context.get("effective_mods", []))
        )
        output["summaries"] = v092.derive_summaries(output["axes"])
        output["archetype"] = v092.classify_axes(output["axes"])
    C.scan_finite(output, "model_v095.output")
    return output
