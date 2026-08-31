"""Experimental decoupled nine-axis Map Demand layer.

This module is deliberately not the production default.  It reuses V0.96's
validated parsing/mod-transform contract, but every final axis is recomputed
from raw component evidence.  No axis calculator may read another axis score.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Optional

from . import contract as C
from . import model_v092 as v092
from . import model_v095 as v095
from . import model_v096 as v096

ALGORITHM_ID = "MAP_DEMAND_DECOUPLED_V01_R2"
MAP_DEMAND_VERSION = "0.9.6-decoupled.2"
SCHEMA_VERSION = "map_demand_v0.9.6-decoupled.2"
AXIS_SCHEMA_VERSION = v096.AXIS_SCHEMA_VERSION
AXIS_ORDER = v096.AXIS_ORDER
MECHANISM_SPEC = (
    "MAP_DEMAND_DECOUPLED_V01_R2:base=v096_contract_only;"
    "axis_dependencies=raw_components_only;"
    "morphology=post_mod_timeline_geometry_without_mapper_bpm_divisor;"
    "jump_flow=peak_first_with_wide_jump_shape_separation;"
    "reading=visibility_gated_structure_no_axis_score_inputs;"
    "precision=strict_post_jump_micro_correction_plus_signed_target_size;"
    "stamina=tapping_chain_only;"
    "endurance=raw_pressure_duration_only;"
    "scale=concave_total_sr_context_without_nonzero_axis_floor"
)

extract_from_path = v096.extract_from_path
sha256_file_bytes = v096.sha256_file_bytes


def _finite(value: Any) -> float | None:
    return v096._finite(value)


def _clamp(value: float, low: float, high: float) -> float:
    return v096._clamp(value, low, high)


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = _clamp(q, 0.0, 1.0) * (len(ordered) - 1)
    left = int(math.floor(position))
    right = int(math.ceil(position))
    if left == right:
        return ordered[left]
    weight = position - left
    return ordered[left] * (1.0 - weight) + ordered[right] * weight


def _independent_sequence_components(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract broad tapping/flow chains without compactness or axis scores.

    V0.95's tapping chain deliberately requires compact circle pairs.  That is
    useful for Raw Speed classification, but it makes spaced streams vanish
    from Stamina and Flow.  The decoupled experiment keeps its own note-chain
    facts so each consumer can apply its own mechanic-specific gate.
    """

    rates: list[float] = []
    intervals: list[tuple[float, float]] = []
    rapid_rates: list[float] = []
    rapid_chain_notes = 0
    longest_rapid_chain_notes = 0
    rapid_pair_count = 0

    flow_chain_notes = 0
    longest_flow_chain_notes = 0
    flow_pair_count = 0
    flow_rates: list[float] = []
    flow_distance_radii: list[float] = []
    reading_shocks: list[float] = []
    previous_reading_interval: float | None = None
    previous_reading_distance_radii: float | None = None
    previous_object_type: str | None = None
    previous_precision_distance: float | None = None
    previous_precision_radius: float | None = None
    precision_micro_terms: list[float] = []

    for row in rows:
        object_type = str(row.get("ls.object_type") or "")
        if object_type == "spinner":
            rapid_chain_notes = 0
            flow_chain_notes = 0
            previous_reading_interval = None
            previous_reading_distance_radii = None
            previous_object_type = None
            previous_precision_distance = None
            previous_precision_radius = None
            continue
        interval = _finite(row.get("ls.adjusted_delta_time_ms"))
        distance = _finite(row.get("ls.jump_distance_raw_px"))
        radius = _finite(row.get("ls.radius_px"))
        angle = _finite(row.get("ls.slider_aware_angle_rad"))
        if interval is None or interval <= 0.0:
            rapid_chain_notes = 0
            flow_chain_notes = 0
            previous_object_type = object_type
            if distance is not None and radius is not None and radius > 0.0:
                previous_precision_distance = distance
                previous_precision_radius = radius
            continue

        rate = 1000.0 / max(interval, C.MIN_TIME_MS)
        rates.append(rate)
        finger_weight = (
            1.0
            if object_type == "circle" and previous_object_type in {None, "circle"}
            # Slider starts still require a tap and slider-tech rhythm changes
            # are legitimate Finger Control evidence.  Down-weight them, but do
            # not erase them as the first R2 draft did.
            else 0.85
        )
        intervals.append((interval, finger_weight))
        rapid = interval <= 180.0
        if rapid:
            rapid_pair_count += 1
            rapid_rates.append(rate)
            rapid_chain_notes = 2 if rapid_chain_notes == 0 else rapid_chain_notes + 1
            longest_rapid_chain_notes = max(longest_rapid_chain_notes, rapid_chain_notes)
        else:
            rapid_chain_notes = 0

        if distance is None or radius is None or radius <= 0.0 or angle is None:
            flow_chain_notes = 0
            continue
        distance_radii = distance / radius
        if (
            previous_precision_distance is not None
            and previous_precision_radius is not None
        ):
            prior_radii = previous_precision_distance / max(
                previous_precision_radius, 1.0
            )
            # A correction must actually be micro.  The old 2.5-radius gate
            # admitted ordinary follow-up jumps and turned Aim Control into
            # Precision, especially on large-circle jump maps.
            if (
                prior_radii >= 4.0
                and distance_radii <= 1.60
                and interval <= 220.0
                and (angle is None or angle <= math.pi / 2.0)
            ):
                precision_micro_terms.append(
                    _clamp((prior_radii - 4.0) / 4.0, 0.0, 1.0)
                    * _clamp((1.60 - distance_radii) / 1.10, 0.0, 1.0)
                    * _clamp((220.0 - interval) / 150.0, 0.0, 1.0)
                )
        spacing_change = (
            0.0
            if previous_reading_distance_radii is None
            else _clamp(
                abs(
                    math.log2(
                        max(distance_radii, 0.10)
                        / max(previous_reading_distance_radii, 0.10)
                    )
                )
                / 1.50,
                0.0,
                1.0,
            )
        )
        cadence_change = (
            0.0
            if previous_reading_interval is None
            else _clamp(
                abs(math.log2(interval / previous_reading_interval)) / 1.50,
                0.0,
                1.0,
            )
        )
        turn_severity = _clamp(1.0 - angle / math.pi, 0.0, 1.0)
        reading_shocks.append(
            0.38 * spacing_change
            + 0.24 * cadence_change
            + 0.38 * turn_severity
        )
        previous_reading_interval = interval
        previous_reading_distance_radii = distance_radii
        # A deliberately broad continuous-aim gate.  Length and cursor speed
        # decide the demand later; this stage only says that a chain exists.
        continuous = (
            interval <= 220.0
            and angle >= math.pi / 2.0
            and 0.55 <= distance_radii <= 6.0
        )
        if continuous:
            flow_pair_count += 1
            flow_rates.append(rate)
            flow_distance_radii.append(distance_radii)
            flow_chain_notes = 2 if flow_chain_notes == 0 else flow_chain_notes + 1
            longest_flow_chain_notes = max(longest_flow_chain_notes, flow_chain_notes)
        else:
            flow_chain_notes = 0

        previous_object_type = object_type
        previous_precision_distance = distance
        previous_precision_radius = radius

    finger_changes: list[float] = []
    finger_complexity: list[float] = []
    switch_count = 0
    alternating_chain = 0
    longest_alternating_chain = 0
    previous_direction = 0
    for (previous, previous_weight), (current, current_weight) in zip(
        intervals, intervals[1:]
    ):
        evidence_weight = min(previous_weight, current_weight)
        if max(previous, current) > 250.0:
            previous_direction = 0
            alternating_chain = 0
            continue
        signed_ratio = math.log2(previous / current)
        magnitude = abs(signed_ratio)
        change = _clamp((magnitude - 0.06) / 0.94, 0.0, 1.0)
        common_distance = min(
            abs(magnitude - lattice) for lattice in (0.0, 0.5, 1.0, math.log2(1.5))
        )
        complexity = _clamp((common_distance - 0.05) / 0.20, 0.0, 1.0)
        finger_changes.append(change * evidence_weight)
        finger_complexity.append(complexity * evidence_weight)
        direction = 1 if signed_ratio > 0.08 else -1 if signed_ratio < -0.08 else 0
        if change >= 0.12:
            switch_count += evidence_weight
        if (
            evidence_weight >= 0.80
            and direction
            and previous_direction
            and direction != previous_direction
        ):
            alternating_chain = 2 if alternating_chain == 0 else alternating_chain + 1
            longest_alternating_chain = max(
                longest_alternating_chain, alternating_chain
            )
        elif evidence_weight >= 0.80 and direction:
            alternating_chain = 1
        else:
            alternating_chain = 0
        if direction:
            previous_direction = direction

    return {
        "decoupled_tapping_rate_p90_per_s": _quantile(rates, 0.90),
        "decoupled_tapping_rapid_rate_p90_per_s": _quantile(rapid_rates, 0.90),
        "decoupled_tapping_rapid_pair_count": rapid_pair_count,
        "decoupled_tapping_transition_count": len(intervals),
        "decoupled_tapping_longest_rapid_chain_notes": longest_rapid_chain_notes,
        "decoupled_flow_pair_count": flow_pair_count,
        "decoupled_flow_longest_chain_notes": longest_flow_chain_notes,
        "decoupled_flow_rate_p90_per_s": _quantile(flow_rates, 0.90),
        "decoupled_flow_distance_radii_p90": _quantile(flow_distance_radii, 0.90),
        "decoupled_finger_change_p90": _quantile(finger_changes, 0.90),
        "decoupled_finger_change_share": (
            None
            if not finger_changes
            else sum(value >= 0.12 for value in finger_changes) / len(finger_changes)
        ),
        "decoupled_finger_complexity_p90": _quantile(finger_complexity, 0.90),
        "decoupled_finger_switch_count": switch_count,
        "decoupled_finger_longest_alternating_chain": longest_alternating_chain,
        "decoupled_precision_micro_correction_count": len(precision_micro_terms),
        "decoupled_precision_micro_correction_p90": _quantile(
            precision_micro_terms, 0.90
        ),
        "decoupled_precision_micro_gate": (
            0.0
            if not precision_micro_terms
            else math.sqrt(
                (_quantile(precision_micro_terms, 0.90) or 0.0)
                * _clamp(len(precision_micro_terms) / 10.0, 0.0, 1.0)
            )
        ),
        "decoupled_reading_irregularity_p90": _quantile(reading_shocks, 0.90),
        "decoupled_reading_irregularity_top10_mean": (
            None
            if not reading_shocks
            else sum(
                sorted(reading_shocks, reverse=True)[
                    : max(1, int(math.ceil(len(reading_shocks) * 0.10)))
                ]
            )
            / max(1, int(math.ceil(len(reading_shocks) * 0.10)))
        ),
    }


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Optional[dict[str, Any]] = None,
    difficulty: Optional[dict[str, Any]] = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    rows = list(local_rows)
    components, abstentions = v096.extract_components(
        rows,
        features,
        difficulty=difficulty,
        clock_rate=clock_rate,
        effective_mods=effective_mods,
    )
    components.update(_independent_sequence_components(rows))
    return components, abstentions


