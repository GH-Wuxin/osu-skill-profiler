"""Coherent Jump/Flow evidence from Local Signal 0.4 rows.

The calculator deliberately keeps distance and time from the same movement
model.  Jump uses the post-slider minimum distance with the post-slider
minimum time, falling back only to head distance with the full transition
time.  Flow uses the complete lazy cursor path over the full transition and
keeps slider-internal travel as a separate channel which can strengthen, but
cannot create, a coherent directional chain.

This module is extraction- and release-agnostic.  It neither reads total star
rating nor mutates the supplied rows, and its returned component is validated
against an exact nested schema before it leaves :func:`aim_routing_measure`.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "aim_routing_v0.1.0"
LOCAL_SIGNAL_VERSION = "0.4.0"
MIN_TIME_MS = 25.0
REFERENCE_RADIUS_PX = (54.4 - 4.48 * 4.0) * 1.00041
REFERENCE_CS_SCALE = 50.0 / REFERENCE_RADIUS_PX

JUMP_PAIRING_POLICY = (
    "minimum_jump_distance_cs_normalised/cs_scale over minimum_jump_time_ms;"
    "fallback jump_distance_raw_px over adjusted_delta_time_ms;"
    "separate lazy_jump_distance_cs_normalised/cs_scale over adjusted_delta_time_ms"
)
FLOW_PAIRING_POLICY = (
    "(previous_lazy_travel+current_lazy_jump)/cs_scale over adjusted_delta_time_ms;"
    "separate current_lazy_travel/cs_scale over current_lazy_travel_time_ms"
)

_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "local_signal_version", "jump", "flow"}
)
_JUMP_KEYS = frozenset(
    {
        "status",
        "pairing_policy",
        "transition_candidate_count",
        "valid_pair_count",
        "valid_pair_coverage",
        "minimum_minimum_pair_count",
        "head_full_fallback_pair_count",
        "lazy_full_pair_count",
        "distance_raw_p95_px",
        "distance_raw_p99_px",
        "velocity_raw_p95_px_per_ms",
        "velocity_raw_p99_px_per_ms",
        "kinematic_joint_p95",
        "kinematic_joint_p99",
        "lazy_full_distance_raw_p95_px",
        "lazy_full_distance_raw_p99_px",
        "lazy_full_velocity_raw_p95_px_per_ms",
        "lazy_full_velocity_raw_p99_px_per_ms",
        "lazy_full_kinematic_joint_p95",
        "lazy_full_kinematic_joint_p99",
        "joint_load_p95",
        "joint_load_p99",
        "high_pair_count",
        "high_pair_share",
        "high_pair_weight_sum",
        "high_pair_weight_share",
        "longest_high_chain_pairs",
        "longest_high_chain_weight",
        "circle_pair_count",
        "circle_large_pair_count",
        "circle_large_pair_share",
        "circle_large_valid_pair_share",
        "circle_large_pair_weight_sum",
        "circle_large_pair_weight_share",
        "circle_large_valid_pair_weight_share",
        "circle_large_local_window_size",
        "circle_large_local_window_count",
        "circle_large_local_window_share",
        "circle_large_local_window_weight_size",
        "circle_large_local_window_weight_sum",
        "circle_large_local_window_weight_share",
        "longest_circle_large_chain_pairs",
        "longest_circle_large_chain_weight",
        "circle_large_presence",
        "size_factor_p50",
        "severity_gate",
        "extreme_gate",
        "persistence_gate",
        "tail_activation",
        "kinematic_peak",
        "lazy_full_kinematic_peak",
        "routing_activation",
        "support",
        "counterevidence",
    }
)
_FLOW_KEYS = frozenset(
    {
        "status",
        "pairing_policy",
        "nonspinner_object_count",
        "transition_candidate_count",
        "full_path_pair_count",
        "full_path_pair_coverage",
        "morphology_opportunity_count",
        "directional_pair_count",
        "directional_pair_coverage",
        "full_path_distance_raw_p95_px",
        "full_path_distance_raw_p99_px",
        "full_path_velocity_raw_p95_px_per_ms",
        "full_path_velocity_raw_p99_px_per_ms",
        "strict_pair_count",
        "strict_pair_coverage",
        "strict_chain_length_p90_notes",
        "strict_velocity_load_p90_px_per_ms",
        "strict_smoothness_mean",
        "broad_pair_count",
        "broad_pair_coverage",
        "broad_longest_chain_notes",
        "broad_rate_p90_per_s",
        "broad_full_path_ref_radii_p90",
        "morphology_pair_count",
        "morphology_full_path_ref_radii_p90",
        "head_dominance_weight_sum",
        "wide_head_dominance_weight_sum",
        "wide_head_dominance_share",
        "slider_object_count",
        "slider_travel_valid_count",
        "slider_note_coverage",
        "slider_travel_velocity_raw_p90_px_per_ms",
        "slider_travel_velocity_load_p90_px_per_ms",
        "size_factor_p50",
        "strict_joint_peak_raw",
        "broad_joint_peak_raw",
        "morphology_joint_peak_raw",
        "joint_coherence_gate",
        "length_gate",
        "velocity_gate",
        "coverage_gate",
        "coherence_gate",
        "chain_peak",
        "broad_peak",
        "morphology",
        "slider_peak",
        "routing_activation",
        "support",
        "counterevidence",
    }
)

_JUMP_COUNT_KEYS = frozenset(
    {
        "transition_candidate_count",
        "valid_pair_count",
        "minimum_minimum_pair_count",
        "head_full_fallback_pair_count",
        "lazy_full_pair_count",
        "high_pair_count",
        "longest_high_chain_pairs",
        "circle_pair_count",
        "circle_large_pair_count",
        "circle_large_local_window_size",
        "circle_large_local_window_count",
        "circle_large_local_window_weight_size",
        "longest_circle_large_chain_pairs",
    }
)
_FLOW_COUNT_KEYS = frozenset(
    {
        "nonspinner_object_count",
        "transition_candidate_count",
        "full_path_pair_count",
        "morphology_opportunity_count",
        "directional_pair_count",
        "strict_pair_count",
        "broad_pair_count",
        "morphology_pair_count",
        "slider_object_count",
        "slider_travel_valid_count",
    }
)
_UNIT_INTERVAL_KEYS = frozenset(
    {
        "high_pair_share",
        "high_pair_weight_share",
        "circle_large_pair_share",
        "circle_large_valid_pair_share",
        "circle_large_pair_weight_share",
        "circle_large_valid_pair_weight_share",
        "circle_large_local_window_share",
        "circle_large_local_window_weight_share",
        "circle_large_presence",
        "kinematic_joint_p95",
        "kinematic_joint_p99",
        "lazy_full_kinematic_joint_p95",
        "lazy_full_kinematic_joint_p99",
        "severity_gate",
        "extreme_gate",
        "persistence_gate",
        "tail_activation",
        "kinematic_peak",
        "lazy_full_kinematic_peak",
        "routing_activation",
        "full_path_pair_coverage",
        "directional_pair_coverage",
        "strict_pair_coverage",
        "strict_smoothness_mean",
        "broad_pair_coverage",
        "wide_head_dominance_share",
        "slider_note_coverage",
        "strict_joint_peak_raw",
        "broad_joint_peak_raw",
        "morphology_joint_peak_raw",
        "joint_coherence_gate",
        "length_gate",
        "velocity_gate",
        "coverage_gate",
        "coherence_gate",
        "chain_peak",
        "broad_peak",
        "morphology",
        "slider_peak",
        "routing_activation",
        "support",
        "counterevidence",
    }
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _nonnegative(value: Any) -> float | None:
    number = _finite(value)
    return number if number is not None and number >= 0.0 else None


def _positive(value: Any) -> float | None:
    number = _finite(value)
    return number if number is not None and number > 0.0 else None


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * _clamp(q)
    left = int(math.floor(position))
    right = int(math.ceil(position))
    if left == right:
        return ordered[left]
    weight = position - left
    return ordered[left] * (1.0 - weight) + ordered[right] * weight


def _ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator <= 0 else numerator / denominator


def _size_factor(cs_scale: float) -> float:
    # The exponent is intentionally mild.  Physical distances and velocities
    # remain raw; target size affects only the positive load channel.
    return (cs_scale / REFERENCE_CS_SCALE) ** 0.08


def _fade_after(value: float, *, full_until: float, zero_at: float) -> float:
    """Return a continuous time-window weight with an explicit full region."""
    if value <= full_until:
        return 1.0
    if value >= zero_at:
        return 0.0
    return (zero_at - value) / (zero_at - full_until)


def _jump_gates(
    *,
    load_p95: float,
    load_p99: float,
    high_weight_share: float,
    longest_high_chain_weight: float,
    circle_large_weight_sum: float,
    circle_large_valid_weight_share: float,
    circle_large_local_weight_sum: float,
    circle_large_local_weight_share: float,
    longest_circle_large_chain_weight: float,
    kinematic_joint_p99: float,
    lazy_full_kinematic_joint_p99: float,
    valid_pair_coverage: float,
) -> dict[str, float]:
    severity = _clamp((load_p95 - 0.50) / 0.70)
    extreme = _clamp((load_p99 - 0.65) / 0.75)
    share_gate = _clamp(high_weight_share / 0.25)
    chain_gate = _clamp((longest_high_chain_weight - 4.0) / 24.0)
    persistence = 0.40 * share_gate + 0.60 * chain_gate
    tail_gate = (0.72 * severity + 0.28 * extreme) * persistence
    tail_activation = _clamp((tail_gate - 0.25) / 0.65)
    kinematic_peak = _clamp(kinematic_joint_p99)
    lazy_full_kinematic_peak = _clamp(lazy_full_kinematic_joint_p99)
    # Large, timely circle-to-circle movements remain valid spatial Jump
    # evidence even when a map-wide p99 does not expose a short jump section.
    # A within-circle share alone is unsafe: one rare circle pair among a
    # thousand easy slider transitions would otherwise look like 100% Jump.
    # Require either a locally dense 8-transition window or distributed
    # prevalence among all valid transitions, with explicit count support.
    local_count_gate = _clamp((circle_large_local_weight_sum - 1.0) / 5.0)
    local_density_gate = _clamp(
        (circle_large_local_weight_share - 0.125) / 0.50
    )
    circle_chain_gate = _clamp(
        (longest_circle_large_chain_weight - 1.0) / 5.0
    )
    localized_circle_evidence = (
        math.sqrt(local_count_gate * local_density_gate)
        * (0.75 + 0.25 * circle_chain_gate)
    )
    distributed_count_gate = _clamp((circle_large_weight_sum - 2.0) / 10.0)
    distributed_share_gate = _clamp(
        circle_large_valid_weight_share / 0.08
    )
    distributed_circle_evidence = math.sqrt(
        distributed_count_gate * distributed_share_gate
    )
    circle_large_presence = 0.80 * max(
        localized_circle_evidence,
        distributed_circle_evidence,
    )
    peak = _clamp(
        max(
            severity,
            extreme,
            0.88 * tail_activation,
            kinematic_peak,
            lazy_full_kinematic_peak,
            circle_large_presence,
        )
    )
    coverage_attenuation = math.sqrt(_clamp(valid_pair_coverage))
    routing_activation = _clamp(valid_pair_coverage)
    support = _clamp(
        max(peak, 0.82 * peak + 0.18 * persistence) * coverage_attenuation
    )
    counter = _clamp(
        (1.0 - max(peak, 0.65 * persistence)) * coverage_attenuation
    )
    return {
        "severity_gate": severity,
        "extreme_gate": extreme,
        "persistence_gate": persistence,
        "tail_activation": tail_activation,
        "kinematic_peak": kinematic_peak,
        "lazy_full_kinematic_peak": lazy_full_kinematic_peak,
        "circle_large_presence": circle_large_presence,
        "routing_activation": routing_activation,
        "support": support,
        "counterevidence": counter,
    }


def _jump_component(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    distances: list[float] = []
    velocities: list[float] = []
    loads: list[float] = []
    kinematic_scores: list[float] = []
    lazy_full_distances: list[float] = []
    lazy_full_velocities: list[float] = []
    lazy_full_kinematic_scores: list[float] = []
    size_factors: list[float] = []
    transition_candidates = 0
    primary_count = 0
    fallback_count = 0
    lazy_full_count = 0
    high_count = 0
    high_weight_sum = 0.0
    high_chain = 0
    longest_high_chain = 0
    high_chain_weight = 0.0
    longest_high_chain_weight = 0.0
    circle_pair_count = 0
    circle_large_count = 0
    circle_large_weight_sum = 0.0
    circle_large_chain = 0
    longest_circle_large_chain = 0
    circle_large_chain_weight = 0.0
    longest_circle_large_chain_weight = 0.0
    circle_large_window: list[int] = []
    circle_large_weight_window: list[float] = []
    circle_large_local_window_size = 0
    circle_large_local_window_count = 0
    circle_large_local_window_share = 0.0
    circle_large_local_rank = (-1.0, -1, -1.0)
    circle_large_local_window_weight_sum = 0.0
    circle_large_local_window_weight_size = 0
    circle_large_local_window_weight_share = 0.0
    circle_large_local_weight_rank = (-1.0, -1.0, -1.0)
    have_previous = False
    previous_was_circle = False

    for row in rows:
        object_type = row.get("ls.object_type")
        if object_type == "spinner":
            have_previous = False
            previous_was_circle = False
            high_chain = 0
            high_chain_weight = 0.0
            circle_large_chain = 0
            circle_large_chain_weight = 0.0
            circle_large_window = []
            circle_large_weight_window = []
            continue
        current_is_circle = object_type == "circle"
        if not have_previous:
            have_previous = True
            previous_was_circle = current_is_circle
            continue
        circle_pair = previous_was_circle and current_is_circle
        previous_was_circle = current_is_circle
        transition_candidates += 1

        cs_scale = _positive(row.get("ls.cs_scale"))
        minimum_distance = _nonnegative(
            row.get("ls.minimum_jump_distance_cs_normalised")
        )
        minimum_time = _positive(row.get("ls.minimum_jump_time_ms"))
        raw_head_distance = _nonnegative(row.get("ls.jump_distance_raw_px"))
        lazy_jump_distance = _nonnegative(
            row.get("ls.lazy_jump_distance_cs_normalised")
        )
        full_time = _positive(row.get("ls.adjusted_delta_time_ms"))

        if (
            lazy_jump_distance is not None
            and full_time is not None
            and cs_scale is not None
        ):
            lazy_full_distance = lazy_jump_distance / cs_scale
            lazy_full_distances.append(lazy_full_distance)
            lazy_full_velocity = lazy_full_distance / max(full_time, MIN_TIME_MS)
            lazy_full_velocities.append(lazy_full_velocity)
            lazy_full_distance_gate = _clamp(
                (lazy_full_distance - 80.0) / 240.0
            )
            lazy_full_velocity_gate = _clamp(
                (lazy_full_velocity - 0.35) / 2.20
            )
            lazy_full_kinematic_scores.append(
                max(
                    0.72 * lazy_full_distance_gate,
                    0.90
                    * math.sqrt(
                        lazy_full_distance_gate * lazy_full_velocity_gate
                    ),
                )
            )
            lazy_full_count += 1

        paired_distance: float | None = None
        paired_time: float | None = None
        pair_scale: float | None = None
        used_minimum_pair = False
        if (
            minimum_distance is not None
            and minimum_time is not None
            and cs_scale is not None
        ):
            paired_distance = minimum_distance / cs_scale
            paired_time = minimum_time
            pair_scale = cs_scale
            used_minimum_pair = True
            primary_count += 1
        elif raw_head_distance is not None and full_time is not None:
            paired_distance = raw_head_distance
            paired_time = full_time
            pair_scale = cs_scale or REFERENCE_CS_SCALE
            fallback_count += 1

        if paired_distance is None or paired_time is None or pair_scale is None:
            high_chain = 0
            high_chain_weight = 0.0
            circle_large_chain = 0
            circle_large_chain_weight = 0.0
            circle_large_window = []
            circle_large_weight_window = []
            continue

        velocity = paired_distance / max(paired_time, MIN_TIME_MS)
        size_factor = _size_factor(pair_scale)
        distance_gate = _clamp((paired_distance - 100.0) / 220.0, 0.0, 1.5)
        velocity_gate = _clamp((velocity - 0.70) / 2.0, 0.0, 1.5)
        load = math.sqrt(distance_gate * velocity_gate) * size_factor
        distances.append(paired_distance)
        velocities.append(velocity)
        loads.append(load)
        kinematic_distance_gate = _clamp((paired_distance - 80.0) / 240.0)
        kinematic_velocity_gate = _clamp((velocity - 0.35) / 2.20)
        kinematic_scores.append(
            max(
                0.72 * kinematic_distance_gate,
                0.90
                * math.sqrt(kinematic_distance_gate * kinematic_velocity_gate),
            )
        )
        size_factors.append(size_factor)

        is_large_circle_pair = False
        circle_large_weight = 0.0
        if circle_pair and used_minimum_pair:
            circle_pair_count += 1
            distance_weight = _clamp(
                (
                    paired_distance / REFERENCE_RADIUS_PX
                    - 3.25
                )
                / 0.50
            )
            time_weight = _fade_after(
                paired_time,
                full_until=250.0,
                zero_at=320.0,
            )
            circle_large_weight = distance_weight * time_weight
            circle_large_weight_sum += circle_large_weight
            if (
                paired_distance >= 3.75 * REFERENCE_RADIUS_PX
                and paired_time <= 250.0
            ):
                circle_large_count += 1
                is_large_circle_pair = True

        if is_large_circle_pair:
            circle_large_chain += 1
            longest_circle_large_chain = max(
                longest_circle_large_chain,
                circle_large_chain,
            )
        else:
            circle_large_chain = 0
        circle_large_chain_weight = circle_large_weight * (
            1.0 + circle_large_chain_weight
        )
        longest_circle_large_chain_weight = max(
            longest_circle_large_chain_weight,
            circle_large_chain_weight,
        )
        circle_large_window.append(1 if is_large_circle_pair else 0)
        circle_large_weight_window.append(circle_large_weight)
        if len(circle_large_window) > 8:
            circle_large_window.pop(0)
            circle_large_weight_window.pop(0)
        local_size = len(circle_large_window)
        local_count = sum(circle_large_window)
        local_share = _ratio(local_count, local_size)
        local_strength = math.sqrt(
            _clamp((local_count - 1.0) / 5.0)
            * _clamp((local_share - 0.125) / 0.50)
        )
        local_rank = (local_strength, local_count, local_share)
        if local_rank > circle_large_local_rank:
            circle_large_local_rank = local_rank
            circle_large_local_window_size = local_size
            circle_large_local_window_count = local_count
            circle_large_local_window_share = local_share

        local_weight_sum = sum(circle_large_weight_window)
        local_weight_share = _ratio(local_weight_sum, local_size)
        local_weight_strength = math.sqrt(
            _clamp((local_weight_sum - 1.0) / 5.0)
            * _clamp((local_weight_share - 0.125) / 0.50)
        )
        local_weight_rank = (
            local_weight_strength,
            local_weight_sum,
            local_weight_share,
        )
        if local_weight_rank > circle_large_local_weight_rank:
            circle_large_local_weight_rank = local_weight_rank
            circle_large_local_window_weight_size = local_size
            circle_large_local_window_weight_sum = local_weight_sum
            circle_large_local_window_weight_share = local_weight_share

        high_weight = (
            _clamp((load - 0.45) / 0.20)
            * _fade_after(
                paired_time,
                full_until=250.0,
                zero_at=320.0,
            )
        )
        high_weight_sum += high_weight
        high_chain_weight = high_weight * (1.0 + high_chain_weight)
        longest_high_chain_weight = max(
            longest_high_chain_weight,
            high_chain_weight,
        )
        if load >= 0.55 and paired_time <= 250.0:
            high_count += 1
            high_chain += 1
            longest_high_chain = max(longest_high_chain, high_chain)
        else:
            high_chain = 0

    valid_count = primary_count + fallback_count
    distance_p95 = _quantile(distances, 0.95)
    distance_p99 = _quantile(distances, 0.99)
    velocity_p95 = _quantile(velocities, 0.95)
    velocity_p99 = _quantile(velocities, 0.99)
    kinematic_joint_p95 = _quantile(kinematic_scores, 0.95)
    kinematic_joint_p99 = _quantile(kinematic_scores, 0.99)
    load_p95 = _quantile(loads, 0.95)
    load_p99 = _quantile(loads, 0.99)
    lazy_full_distance_p95 = _quantile(lazy_full_distances, 0.95)
    lazy_full_distance_p99 = _quantile(lazy_full_distances, 0.99)
    lazy_full_velocity_p95 = _quantile(lazy_full_velocities, 0.95)
    lazy_full_velocity_p99 = _quantile(lazy_full_velocities, 0.99)
    lazy_full_kinematic_joint_p95 = _quantile(
        lazy_full_kinematic_scores,
        0.95,
    )
    lazy_full_kinematic_joint_p99 = _quantile(
        lazy_full_kinematic_scores,
        0.99,
    )
    high_share = _ratio(high_count, valid_count)
    high_weight_share = _ratio(high_weight_sum, valid_count)
    valid_coverage = _ratio(valid_count, transition_candidates)
    circle_large_share = _ratio(circle_large_count, circle_pair_count)
    circle_large_valid_share = _ratio(circle_large_count, valid_count)
    circle_large_weight_share = _ratio(
        circle_large_weight_sum,
        circle_pair_count,
    )
    circle_large_valid_weight_share = _ratio(
        circle_large_weight_sum,
        valid_count,
    )
    gates = _jump_gates(
        load_p95=load_p95,
        load_p99=load_p99,
        high_weight_share=high_weight_share,
        longest_high_chain_weight=longest_high_chain_weight,
        circle_large_weight_sum=circle_large_weight_sum,
        circle_large_valid_weight_share=circle_large_valid_weight_share,
        circle_large_local_weight_sum=circle_large_local_window_weight_sum,
        circle_large_local_weight_share=(
            circle_large_local_window_weight_share
        ),
        longest_circle_large_chain_weight=(
            longest_circle_large_chain_weight
        ),
        kinematic_joint_p99=kinematic_joint_p99,
        lazy_full_kinematic_joint_p99=lazy_full_kinematic_joint_p99,
        valid_pair_coverage=valid_coverage,
    )
    return {
        "status": "OK" if valid_count else "INSUFFICIENT",
        "pairing_policy": JUMP_PAIRING_POLICY,
        "transition_candidate_count": transition_candidates,
        "valid_pair_count": valid_count,
        "valid_pair_coverage": valid_coverage,
        "minimum_minimum_pair_count": primary_count,
        "head_full_fallback_pair_count": fallback_count,
        "lazy_full_pair_count": lazy_full_count,
        "distance_raw_p95_px": distance_p95,
        "distance_raw_p99_px": distance_p99,
        "velocity_raw_p95_px_per_ms": velocity_p95,
        "velocity_raw_p99_px_per_ms": velocity_p99,
        "kinematic_joint_p95": kinematic_joint_p95,
        "kinematic_joint_p99": kinematic_joint_p99,
        "lazy_full_distance_raw_p95_px": lazy_full_distance_p95,
        "lazy_full_distance_raw_p99_px": lazy_full_distance_p99,
        "lazy_full_velocity_raw_p95_px_per_ms": lazy_full_velocity_p95,
        "lazy_full_velocity_raw_p99_px_per_ms": lazy_full_velocity_p99,
        "lazy_full_kinematic_joint_p95": lazy_full_kinematic_joint_p95,
        "lazy_full_kinematic_joint_p99": lazy_full_kinematic_joint_p99,
        "joint_load_p95": load_p95,
        "joint_load_p99": load_p99,
        "high_pair_count": high_count,
        "high_pair_share": high_share,
        "high_pair_weight_sum": high_weight_sum,
        "high_pair_weight_share": high_weight_share,
        "longest_high_chain_pairs": longest_high_chain,
        "longest_high_chain_weight": longest_high_chain_weight,
        "circle_pair_count": circle_pair_count,
        "circle_large_pair_count": circle_large_count,
        "circle_large_pair_share": circle_large_share,
        "circle_large_valid_pair_share": circle_large_valid_share,
        "circle_large_pair_weight_sum": circle_large_weight_sum,
        "circle_large_pair_weight_share": circle_large_weight_share,
        "circle_large_valid_pair_weight_share": (
            circle_large_valid_weight_share
        ),
        "circle_large_local_window_size": circle_large_local_window_size,
        "circle_large_local_window_count": circle_large_local_window_count,
        "circle_large_local_window_share": circle_large_local_window_share,
        "circle_large_local_window_weight_sum": (
            circle_large_local_window_weight_sum
        ),
        "circle_large_local_window_weight_size": (
            circle_large_local_window_weight_size
        ),
        "circle_large_local_window_weight_share": (
            circle_large_local_window_weight_share
        ),
        "longest_circle_large_chain_pairs": longest_circle_large_chain,
        "longest_circle_large_chain_weight": (
            longest_circle_large_chain_weight
        ),
        "size_factor_p50": _quantile(size_factors, 0.50) if size_factors else 1.0,
        **gates,
    }


def _flow_shape_confidence(
    notes: float,
    spacings: list[float],
    wide_head_dominance_sum: float,
) -> float:
    if not spacings:
        return 1.0
    spacing = _quantile(spacings, 0.90)
    wide_share = wide_head_dominance_sum / len(spacings)
    long_chain_rescue = _clamp((notes - 18.0) / 50.0)
    extreme_wide_jump = (
        _clamp((spacing - 4.30) / 0.70)
        * _clamp((wide_share - 0.45) / 0.15)
    )
    return _clamp(
        1.0
        - 0.55 * extreme_wide_jump * (1.0 - 0.65 * long_chain_rescue)
    )


def _strict_chain_evidence(chain: Mapping[str, Any]) -> tuple[float, float, float]:
    notes = float(chain["notes"])
    # One angle (three notes) describes a turn, but not persistence.  Treat it
    # as diagnostic morphology only; normative Flow evidence ramps
    # continuously from three to four effective notes.
    presence = _clamp((notes - 3.0) / 1.0)
    length_gate = _clamp((notes - 2.0) / 10.0)
    velocity = _quantile(chain["velocity_loads"], 0.90) * (
        1.0 + min(max(notes - 1.0, 0.0), 12.0) / 12.0
    )
    velocity_gate = _clamp((velocity - 0.25) / 1.10)
    smoothness = (
        sum(chain["smoothness"]) / len(chain["smoothness"])
        if chain["smoothness"]
        else 0.0
    )
    confidence = _flow_shape_confidence(
        notes,
        chain["spacings"],
        float(chain["wide_sum"]),
    )
    chain_peak = presence * max(
        0.82 * length_gate,
        math.sqrt(length_gate * velocity_gate),
    ) * confidence
    morphology = presence * _clamp(
        0.20
        + 0.34 * length_gate
        + 0.34 * velocity_gate
        + 0.12 * smoothness
    ) * confidence
    return _clamp(chain_peak), _clamp(morphology), presence


def _broad_chain_evidence(chain: Mapping[str, Any]) -> tuple[float, float]:
    notes = float(chain["notes"])
    presence = _clamp((notes - 3.5) / 0.5)
    length_gate = _clamp((notes - 3.0) / 11.0)
    rate_gate = _clamp((_quantile(chain["rates"], 0.90) - 4.5) / 7.5)
    spacing_gate = _clamp(
        (_quantile(chain["spacings"], 0.90) - 0.6) / 3.8
    )
    confidence = _flow_shape_confidence(
        notes,
        chain["spacings"],
        float(chain["wide_sum"]),
    )
    peak = (
        presence
        * math.sqrt(length_gate * rate_gate)
        * (0.72 + 0.28 * spacing_gate)
        * confidence
    )
    return _clamp(peak), presence


def _flow_gates(
    *,
    strict_length: float,
    strict_velocity: float,
    strict_coverage: float,
    broad_coverage: float,
    strict_joint_peak_raw: float,
    broad_joint_peak_raw: float,
    morphology_joint_peak_raw: float,
    joint_coherence_gate: float,
    slider_velocity: float,
    slider_coverage: float,
    full_path_coverage: float,
    directional_coverage: float,
) -> dict[str, float]:
    # These three gates remain map-level diagnostics.  Positive evidence is
    # scored inside each uninterrupted chain before maxima are taken, so no
    # chain can borrow length, cadence, spacing, or shape from another section.
    length_gate = _clamp((strict_length - 2.0) / 10.0)
    velocity_gate = _clamp((strict_velocity - 0.25) / 1.10)
    coverage_gate = _clamp(max(strict_coverage, broad_coverage) / 0.45)
    coherence_gate = _clamp(joint_coherence_gate)
    coverage_product = _clamp(full_path_coverage) * _clamp(
        directional_coverage
    )
    coverage_attenuation = math.sqrt(coverage_product)
    chain_peak = _clamp(strict_joint_peak_raw) * coverage_attenuation
    broad_peak = _clamp(broad_joint_peak_raw) * coverage_attenuation
    morphology = _clamp(morphology_joint_peak_raw) * coverage_attenuation
    slider_velocity_gate = _clamp((slider_velocity - 0.25) / 1.10)
    slider_coverage_gate = _clamp(slider_coverage / 0.45)
    slider_peak = (
        coherence_gate
        * 0.82
        * math.sqrt(slider_velocity_gate * slider_coverage_gate)
        * coverage_attenuation
    )
    # Slider travel is already present in full-path transition distance.
    # Its isolated context peak remains diagnostic but is not a standalone
    # proof, which would combine a chain in one section with a fast slider in
    # an unrelated section.
    raw_peak = max(
        _clamp(strict_joint_peak_raw),
        _clamp(broad_joint_peak_raw),
        _clamp(morphology_joint_peak_raw),
    )
    support = _clamp(max(chain_peak, broad_peak, morphology))
    counter = _clamp((1.0 - raw_peak) * coverage_attenuation)
    routing_activation = coherence_gate * coverage_product
    return {
        "length_gate": length_gate,
        "velocity_gate": velocity_gate,
        "coverage_gate": coverage_gate,
        "coherence_gate": coherence_gate,
        "chain_peak": chain_peak,
        "broad_peak": broad_peak,
        "morphology": morphology,
        "slider_peak": slider_peak,
        "routing_activation": routing_activation,
        "support": support,
        "counterevidence": counter,
    }


def _known_previous_travel(row: Mapping[str, Any]) -> float | None:
    travel = _nonnegative(row.get("ls.lazy_travel_distance_cs_normalised"))
    if travel is not None:
        return travel
    # A non-slider has no internal cursor path by definition.  Missing slider
    # geometry, however, is unknown and must never be fabricated as zero.
    if row.get("ls.object_type") != "slider":
        return 0.0
    return None


def _flow_component(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    nonspinner_count = 0
    transition_candidates = 0
    full_distances: list[float] = []
    full_velocities: list[float] = []
    size_factors: list[float] = []
    strict_lengths: list[float] = []
    strict_velocity_loads: list[float] = []
    strict_smoothness: list[float] = []
    broad_rates: list[float] = []
    broad_spacings: list[float] = []
    morphology_spacings: list[float] = []
    slider_velocities: list[float] = []
    slider_velocity_loads: list[float] = []
    strict_chains: list[dict[str, Any]] = []
    broad_chains: list[dict[str, Any]] = []
    strict_chain: dict[str, Any] | None = None
    broad_chain: dict[str, Any] | None = None
    strict_count = 0
    broad_count = 0
    broad_longest = 0.0
    morphology_count = 0
    morphology_opportunity_count = 0
    directional_pair_count = 0
    head_dominance_sum = 0.0
    wide_head_dominance_sum = 0.0
    slider_count = 0
    slider_valid_count = 0
    previous_path_valid = False
    previous_strict_time_weight = 0.0
    previous_broad_time_weight = 0.0
    previous_velocity_load = 0.0
    previous_rate = 0.0
    previous_spacing = 0.0
    previous_head_dominance = 0.0
    previous_wide_head_dominance = 0.0
    previous: Mapping[str, Any] | None = None
    previous_angle: float | None = None

    def finish_strict_chain() -> None:
        nonlocal strict_chain
        if strict_chain is not None:
            strict_chains.append(strict_chain)
            strict_chain = None

    def finish_broad_chain() -> None:
        nonlocal broad_chain
        if broad_chain is not None:
            broad_chains.append(broad_chain)
            broad_chain = None

    def reset_previous_path() -> None:
        nonlocal previous_path_valid
        nonlocal previous_strict_time_weight, previous_broad_time_weight
        nonlocal previous_velocity_load, previous_rate, previous_spacing
        nonlocal previous_head_dominance, previous_wide_head_dominance
        previous_path_valid = False
        previous_strict_time_weight = 0.0
        previous_broad_time_weight = 0.0
        previous_velocity_load = 0.0
        previous_rate = 0.0
        previous_spacing = 0.0
        previous_head_dominance = 0.0
        previous_wide_head_dominance = 0.0

    for row in rows:
        object_type = str(row.get("ls.object_type") or "")
        if object_type == "spinner":
            finish_strict_chain()
            finish_broad_chain()
            previous = None
            previous_angle = None
            reset_previous_path()
            continue

        nonspinner_count += 1
        cs_scale = _positive(row.get("ls.cs_scale"))
        if object_type == "slider":
            slider_count += 1
            travel_distance = _nonnegative(
                row.get("ls.lazy_travel_distance_cs_normalised")
            )
            travel_time = _positive(row.get("ls.lazy_travel_time_ms"))
            if (
                travel_distance is not None
                and travel_time is not None
                and cs_scale is not None
            ):
                raw_travel = travel_distance / cs_scale
                velocity = raw_travel / max(travel_time, MIN_TIME_MS)
                factor = _size_factor(cs_scale)
                slider_valid_count += 1
                slider_velocities.append(velocity)
                slider_velocity_loads.append(velocity * factor)
                size_factors.append(factor)

        if previous is None:
            previous = row
            continue

        transition_candidates += 1
        adjusted_time = _positive(row.get("ls.adjusted_delta_time_ms"))
        lazy_jump = _nonnegative(row.get("ls.lazy_jump_distance_cs_normalised"))
        previous_travel = _known_previous_travel(previous)
        angle = _finite(row.get("ls.slider_aware_angle_rad"))
        path_valid = (
            adjusted_time is not None
            and lazy_jump is not None
            and previous_travel is not None
            and cs_scale is not None
        )
        if not path_valid:
            finish_strict_chain()
            finish_broad_chain()
            reset_previous_path()
            previous_angle = None
            previous = row
            continue

        assert adjusted_time is not None
        assert lazy_jump is not None
        assert previous_travel is not None
        assert cs_scale is not None
        full_distance = (previous_travel + lazy_jump) / cs_scale
        full_velocity = full_distance / max(adjusted_time, MIN_TIME_MS)
        factor = _size_factor(cs_scale)
        velocity_load = full_velocity * factor
        rate = 1000.0 / max(adjusted_time, MIN_TIME_MS)
        full_ref_radii = full_distance / REFERENCE_RADIUS_PX
        lazy_jump_ref_radii = (lazy_jump / cs_scale) / REFERENCE_RADIUS_PX
        head_dominance = (lazy_jump / cs_scale) / max(full_distance, 1e-12)
        wide_head_dominance = head_dominance * _clamp(
            (lazy_jump_ref_radii - 3.25) / 0.50
        )
        full_distances.append(full_distance)
        full_velocities.append(full_velocity)
        size_factors.append(factor)
        strict_time_weight = _fade_after(
            adjusted_time,
            full_until=300.0,
            zero_at=360.0,
        )
        broad_time_weight = _fade_after(
            adjusted_time,
            full_until=220.0,
            zero_at=300.0,
        )

        if previous_path_valid:
            morphology_opportunity_count += 1
        if not previous_path_valid or angle is None:
            finish_strict_chain()
            finish_broad_chain()
            previous_path_valid = True
            previous_strict_time_weight = strict_time_weight
            previous_broad_time_weight = broad_time_weight
            previous_velocity_load = velocity_load
            previous_rate = rate
            previous_spacing = full_ref_radii
            previous_head_dominance = head_dominance
            previous_wide_head_dominance = wide_head_dominance
            previous_angle = angle
            previous = row
            continue

        directional_pair_count += 1
        angle_change = (
            0.0
            if previous_angle is None
            else min(abs(angle - previous_angle), math.pi)
        )
        morphology_pair = (
            strict_time_weight > 0.0
            and angle >= math.pi / 2.0
            and full_ref_radii >= 0.55
        )
        if morphology_pair:
            morphology_count += 1
            morphology_spacings.append(full_ref_radii)
            head_dominance_sum += head_dominance
            wide_head_dominance_sum += wide_head_dominance

        strict = (
            strict_time_weight > 0.0
            and angle >= 3.0 * math.pi / 4.0
            and full_ref_radii >= 1.25
        )
        if strict:
            extends = strict_chain is not None and angle_change <= math.pi / 4.0
            if not extends:
                finish_strict_chain()
                prior_eligible = (
                    previous_strict_time_weight > 0.0
                    and previous_spacing >= 1.25
                )
                prior_weight = (
                    previous_strict_time_weight if prior_eligible else 0.0
                )
                strict_chain = {
                    "notes": 1.0 + prior_weight + strict_time_weight,
                    "velocity_loads": (
                        [previous_velocity_load] if prior_eligible else []
                    )
                    + [velocity_load],
                    "smoothness": [1.0],
                    "spacings": (
                        [previous_spacing] if prior_eligible else []
                    )
                    + [full_ref_radii],
                    "wide_sum": (
                        previous_wide_head_dominance if prior_eligible else 0.0
                    )
                    + wide_head_dominance,
                }
                step_smoothness = 1.0
            else:
                assert strict_chain is not None
                strict_chain["notes"] += strict_time_weight
                strict_chain["velocity_loads"].append(velocity_load)
                strict_chain["spacings"].append(full_ref_radii)
                strict_chain["wide_sum"] += wide_head_dominance
                step_smoothness = 1.0 - angle_change / (math.pi / 4.0)
                strict_chain["smoothness"].append(step_smoothness)
            assert strict_chain is not None
            strict_count += 1
            strict_lengths.append(float(strict_chain["notes"]))
            strict_velocity_loads.append(
                velocity_load
                * (
                    1.0
                    + min(float(strict_chain["notes"]) - 1.0, 12.0) / 12.0
                )
            )
            strict_smoothness.append(step_smoothness)
        else:
            finish_strict_chain()

        # Fixed CS4 reference radii make morphology invariant under HR.  There
        # is deliberately no upper spacing cap: long spaced streams remain a
        # chain and are separated from head-dominated wide jumps.
        broad = (
            broad_time_weight > 0.0
            and angle >= math.pi / 2.0
            and full_ref_radii >= 0.55
        )
        if broad:
            if broad_chain is None:
                prior_eligible = (
                    previous_broad_time_weight > 0.0
                    and previous_spacing >= 0.55
                )
                prior_weight = (
                    previous_broad_time_weight if prior_eligible else 0.0
                )
                broad_chain = {
                    "notes": 1.0 + prior_weight + broad_time_weight,
                    "rates": ([previous_rate] if prior_eligible else []) + [rate],
                    "spacings": (
                        [previous_spacing] if prior_eligible else []
                    )
                    + [full_ref_radii],
                    "wide_sum": (
                        previous_wide_head_dominance if prior_eligible else 0.0
                    )
                    + wide_head_dominance,
                }
            else:
                broad_chain["notes"] += broad_time_weight
                broad_chain["rates"].append(rate)
                broad_chain["spacings"].append(full_ref_radii)
                broad_chain["wide_sum"] += wide_head_dominance
            broad_count += 1
            broad_longest = max(broad_longest, float(broad_chain["notes"]))
            broad_rates.append(rate)
            broad_spacings.append(full_ref_radii)
        else:
            finish_broad_chain()

        previous_path_valid = True
        previous_strict_time_weight = strict_time_weight
        previous_broad_time_weight = broad_time_weight
        previous_velocity_load = velocity_load
        previous_rate = rate
        previous_spacing = full_ref_radii
        previous_head_dominance = head_dominance
        previous_wide_head_dominance = wide_head_dominance
        previous_angle = angle
        previous = row

    finish_strict_chain()
    finish_broad_chain()

    strict_joint_peak_raw = 0.0
    morphology_joint_peak_raw = 0.0
    joint_coherence_gate = 0.0
    for chain in strict_chains:
        strict_peak, morphology_peak, coherence = _strict_chain_evidence(chain)
        strict_joint_peak_raw = max(strict_joint_peak_raw, strict_peak)
        morphology_joint_peak_raw = max(
            morphology_joint_peak_raw,
            morphology_peak,
        )
        joint_coherence_gate = max(joint_coherence_gate, coherence)
    broad_joint_peak_raw = 0.0
    for chain in broad_chains:
        broad_peak, coherence = _broad_chain_evidence(chain)
        broad_joint_peak_raw = max(broad_joint_peak_raw, broad_peak)
        joint_coherence_gate = max(joint_coherence_gate, coherence)

    full_count = len(full_distances)
    directional_coverage = _ratio(
        directional_pair_count,
        morphology_opportunity_count,
    )
    strict_coverage = _ratio(strict_count, directional_pair_count)
    broad_coverage = _ratio(broad_count, directional_pair_count)
    strict_length = _quantile(strict_lengths, 0.90)
    strict_velocity = _quantile(strict_velocity_loads, 0.90)
    smoothness = (
        sum(strict_smoothness) / len(strict_smoothness)
        if strict_smoothness
        else 0.0
    )
    broad_rate = _quantile(broad_rates, 0.90)
    broad_spacing = _quantile(broad_spacings, 0.90)
    morphology_spacing = _quantile(morphology_spacings, 0.90)
    wide_head_dominance_share = (
        0.0
        if morphology_count <= 0
        else wide_head_dominance_sum / morphology_count
    )
    full_path_coverage = _ratio(full_count, transition_candidates)
    slider_coverage = _ratio(slider_valid_count, nonspinner_count)
    slider_velocity_raw = _quantile(slider_velocities, 0.90)
    slider_velocity_load = _quantile(slider_velocity_loads, 0.90)
    gates = _flow_gates(
        strict_length=strict_length,
        strict_velocity=strict_velocity,
        strict_coverage=strict_coverage,
        broad_coverage=broad_coverage,
        strict_joint_peak_raw=strict_joint_peak_raw,
        broad_joint_peak_raw=broad_joint_peak_raw,
        morphology_joint_peak_raw=morphology_joint_peak_raw,
        joint_coherence_gate=joint_coherence_gate,
        slider_velocity=slider_velocity_load,
        slider_coverage=slider_coverage,
        full_path_coverage=full_path_coverage,
        directional_coverage=directional_coverage,
    )
    return {
        "status": "OK" if full_count or slider_valid_count else "INSUFFICIENT",
        "pairing_policy": FLOW_PAIRING_POLICY,
        "nonspinner_object_count": nonspinner_count,
        "transition_candidate_count": transition_candidates,
        "full_path_pair_count": full_count,
        "full_path_pair_coverage": full_path_coverage,
        "morphology_opportunity_count": morphology_opportunity_count,
        "directional_pair_count": directional_pair_count,
        "directional_pair_coverage": directional_coverage,
        "full_path_distance_raw_p95_px": _quantile(full_distances, 0.95),
        "full_path_distance_raw_p99_px": _quantile(full_distances, 0.99),
        "full_path_velocity_raw_p95_px_per_ms": _quantile(full_velocities, 0.95),
        "full_path_velocity_raw_p99_px_per_ms": _quantile(full_velocities, 0.99),
        "strict_pair_count": strict_count,
        "strict_pair_coverage": strict_coverage,
        "strict_chain_length_p90_notes": strict_length,
        "strict_velocity_load_p90_px_per_ms": strict_velocity,
        "strict_smoothness_mean": smoothness,
        "broad_pair_count": broad_count,
        "broad_pair_coverage": broad_coverage,
        "broad_longest_chain_notes": broad_longest,
        "broad_rate_p90_per_s": broad_rate,
        "broad_full_path_ref_radii_p90": broad_spacing,
        "morphology_pair_count": morphology_count,
        "morphology_full_path_ref_radii_p90": morphology_spacing,
        "head_dominance_weight_sum": head_dominance_sum,
        "wide_head_dominance_weight_sum": wide_head_dominance_sum,
        "wide_head_dominance_share": wide_head_dominance_share,
        "slider_object_count": slider_count,
        "slider_travel_valid_count": slider_valid_count,
        "slider_note_coverage": slider_coverage,
        "slider_travel_velocity_raw_p90_px_per_ms": slider_velocity_raw,
        "slider_travel_velocity_load_p90_px_per_ms": slider_velocity_load,
        "size_factor_p50": _quantile(size_factors, 0.50) if size_factors else 1.0,
        "strict_joint_peak_raw": strict_joint_peak_raw,
        "broad_joint_peak_raw": broad_joint_peak_raw,
        "morphology_joint_peak_raw": morphology_joint_peak_raw,
        "joint_coherence_gate": joint_coherence_gate,
        **gates,
    }


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], path: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{path} schema mismatch: missing={missing}, extra={extra}")


def _require_close(actual: float, expected: float, path: str) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(f"{path} inconsistent: {actual!r} != {expected!r}")


def _validate_numbers(
    component: Mapping[str, Any],
    *,
    count_keys: frozenset[str],
    path: str,
) -> None:
    for key, value in component.items():
        if key in {"status", "pairing_policy"}:
            continue
        if key in count_keys:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{path}.{key} must be a non-negative integer")
            continue
        number = _finite(value)
        if number is None or number < 0.0:
            raise ValueError(f"{path}.{key} must be finite and non-negative")
        if key in _UNIT_INTERVAL_KEYS and number > 1.0:
            raise ValueError(f"{path}.{key} must be in [0, 1]")


def _validate_jump(component: Mapping[str, Any]) -> None:
    _require_exact_keys(component, _JUMP_KEYS, "aim_routing.jump")
    if component["status"] not in {"OK", "INSUFFICIENT"}:
        raise ValueError("aim_routing.jump.status is invalid")
    if component["pairing_policy"] != JUMP_PAIRING_POLICY:
        raise ValueError("aim_routing.jump.pairing_policy mismatch")
    _validate_numbers(component, count_keys=_JUMP_COUNT_KEYS, path="aim_routing.jump")

    candidates = component["transition_candidate_count"]
    valid = component["valid_pair_count"]
    primary = component["minimum_minimum_pair_count"]
    fallback = component["head_full_fallback_pair_count"]
    lazy_full = component["lazy_full_pair_count"]
    high = component["high_pair_count"]
    high_weight = component["high_pair_weight_sum"]
    longest = component["longest_high_chain_pairs"]
    longest_high_weight = component["longest_high_chain_weight"]
    circle = component["circle_pair_count"]
    circle_large = component["circle_large_pair_count"]
    circle_large_weight = component["circle_large_pair_weight_sum"]
    local_window_size = component["circle_large_local_window_size"]
    local_window_count = component["circle_large_local_window_count"]
    local_weight_window_size = component[
        "circle_large_local_window_weight_size"
    ]
    local_window_weight = component["circle_large_local_window_weight_sum"]
    longest_circle_large = component["longest_circle_large_chain_pairs"]
    longest_circle_large_weight = component[
        "longest_circle_large_chain_weight"
    ]
    if valid != primary + fallback or valid > candidates:
        raise ValueError("aim_routing.jump pairing counts are inconsistent")
    if lazy_full > candidates:
        raise ValueError("aim_routing.jump lazy/full count is inconsistent")
    if high > valid or longest > high:
        raise ValueError("aim_routing.jump high-pair counts are inconsistent")
    if (
        high_weight > valid
        or (
            longest_high_weight > high_weight
            and not math.isclose(
                longest_high_weight,
                high_weight,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        )
    ):
        raise ValueError("aim_routing.jump weighted high-pair evidence is inconsistent")
    if circle_large > circle or circle > valid:
        raise ValueError("aim_routing.jump circle-pair counts are inconsistent")
    if circle_large_weight > circle and not math.isclose(
        circle_large_weight,
        circle,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError("aim_routing.jump weighted circle evidence is inconsistent")
    if (
        local_window_count > local_window_size
        or local_window_size > min(8, valid)
        or local_window_count > circle_large
        or longest_circle_large > circle_large
        or (
            local_window_weight > circle_large_weight
            and not math.isclose(
                local_window_weight,
                circle_large_weight,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        )
        or (
            longest_circle_large_weight > circle_large_weight
            and not math.isclose(
                longest_circle_large_weight,
                circle_large_weight,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        )
        or local_weight_window_size > min(8, valid)
        or local_window_weight > local_weight_window_size
    ):
        raise ValueError("aim_routing.jump local circle evidence is inconsistent")
    if (component["status"] == "OK") != (valid > 0):
        raise ValueError("aim_routing.jump.status contradicts valid_pair_count")
    _require_close(
        component["valid_pair_coverage"],
        _ratio(valid, candidates),
        "jump.valid_pair_coverage",
    )
    _require_close(component["high_pair_share"], _ratio(high, valid), "jump.high_pair_share")
    _require_close(
        component["high_pair_weight_share"],
        _ratio(high_weight, valid),
        "jump.high_pair_weight_share",
    )
    _require_close(
        component["circle_large_pair_share"],
        _ratio(circle_large, circle),
        "jump.circle_large_pair_share",
    )
    _require_close(
        component["circle_large_valid_pair_share"],
        _ratio(circle_large, valid),
        "jump.circle_large_valid_pair_share",
    )
    _require_close(
        component["circle_large_pair_weight_share"],
        _ratio(circle_large_weight, circle),
        "jump.circle_large_pair_weight_share",
    )
    _require_close(
        component["circle_large_valid_pair_weight_share"],
        _ratio(circle_large_weight, valid),
        "jump.circle_large_valid_pair_weight_share",
    )
    _require_close(
        component["circle_large_local_window_share"],
        _ratio(local_window_count, local_window_size),
        "jump.circle_large_local_window_share",
    )
    _require_close(
        component["circle_large_local_window_weight_share"],
        _ratio(local_window_weight, local_weight_window_size),
        "jump.circle_large_local_window_weight_share",
    )
    for p95, p99 in (
        ("distance_raw_p95_px", "distance_raw_p99_px"),
        ("velocity_raw_p95_px_per_ms", "velocity_raw_p99_px_per_ms"),
        ("kinematic_joint_p95", "kinematic_joint_p99"),
        ("lazy_full_distance_raw_p95_px", "lazy_full_distance_raw_p99_px"),
        (
            "lazy_full_velocity_raw_p95_px_per_ms",
            "lazy_full_velocity_raw_p99_px_per_ms",
        ),
        (
            "lazy_full_kinematic_joint_p95",
            "lazy_full_kinematic_joint_p99",
        ),
        ("joint_load_p95", "joint_load_p99"),
    ):
        if component[p95] > component[p99] and not math.isclose(
            component[p95], component[p99], rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError(f"aim_routing.jump requires {p95} <= {p99}")
    expected = _jump_gates(
        load_p95=component["joint_load_p95"],
        load_p99=component["joint_load_p99"],
        high_weight_share=component["high_pair_weight_share"],
        longest_high_chain_weight=longest_high_weight,
        circle_large_weight_sum=circle_large_weight,
        circle_large_valid_weight_share=component[
            "circle_large_valid_pair_weight_share"
        ],
        circle_large_local_weight_sum=local_window_weight,
        circle_large_local_weight_share=component[
            "circle_large_local_window_weight_share"
        ],
        longest_circle_large_chain_weight=longest_circle_large_weight,
        kinematic_joint_p99=component["kinematic_joint_p99"],
        lazy_full_kinematic_joint_p99=component[
            "lazy_full_kinematic_joint_p99"
        ],
        valid_pair_coverage=component["valid_pair_coverage"],
    )
    for key, value in expected.items():
        _require_close(component[key], value, f"jump.{key}")


def _validate_flow(component: Mapping[str, Any]) -> None:
    _require_exact_keys(component, _FLOW_KEYS, "aim_routing.flow")
    if component["status"] not in {"OK", "INSUFFICIENT"}:
        raise ValueError("aim_routing.flow.status is invalid")
    if component["pairing_policy"] != FLOW_PAIRING_POLICY:
        raise ValueError("aim_routing.flow.pairing_policy mismatch")
    _validate_numbers(component, count_keys=_FLOW_COUNT_KEYS, path="aim_routing.flow")

    objects = component["nonspinner_object_count"]
    candidates = component["transition_candidate_count"]
    full = component["full_path_pair_count"]
    opportunities = component["morphology_opportunity_count"]
    directional = component["directional_pair_count"]
    strict = component["strict_pair_count"]
    broad = component["broad_pair_count"]
    morphology = component["morphology_pair_count"]
    head_dominance = component["head_dominance_weight_sum"]
    wide = component["wide_head_dominance_weight_sum"]
    sliders = component["slider_object_count"]
    valid_sliders = component["slider_travel_valid_count"]
    if full > candidates or opportunities > full or directional > opportunities:
        raise ValueError("aim_routing.flow opportunity counts are inconsistent")
    if strict > directional or broad > directional or morphology > directional:
        raise ValueError("aim_routing.flow transition counts are inconsistent")
    if wide > head_dominance or head_dominance > morphology:
        raise ValueError("aim_routing.flow head-dominance weights are inconsistent")
    if valid_sliders > sliders or sliders > objects:
        raise ValueError("aim_routing.flow slider counts are inconsistent")
    if (component["status"] == "OK") != (full > 0 or valid_sliders > 0):
        raise ValueError("aim_routing.flow.status contradicts available evidence")
    _require_close(
        component["full_path_pair_coverage"],
        _ratio(full, candidates),
        "flow.full_path_pair_coverage",
    )
    _require_close(
        component["directional_pair_coverage"],
        _ratio(directional, opportunities),
        "flow.directional_pair_coverage",
    )
    _require_close(
        component["strict_pair_coverage"],
        _ratio(strict, directional),
        "flow.strict_pair_coverage",
    )
    _require_close(
        component["broad_pair_coverage"],
        _ratio(broad, directional),
        "flow.broad_pair_coverage",
    )
    _require_close(
        component["wide_head_dominance_share"],
        0.0 if morphology <= 0 else wide / morphology,
        "flow.wide_head_dominance_share",
    )
    _require_close(
        component["slider_note_coverage"],
        _ratio(valid_sliders, objects),
        "flow.slider_note_coverage",
    )
    for p95, p99 in (
        ("full_path_distance_raw_p95_px", "full_path_distance_raw_p99_px"),
        (
            "full_path_velocity_raw_p95_px_per_ms",
            "full_path_velocity_raw_p99_px_per_ms",
        ),
    ):
        if component[p95] > component[p99] and not math.isclose(
            component[p95], component[p99], rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError(f"aim_routing.flow requires {p95} <= {p99}")
    expected = _flow_gates(
        strict_length=component["strict_chain_length_p90_notes"],
        strict_velocity=component["strict_velocity_load_p90_px_per_ms"],
        strict_coverage=component["strict_pair_coverage"],
        broad_coverage=component["broad_pair_coverage"],
        strict_joint_peak_raw=component["strict_joint_peak_raw"],
        broad_joint_peak_raw=component["broad_joint_peak_raw"],
        morphology_joint_peak_raw=component["morphology_joint_peak_raw"],
        joint_coherence_gate=component["joint_coherence_gate"],
        slider_velocity=component[
            "slider_travel_velocity_load_p90_px_per_ms"
        ],
        slider_coverage=component["slider_note_coverage"],
        full_path_coverage=component["full_path_pair_coverage"],
        directional_coverage=component["directional_pair_coverage"],
    )
    for key, value in expected.items():
        _require_close(component[key], value, f"flow.{key}")


def validate_measure(measure: Any) -> dict[str, Any]:
    """Validate the exact component schema and every derived finite value.

    The input is returned unchanged on success so callers can validate at the
    extraction/analysis boundary without introducing a hidden mutation.
    """
    if not isinstance(measure, dict):
        raise ValueError("aim_routing component must be a dict")
    _require_exact_keys(measure, _TOP_LEVEL_KEYS, "aim_routing")
    if measure["schema_version"] != SCHEMA_VERSION:
        raise ValueError("aim_routing schema_version mismatch")
    if measure["local_signal_version"] != LOCAL_SIGNAL_VERSION:
        raise ValueError("aim_routing local_signal_version mismatch")
    jump = measure["jump"]
    flow = measure["flow"]
    if not isinstance(jump, dict) or not isinstance(flow, dict):
        raise ValueError("aim_routing jump and flow components must be dicts")
    _validate_jump(jump)
    _validate_flow(flow)
    return measure


def axis_evidence(measure: Any) -> dict[str, tuple[float, float, dict[str, Any]]]:
    """Return validated support/counterevidence tuples for beta integration."""
    validated = validate_measure(measure)
    return {
        axis: (
            validated[key]["support"],
            validated[key]["counterevidence"],
            dict(validated[key]),
        )
        for axis, key in (("jump_aim", "jump"), ("flow_aim", "flow"))
    }


def aim_routing_measure(
    local_rows: Iterable[Mapping[str, Any]],
    *,
    source_local_signal_version: str,
) -> dict[str, Any]:
    """Extract deterministic, target-free Jump/Flow evidence from Local 0.4 rows.

    The source version is mandatory because object rows intentionally do not
    repeat contract metadata.  Refusing an unlabelled or historical row set
    prevents a caller from silently stamping Local 0.3 geometry as Local 0.4.
    """
    if source_local_signal_version != LOCAL_SIGNAL_VERSION:
        raise ValueError(
            "aim routing requires Local Signal "
            f"{LOCAL_SIGNAL_VERSION}, got {source_local_signal_version!r}"
        )
    rows = list(local_rows)
    measure = {
        "schema_version": SCHEMA_VERSION,
        "local_signal_version": LOCAL_SIGNAL_VERSION,
        "jump": _jump_component(rows),
        "flow": _flow_component(rows),
    }
    return validate_measure(measure)


__all__ = [
    "SCHEMA_VERSION",
    "LOCAL_SIGNAL_VERSION",
    "REFERENCE_RADIUS_PX",
    "REFERENCE_CS_SCALE",
    "JUMP_PAIRING_POLICY",
    "FLOW_PAIRING_POLICY",
    "aim_routing_measure",
    "validate_measure",
    "axis_evidence",
]