def calibration_id(base_calibration_id: str) -> str:
    payload = json.dumps(
        {"base_calibration_id": base_calibration_id, "mechanism_spec": MECHANISM_SPEC},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"mddecoupled_v01:{digest}"


def _jump_evidence(components: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    severity = _clamp(_finite(components.get("v092_jump_severity_gate")) or 0.0, 0.0, 1.2)
    extreme = _clamp(_finite(components.get("v092_jump_extreme_gate")) or 0.0, 0.0, 1.2)
    persistence = _clamp(_finite(components.get("v092_jump_persistence_gate")) or 0.0, 0.0, 1.0)
    tail = _clamp(_finite(components.get("v092_jump_tail_activation")) or 0.0, 0.0, 1.2)
    large_share = max(
        _clamp(_finite(components.get("v095_tapping_large_jump_pair_share")) or 0.0, 0.0, 1.0),
        _clamp(_finite(components.get("v095_control_large_jump_share")) or 0.0, 0.0, 1.0),
    )
    distance_p99 = max(
        0.0, _finite(components.get("v092_jump_distance_raw_p99_px")) or 0.0
    )
    velocity_p99 = max(
        0.0,
        _finite(components.get("v092_jump_velocity_raw_p99_px_per_ms")) or 0.0,
    )
    distance_gate = _clamp((distance_p99 - 80.0) / 240.0, 0.0, 1.0)
    velocity_gate = _clamp((velocity_p99 - 0.35) / 2.20, 0.0, 1.0)
    kinematic_peak = max(
        0.72 * distance_gate,
        0.90 * math.sqrt(distance_gate * velocity_gate),
    )
    large_presence = 0.80 * math.sqrt(_clamp(large_share / 0.35, 0.0, 1.0))
    distance_speed = math.sqrt(
        _clamp(large_share / 0.55, 0.0, 1.0)
        * _clamp(max(severity, 0.80 * tail), 0.0, 1.0)
    )
    # P99 extreme evidence prevents a short genuine difficulty spike from
    # disappearing into an otherwise easy map.  Persistence still describes
    # how much of the map is jump-heavy, but it does not veto the peak.
    peak = _clamp(
        max(
            severity,
            extreme,
            0.88 * tail,
            distance_speed,
            kinematic_peak,
            large_presence,
        ),
        0.0,
        1.0,
    )
    support = _clamp(max(peak, 0.82 * peak + 0.18 * persistence), 0.0, 1.0)
    # Absence/low coverage is weak evidence only.  A real hard jump peak must
    # survive easy filler and sparse placement.
    counter = _clamp(1.0 - max(peak, 0.65 * persistence), 0.0, 1.0)
    return support, counter, {
        "peak": peak,
        "severity": severity,
        "extreme": extreme,
        "tail": tail,
        "persistence": persistence,
        "large_jump_share": large_share,
        "distance_speed": distance_speed,
        "distance_p99_px": distance_p99,
        "velocity_p99_px_per_ms": velocity_p99,
        "kinematic_peak": kinematic_peak,
        "large_presence": large_presence,
    }


def _flow_evidence(components: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    share = _clamp(_finite(components.get("v091_flow_chain_share")) or 0.0, 0.0, 1.0)
    length = max(0.0, _finite(components.get("v091_flow_chain_length_p90")) or 0.0)
    velocity = max(0.0, _finite(components.get("v091_flow_chain_velocity_p90")) or 0.0)
    smoothness = _clamp(_finite(components.get("v091_flow_chain_smoothness_mean")) or 0.0, 0.0, 1.0)
    length_gate = _clamp((length - 2.0) / 10.0, 0.0, 1.0)
    velocity_gate = _clamp((velocity - 0.25) / 1.10, 0.0, 1.0)
    broad_notes = max(0.0, _finite(components.get("decoupled_flow_longest_chain_notes")) or 0.0)
    broad_rate = max(0.0, _finite(components.get("decoupled_flow_rate_p90_per_s")) or 0.0)
    broad_spacing = max(0.0, _finite(components.get("decoupled_flow_distance_radii_p90")) or 0.0)
    large_share = max(
        _clamp(
            _finite(components.get("v095_tapping_large_jump_pair_share")) or 0.0,
            0.0,
            1.0,
        ),
        _clamp(
            _finite(components.get("v095_control_large_jump_share")) or 0.0,
            0.0,
            1.0,
        ),
    )
    broad_length_gate = _clamp((broad_notes - 3.0) / 11.0, 0.0, 1.0)
    broad_rate_gate = _clamp((broad_rate - 4.5) / 7.5, 0.0, 1.0)
    broad_spacing_gate = _clamp((broad_spacing - 0.6) / 3.8, 0.0, 1.0)
    broad_peak_unshaped = max(
        0.88 * broad_length_gate,
        math.sqrt(broad_length_gate * broad_rate_gate)
        * (0.72 + 0.28 * broad_spacing_gate),
    )
    # Absolute hit rate cannot distinguish a spaced stream from a high-BPM
    # jump chain.  Wide spacing plus a large-jump-dominant geometry is therefore
    # counter-shape evidence.  It only attenuates: genuinely long spaced streams
    # recover through length instead of being hard-rejected by one distance cap.
    wide_gate = _clamp((broad_spacing - 2.60) / 2.20, 0.0, 1.0)
    wide_jump_shape = math.sqrt(
        wide_gate * _clamp(large_share / 0.55, 0.0, 1.0)
    )
    long_chain_rescue = _clamp((broad_notes - 18.0) / 50.0, 0.0, 1.0)
    extreme_wide_jump = (
        _clamp((broad_spacing - 4.30) / 0.70, 0.0, 1.0)
        * _clamp((large_share - 0.45) / 0.15, 0.0, 1.0)
    )
    morphology_confidence = _clamp(
        1.0
        - (
            0.20 * wide_jump_shape
            + 0.22 * extreme_wide_jump
        )
        * (1.0 - 0.65 * long_chain_rescue),
        0.0,
        1.0,
    )
    broad_peak = broad_peak_unshaped * morphology_confidence
    # Long coherent chains remain Flow evidence even when spacing/velocity is
    # moderate.  Velocity raises the peak; it does not veto the chain.
    chain_peak = max(0.82 * length_gate, math.sqrt(length_gate * velocity_gate))
    morphology = _clamp(
        0.20 * _clamp(share / 0.45, 0.0, 1.0)
        + 0.34 * length_gate
        + 0.34 * velocity_gate
        + 0.12 * smoothness,
        0.0,
        1.0,
    )
    support = max(chain_peak, broad_peak, morphology)
    counter = _clamp(1.0 - support, 0.0, 1.0)
    return support, counter, {
        "chain_peak": chain_peak,
        "morphology": morphology,
        "chain_share": share,
        "chain_length_p90": length,
        "chain_velocity_p90": velocity,
        "smoothness": smoothness,
        "broad_chain_notes": broad_notes,
        "broad_rate_per_s": broad_rate,
        "broad_spacing_radii": broad_spacing,
        "large_jump_share": large_share,
        "wide_jump_shape": wide_jump_shape,
        "extreme_wide_jump": extreme_wide_jump,
        "long_chain_rescue": long_chain_rescue,
        "morphology_confidence": morphology_confidence,
        "broad_peak_unshaped": broad_peak_unshaped,
        "broad_peak": broad_peak,
    }


def _control_evidence(components: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    index = _clamp(_finite(components.get("v095_control_index")) or 0.0, 0.0, 1.2)
    index_support = _clamp((index - 0.08) / 0.82, 0.0, 1.0)
    shock = _clamp(
        ((_finite(components.get("v095_control_shock_p95")) or 0.0) - 0.06)
        / 0.58,
        0.0,
        1.0,
    )
    turn_change = _clamp(
        ((_finite(components.get("v095_control_turn_change_p95")) or 0.0) - 0.10)
        / 0.90,
        0.0,
        1.0,
    )
    speed_change = _clamp(
        (_finite(components.get("v095_control_speed_change_p95")) or 0.0)
        / 1.50,
        0.0,
        1.0,
    )
    state_change_peak = (
        0.36 * turn_change + 0.34 * speed_change + 0.30 * shock
    )
    repeated_state_change = state_change_peak * (
        0.30 + 0.70 * math.sqrt(index_support)
    )
    # The legacy index already includes peak density and can saturate on plain
    # jump maps.  It is repetition context, not a standalone proof of control.
    support = _clamp(
        0.30 * state_change_peak + 0.70 * repeated_state_change,
        0.0,
        1.0,
    )
    regular_large_jump = (
        _clamp(_finite(components.get("v095_control_large_jump_share")) or 0.0, 0.0, 1.0)
        * _clamp(_finite(components.get("v092_jump_tail_activation")) or 0.0, 0.0, 1.0)
        * (1.0 - state_change_peak)
    )
    counter = _clamp(0.55 * (1.0 - support) + 0.45 * regular_large_jump, 0.0, 1.0)
    return support, counter, {
        "control_index": index,
        "index_support": index_support,
        "shock": shock,
        "turn_change": turn_change,
        "speed_change": speed_change,
        "state_change_peak": state_change_peak,
        "repeated_state_change": repeated_state_change,
        "regular_large_jump": regular_large_jump,
    }


def _precision_evidence(components: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    small_target = _clamp(_finite(components.get("v096_precision_small_target_gate")) or 0.0, 0.0, 1.0)
    large_target = _clamp(_finite(components.get("v096_precision_large_target_relief")) or 0.0, 0.0, 1.0)
    strict_micro = _finite(components.get("decoupled_precision_micro_gate"))
    micro = _clamp(
        strict_micro
        if strict_micro is not None
        else (_finite(components.get("v095_precision_micro_gate")) or 0.0),
        0.0,
        1.0,
    )
    settling = _clamp(_finite(components.get("v095_precision_settling_p90")) or 0.0, 0.0, 1.0)
    # Repeated post-jump correction is precision evidence in its own right;
    # requiring a high-CS gate here previously erased ordinary-CS tech maps.
    target_context = _clamp(
        0.50 + 0.50 * max(small_target, 1.0 - large_target), 0.0, 1.0
    )
    micro_support = micro * target_context
    tolerance_context = max(small_target, micro_support)
    support = _clamp(
        max(
            0.80 * micro_support,
            0.90 * small_target,
            0.58 * small_target + 0.30 * micro_support + 0.08 * settling,
        ),
        0.0,
        1.0,
    )
    # Large circles are real relief, but cannot veto repeated fine correction.
    counter = _clamp(
        large_target * (0.78 - 0.38 * micro_support)
        + 0.22 * (1.0 - tolerance_context),
        0.0,
        1.0,
    )
    return support, counter, {
        "small_target": small_target,
        "large_target_relief": large_target,
        "micro_correction": micro,
        "micro_target_context": target_context,
        "micro_support": micro_support,
        "settling": settling,
    }


def _raw_speed_evidence(components: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    rate = max(
        0.0,
        _finite(components.get("decoupled_tapping_rapid_rate_p90_per_s"))
        or _finite(components.get("v095_tapping_rate_p90_per_s"))
        or 0.0,
    )
    rate_gate = _clamp((rate - 5.5) / 8.5, 0.0, 1.0) ** 0.75
    longest = max(
        0.0,
        _finite(components.get("decoupled_tapping_longest_rapid_chain_notes"))
        or _finite(components.get("v095_tapping_longest_fast_chain_count"))
        or 0.0,
    )
    fast_count = max(
        0.0,
        _finite(components.get("decoupled_tapping_rapid_pair_count"))
        or _finite(components.get("v095_tapping_fast_compact_pair_count"))
        or 0.0,
    )
    transition_count = max(
        0.0,
        _finite(components.get("decoupled_tapping_transition_count")) or 0.0,
    )
    rapid_share = (
        0.0
        if transition_count <= 0.0
        else _clamp(fast_count / transition_count, 0.0, 1.0)
    )
    short_sustain = _clamp((longest - 2.0) / 4.0, 0.0, 1.0)
    repetition = _clamp((fast_count - 4.0) / 24.0, 0.0, 1.0)
    large_share = max(
        _clamp(
            _finite(components.get("v095_tapping_large_jump_pair_share")) or 0.0,
            0.0,
            1.0,
        ),
        _clamp(
            _finite(components.get("v095_control_large_jump_share")) or 0.0,
            0.0,
            1.0,
        ),
    )
    # Fast jumps still require tapping, so this is deliberately mild.  It only
    # prevents a jump-dominant cadence from being treated as a full stream-speed
    # specialist signal.
    tapping_morphology = 1.0 - 0.32 * math.sqrt(large_share)
    support = rate_gate * (
        0.46
        + 0.25 * short_sustain
        + 0.17 * repetition
        + 0.12 * math.sqrt(rapid_share)
    ) * tapping_morphology
    counter = _clamp(0.60 * (1.0 - rate_gate) + 0.40 * (1.0 - max(short_sustain, repetition)), 0.0, 1.0)
    return support, counter, {
        "rate_per_s": rate,
        "rate_gate": rate_gate,
        "longest_fast_chain": longest,
        "fast_pair_count": fast_count,
        "short_sustain": short_sustain,
        "repetition": repetition,
        "rapid_share": rapid_share,
        "large_jump_share": large_share,
        "tapping_morphology": tapping_morphology,
    }


def _finger_evidence(components: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    change = _clamp(_finite(components.get("decoupled_finger_change_p90")) or 0.0, 0.0, 1.0)
    change_share = _clamp(
        _finite(components.get("decoupled_finger_change_share")) or 0.0,
        0.0,
        1.0,
    )
    complexity = _clamp(
        _finite(components.get("decoupled_finger_complexity_p90")) or 0.0,
        0.0,
        1.0,
    )
    switch_count = max(
        0.0, _finite(components.get("decoupled_finger_switch_count")) or 0.0
    )
    alternating = max(
        0.0,
        _finite(components.get("decoupled_finger_longest_alternating_chain"))
        or 0.0,
    )
    repeat = _clamp((switch_count - 3.0) / 45.0, 0.0, 1.0)
    alternation = _clamp((alternating - 1.0) / 10.0, 0.0, 1.0)
    common_switching = math.sqrt(change * change_share) * repeat
    odd_rhythm = math.sqrt(complexity * max(change_share, repeat))
    switch_peak = (
        change
        * (0.50 + 0.50 * math.sqrt(change_share))
        * math.sqrt(repeat)
    )
    support = _clamp(
        max(
            switch_peak,
            0.62 * common_switching
            + 0.28 * odd_rhythm
            + 0.20 * alternation * max(change, complexity),
        ),
        0.0,
        1.0,
    )
    counter = _clamp(
        0.50 * (1.0 - repeat)
        + 0.30 * (1.0 - change_share)
        + 0.20 * (1.0 - max(change, complexity)),
        0.0,
        1.0,
    )
    return support, counter, {
        "change_p90": change,
        "change_share": change_share,
        "complexity_p90": complexity,
        "switch_count": switch_count,
        "longest_alternating_chain": alternating,
        "repeat": repeat,
        "common_switching": common_switching,
        "odd_rhythm": odd_rhythm,
        "switch_peak": switch_peak,
    }


def _stamina_evidence(components: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    rate = max(
        0.0,
        _finite(components.get("decoupled_tapping_rapid_rate_p90_per_s"))
        or _finite(components.get("v095_tapping_rate_p90_per_s"))
        or 0.0,
    )
    longest = max(
        0.0,
        _finite(components.get("decoupled_tapping_longest_rapid_chain_notes"))
        or _finite(components.get("v095_tapping_longest_fast_chain_count"))
        or 0.0,
    )
    rapid_pairs = max(
        0.0,
        _finite(components.get("decoupled_tapping_rapid_pair_count")) or 0.0,
    )
    transition_count = max(
        0.0,
        _finite(components.get("decoupled_tapping_transition_count")) or 0.0,
    )
    rapid_share = (
        0.0
        if transition_count <= 0.0
        else _clamp(rapid_pairs / transition_count, 0.0, 1.0)
    )
    chain_duration_s = 0.0 if rate <= 0.0 else max(0.0, longest - 1.0) / rate
    rate_linear = _clamp((rate - 5.5) / 8.5, 0.0, 1.0)
    # Stamina rises convexly with tapping rate: a 210 BPM stream is not a
    # small linear step above 180 BPM.  Length can reinforce but cannot replace
    # that speed pressure; very long moderate streams belong partly to Endurance.
    rate_gate = rate_linear**1.80
    # Six or fewer notes are not stamina.  Seven notes starts the axis; longer
    # chains then rise with diminishing returns.
    chain_gate = 0.0 if longest < 7.0 else 1.0 - math.exp(-(longest - 6.0) / 24.0)
    duration_gate = (
        0.0 if longest < 7.0 else 1.0 - math.exp(-chain_duration_s / 4.5)
    )
    occurrence = 0.40 + 0.60 * math.sqrt(rapid_share)
    sustain_shape = _clamp(
        0.68 * chain_gate + 0.32 * duration_gate, 0.0, 1.0
    )
    support = (
        0.0
        if longest < 7.0
        else (
            rate_gate + (1.0 - rate_gate) * 0.28 * sustain_shape
        )
        * occurrence
    )
    counter = 1.0 if longest < 7.0 else _clamp(1.0 - max(chain_gate, duration_gate), 0.0, 1.0)
    return support, counter, {
        "rate_per_s": rate,
        "rate_gate": rate_gate,
        "longest_fast_chain": longest,
        "chain_gate": chain_gate,
        "duration_gate": duration_gate,
        "chain_duration_s": chain_duration_s,
        "rapid_share": rapid_share,
        "occurrence_gate": occurrence,
        "sustain_shape": sustain_shape,
    }


def _endurance_evidence(components: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    coverage = _clamp(_finite(components.get("v092_pressure_coverage")) or 0.0, 0.0, 1.0)
    effective_s = max(0.0, _finite(components.get("v092_pressure_effective_duration_ms")) or 0.0) / 1000.0
    repeated_s = max(0.0, _finite(components.get("v092_pressure_repeated_section_effective_ms")) or 0.0) / 1000.0
    longest_s = max(0.0, _finite(components.get("v092_pressure_longest_continuous_effective_ms")) or 0.0) / 1000.0
    recovery = _clamp(_finite(components.get("v092_pressure_recovery_ratio")) or 0.0, 0.0, 1.0)
    pressure_p90 = max(
        0.0, _finite(components.get("v092_pressure_p90")) or 0.0
    )
    intensity = _clamp((pressure_p90 - 0.20) / 0.95, 0.0, 1.0)
    duration = effective_s / (effective_s + 120.0)
    repeated = repeated_s / (repeated_s + 75.0)
    continuous = longest_s / (longest_s + 20.0)
    duration_shape = _clamp(
        0.38 * duration
        + 0.28 * repeated
        + 0.20 * math.sqrt(coverage)
        + 0.14 * continuous,
        0.0,
        1.0,
    )
    support = duration_shape * (0.34 + 0.66 * math.sqrt(intensity))
    counter = _clamp(0.45 * (1.0 - duration) + 0.30 * recovery + 0.25 * (1.0 - coverage), 0.0, 1.0)
    return support, counter, {
        "coverage": coverage,
        "effective_s": effective_s,
        "repeated_s": repeated_s,
        "longest_s": longest_s,
        "recovery": recovery,
        "pressure_p90": pressure_p90,
        "intensity": intensity,
        "duration_shape": duration_shape,
    }


def _reading_evidence(
    components: dict[str, Any], mods: set[str], anchor: float
) -> tuple[float, float, dict[str, Any]]:
    preempt = _finite(components.get("reading_preempt_median_ms")) or 600.0
    overlap = _finite(components.get("v091_visible_overlap_load_p90")) or 0.0
    cluster = _finite(components.get("v091_visible_cluster_load_p90")) or 1.0
    overlap_share = _finite(components.get("v091_visible_overlap_pair_share")) or 0.0
    stack_share = _finite(components.get("v091_visible_stack_object_share")) or 0.0
    density = _finite(components.get("reading_density")) or 0.0
    hidden_pressure = _clamp(
        _finite(components.get("reading_hidden_pressure")) or 0.0, 0.0, 1.0
    )
    irregularity_p90 = _clamp(
        _finite(components.get("decoupled_reading_irregularity_p90")) or 0.0,
        0.0,
        1.0,
    )
    irregularity_top = _clamp(
        _finite(components.get("decoupled_reading_irregularity_top10_mean"))
        or 0.0,
        0.0,
        1.0,
    )
    irregularity = _clamp(
        max(
            (irregularity_p90 - 0.08) / 0.58,
            (irregularity_top - 0.10) / 0.62,
        ),
        0.0,
        1.0,
    )
    pair_support = _clamp((overlap_share - 0.04) / 0.30, 0.0, 1.0)
    visual_confusion = _clamp(
        0.46 * math.sqrt(_clamp((overlap - 0.40) / 1.80, 0.0, 1.0) * pair_support)
        + 0.28 * math.sqrt(_clamp((cluster - 1.0) / 6.0, 0.0, 1.0) * pair_support)
        + 0.16 * _clamp((stack_share - 0.04) / 0.50, 0.0, 1.0)
        + 0.10 * hidden_pressure,
        0.0,
        1.0,
    )
    density_gate = _clamp((density - 2.0) / 6.0, 0.0, 1.0)
    # Pattern irregularity is a shared raw fact, not an Aim Control score.
    # Reading consumes it only through the visibility/ordering mechanism.
    structure = _clamp(
        max(
            0.72 * visual_confusion,
            0.58 * irregularity
            + 0.30 * visual_confusion
            + 0.12 * density_gate * max(irregularity, visual_confusion),
        ),
        0.0,
        1.0,
    )
    # Relative AR uses the one global map anchor, never another axis result.
    required_preempt = _clamp(720.0 - 60.0 * (anchor - 5.0), 330.0, 780.0)
    relative_low_ar = _clamp((preempt - required_preempt) / 220.0, 0.0, 1.0)
    absolute_low_ar = _clamp((preempt - 620.0) / 180.0, 0.0, 1.0)
    structure_presence = max(structure, 0.72 * density_gate)
    low_ar_peak = math.sqrt(
        _clamp(relative_low_ar * 1.55, 0.0, 1.0) * structure_presence
    )
    high_ar = _clamp((430.0 - preempt) / 150.0, 0.0, 1.0) * structure
    hd_low_ar = 0.0
    hd_occlusion = 0.0
    if "HD" in mods:
        hd_low_ar = (
            _clamp((preempt - 650.0) / 100.0, 0.0, 1.0)
            * (0.55 + 0.45 * math.sqrt(structure_presence))
        )
        hd_occlusion = math.sqrt(
            max(hidden_pressure, visual_confusion) * max(structure, 0.25 * density_gate)
        )
    # Geometry can make ordering harder, but irregular aim by itself is not
    # Reading.  Structural evidence must pass through an actual visibility/
    # clustering context; high AR remains a bounded secondary pressure.
    high_ar_gate = _clamp((430.0 - preempt) / 150.0, 0.0, 1.0)
    high_ar_relief = 1.0 - 0.15 * high_ar_gate
    structural_reading = (
        structure
        * _clamp(0.52 + 0.62 * math.sqrt(visual_confusion), 0.0, 1.0)
        * high_ar_relief
    )
    high_ar *= 0.45
    support = _clamp(
        max(structural_reading, low_ar_peak, high_ar, hd_low_ar, hd_occlusion),
        0.0,
        1.0,
    )
    counter = _clamp(
        0.70 * (1.0 - support) + 0.30 * (1.0 - max(structure, visual_confusion)),
        0.0,
        1.0,
    )
    return support, counter, {
        "reading_irregularity_p90": irregularity_p90,
        "reading_irregularity_top10_mean": irregularity_top,
        "reading_irregularity_gate": irregularity,
        "visual_confusion": visual_confusion,
        "structure": structure,
        "density_gate": density_gate,
        "required_preempt_ms": required_preempt,
        "actual_preempt_ms": preempt,
        "relative_low_ar": relative_low_ar,
        "absolute_low_ar": absolute_low_ar,
        "low_ar_peak": low_ar_peak,
        "hd_low_ar": hd_low_ar,
        "hd_occlusion": hd_occlusion,
        "high_ar_with_structure": high_ar,
        "high_ar_relief": high_ar_relief,
    }


def axis_evidence(
    components: dict[str, Any], *, mods: Iterable[str] = (), anchor: float = 5.0
) -> dict[str, tuple[float, float, dict[str, Any]]]:
    """Return independent support/counterevidence for every axis."""

    effective_mods = set(mods)
    return {
        "jump_aim": _jump_evidence(components),
        "aim_control": _control_evidence(components),
        "spatial_precision": _precision_evidence(components),
        "flow_aim": _flow_evidence(components),
        "raw_speed": _raw_speed_evidence(components),
        "finger_control": _finger_evidence(components),
        "reading": _reading_evidence(components, effective_mods, anchor),
        "stamina": _stamina_evidence(components),
        "endurance": _endurance_evidence(components),
    }


_COUNTER_WEIGHTS = {
    "jump_aim": 0.06,
    "flow_aim": 0.06,
    "aim_control": 0.34,
    "spatial_precision": 0.42,
    "raw_speed": 0.28,
    "finger_control": 0.30,
    "reading": 0.30,
    "stamina": 0.32,
    "endurance": 0.30,
}

_PROMINENCE_WEIGHTS = {
    "jump_aim": 0.18,
    "flow_aim": 0.18,
    "aim_control": 0.16,
    "spatial_precision": 0.12,
    "raw_speed": 0.10,
    "finger_control": 0.10,
    "reading": 0.22,
    "stamina": 0.0,
    "endurance": 0.0,
}


def _axis_value(axis: str, anchor: float, support: float, counter: float) -> float:
    positive = _clamp(support, 0.0, 1.0)
    negative = _clamp(counter, 0.0, 1.0)
    prominence = _clamp((positive - 0.74) / 0.26, 0.0, 1.0) ** 1.35
    attenuation = 1.0 - _COUNTER_WEIGHTS[axis] * negative * (1.0 - positive ** 2)
    if axis in {"stamina", "endurance"}:
        if positive <= 0.0:
            return 0.0
        return _clamp(10.0 * positive ** 0.88 * attenuation, 0.0, 10.0)
    if positive <= 0.0:
        return 0.0
    # Total SR remains useful context, but it is no longer a direct multiplier.
    # The concave scale preserves low-map ordering and permits exceptional axes
    # to exceed 10 without making every supported axis inherit an extreme map's
    # full star rating.
    if axis in {"jump_aim", "flow_aim"}:
        # A proven dominant jump/flow mechanic is allowed to explain the map's
        # full difficulty.  Softening these axes erased exactly the peaks the
        # profiler is meant to expose (for example a 12-star jump map becoming
        # 9.6 Jump).  Morphology decides whether the proof is real; scaling must
        # not suppress it afterwards.
        mechanic_scale = max(anchor, 0.10)
    else:
        # Ordinary maps retain a readable star-like scale.  Above 8.5 the
        # context grows slowly so extreme total SR cannot inflate every axis.
        mechanic_scale = min(max(anchor, 0.10), 8.50) + 0.20 * max(
            anchor - 8.50, 0.0
        )
    value = max(
        0.0,
        mechanic_scale
        * (positive ** 0.92 + _PROMINENCE_WEIGHTS[axis] * prominence)
        * attenuation,
    )
    if axis in {"jump_aim", "flow_aim"}:
        # A peak may exceed total SR, but not explode to 1.2x merely because a
        # support gate saturated.  This is a soft semantic ceiling, not the old
        # global 10-star cap.
        value = min(value, max(anchor, 0.10) * 1.08)
    return value


def decoupled_values(
    components: dict[str, Any], *, mods: Iterable[str] = (), anchor: float = 5.0
) -> tuple[dict[str, float], dict[str, tuple[float, float, dict[str, Any]]]]:
    evidence = axis_evidence(components, mods=mods, anchor=anchor)
    values = {
        axis: _axis_value(axis, anchor, support, counter)
        for axis, (support, counter, _) in evidence.items()
    }
    return values, evidence


def _replace_axis(
    axes: dict[str, Any],
    axis: str,
    value: float,
    evidence: tuple[float, float, dict[str, Any]],
) -> None:
    item = axes.get(axis)
    if not isinstance(item, dict):
        return
    support, counter, signals = evidence
    item.update(
        {
            "status": "EMITTED",
            "demand_star_equivalent": value,
            "score": value / 10.0,
            "percentile_rank": None,
            "scale_method": "DECOUPLED_CONCAVE_CONTEXT_SCALE_V02",
            "method": "INDEPENDENT_AXIS_SUPPORT_COUNTEREVIDENCE_V02",
            "evidence": [
                {
                    "component": "decoupled_axis_v01_r2",
                    "support_gate": support,
                    "counterevidence_gate": counter,
                    "counter_weight": _COUNTER_WEIGHTS[axis],
                    "signals": signals,
                    "evidence_tag": "EXPERIMENTAL_DECOUPLING_NOT_PRODUCTION",
                }
            ],
        }
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
    output = v096.analyze_components(
        checksum=checksum,
        requested_mods=requested_mods,
        components=components,
        calibration=calibration,
        reference_diagnostics=reference_diagnostics,
        applied_mod_context=applied_mod_context,
        algorithm_id=algorithm_id,
    )
    diagnostics = output.setdefault("diagnostics", {})
    mod_context = diagnostics.get("mod_context", {})
    anchor_data = diagnostics.get("v091_star_anchor", {})
    anchor = _finite(anchor_data.get("stars")) if isinstance(anchor_data, dict) else None
    if anchor is None:
        anchor = 5.0
        diagnostics["decoupled_anchor_fallback"] = True
    mods = set(mod_context.get("effective_mods", []))
    output["schema_version"] = SCHEMA_VERSION
    output["identity"] = C.make_identity(
        beatmap_checksum=checksum,
        effective_mods=mods,
        clock_rate=mod_context.get("clock_rate", 1.0),
        calibration_id=calibration_id(str(calibration.get("calibration_id", ""))),
        algorithm_id=algorithm_id,
        map_demand_version=MAP_DEMAND_VERSION,
    )
    diagnostics["decoupled_mechanism_spec"] = MECHANISM_SPEC
    diagnostics["decoupled_no_axis_score_dependencies"] = True
    if output.get("status") == "OK":
        values, evidence = decoupled_values(components, mods=mods, anchor=anchor)
        for axis in AXIS_ORDER:
            _replace_axis(output["axes"], axis, values[axis], evidence[axis])
        diagnostics["decoupled_axis_gates"] = {
            axis: {"support": item[0], "counterevidence": item[1]}
            for axis, item in evidence.items()
        }
        output["summaries"] = v092.derive_summaries(output["axes"])
        output["archetype"] = v095._classify_axes_with_low_demand_abstention(
            output["axes"], anchor
        )
    C.scan_finite(output, "model_decoupled_v01.output")
    return output
