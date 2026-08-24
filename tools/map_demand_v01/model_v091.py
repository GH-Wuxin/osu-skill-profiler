"""Map Demand V0.91: de-duplicated mechanics with a soft total-SR anchor.

V0.9 remains replayable. This revision retains its human-checked ordering,
then replaces or de-duplicates the mechanics that assisted review exposed as
conflated:

* Jump Aim is distance/speed first, with only a mild circle-size term.
* Spatial Precision measures tolerance, settling speed, and micro-correction.
* Flow Aim requires a fast, smooth, persistent curved chain.
* Finger Control requires locally fast non-trivial interval changes.
* Reading observes real spatial overlap inside the approach window.

V0.9's already human-checked ordering is retained where the older atomic
baseline is known to understate a mechanic, but each exposed overlay is
replaced or de-duplicated before scaling.  All star-equivalent axes then pass
through one final soft anchor.  The anchor is
the local NM star rating when available (adjusted conservatively for mods), or
a robust estimate from the de-duplicated physical axes. It is a scale reference, never
a hard equality constraint: specialist axes may exceed total SR, but the
unbounded calibration tail can no longer add arbitrary double-digit bonuses.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Optional

from . import contract as C
from . import model as v06
from . import model_v08 as v08
from . import model_v09 as v09
from .archetype_v08 import AXIS_ORDER, classify_axes
from .mod_context_v01 import normalize_mods
from .mod_transform_v01 import transform_beatmap

ALGORITHM_ID = "MAP_DEMAND_ATOMIC_V091"
MAP_DEMAND_VERSION = "0.9.1"
SCHEMA_VERSION = "map_demand_v0.9.1"
AXIS_SCHEMA_VERSION = v08.AXIS_SCHEMA_VERSION
MECHANISM_SPEC = (
    "MAP_DEMAND_ATOMIC_V091:base=v09_ordering_then_mechanism_deduplication;"
    "jump=distance_speed_with_mild_cs_and_clock_speed_tail_recovery;"
    "precision=tolerance_settling_micro_correction;"
    "flow=fast_smooth_persistent_curved_chain;"
    "finger=fast_nontrivial_local_interval_change_once;"
    "reading=visible_window_geometric_overlap_plus_relative_ar_hd;"
    "scale=single_soft_total_sr_anchor_saturating_tail"
)

_PRIVATE_X = "v091.start_x_px"
_PRIVATE_Y = "v091.start_y_px"
_STAR_AXES = (
    "jump_aim",
    "flow_aim",
    "aim_control",
    "spatial_precision",
    "raw_speed",
    "finger_control",
    "reading",
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
    return C.percentile_linear(sorted(values), _clamp(q, 0.0, 1.0))


def calibration_id(base_calibration_id: str) -> str:
    payload = json.dumps(
        {"base_calibration_id": base_calibration_id, "mechanism_spec": MECHANISM_SPEC},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"mdoverlay_v091:{digest}"


def extract_from_path(
    path: str, requested_mods: Iterable[str] = ()
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Extract frozen signals and attach V0.91-private absolute positions.

    Absolute coordinates intentionally do not alter the frozen Local Signal
    0.3 contract.  They exist only in this model's transient row copies and
    are immediately aggregated by :func:`extract_components`.
    """
    rows, features, metadata = v06.extract_from_path(path, requested_mods=requested_mods)

    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src = os.path.join(root, "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from osu_skill_profiler.parser.osu_parser import parse_osu_file

    source = parse_osu_file(path)
    transformed, _ = transform_beatmap(source, normalize_mods(requested_mods))
    if len(rows) != len(transformed.hit_objects):
        raise ValueError("V0.91 position alignment failed")
    private_rows: list[dict[str, Any]] = []
    for row, obj in zip(rows, transformed.hit_objects):
        enriched = dict(row)
        enriched[_PRIVATE_X] = float(obj.x)
        enriched[_PRIVATE_Y] = float(obj.y)
        private_rows.append(enriched)
    return private_rows, features, metadata


def sha256_file_bytes(data: bytes) -> str:
    return v06.sha256_file_bytes(data)


def _visible_overlap(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    objects: list[tuple[float, float, float, float, float]] = []
    for row in rows:
        if row.get("ls.object_type") == "spinner":
            continue
        values = (
            _finite(row.get("ls.start_time_ms")),
            _finite(row.get(_PRIVATE_X)),
            _finite(row.get(_PRIVATE_Y)),
            _finite(row.get("ls.radius_px")),
            _finite(row.get("ls.preempt_ms")),
        )
        if any(value is None for value in values):
            continue
        time_ms, x, y, radius, preempt = (float(value) for value in values)
        if radius <= 0.0 or preempt <= 0.0:
            continue
        objects.append((time_ms, x, y, radius, preempt))
    objects.sort(key=lambda item: item[0])
    loads = [0.0] * len(objects)
    clusters = [0.0] * len(objects)
    overlap_pairs = 0
    stack_pairs = 0
    visible_pairs = 0
    for i, (time_i, x_i, y_i, radius_i, preempt_i) in enumerate(objects):
        for j in range(i + 1, len(objects)):
            time_j, x_j, y_j, radius_j, preempt_j = objects[j]
            dt = time_j - time_i
            if dt > max(preempt_i, preempt_j):
                break
            if dt > min(preempt_i, preempt_j):
                continue
            visible_pairs += 1
            radius = (radius_i + radius_j) / 2.0
            distance = math.hypot(x_j - x_i, y_j - y_i)
            overlap = _clamp(1.0 - distance / max(2.0 * radius, 1.0), 0.0, 1.0)
            cluster = _clamp(1.0 - distance / max(4.0 * radius, 1.0), 0.0, 1.0)
            loads[i] += overlap**1.5
            loads[j] += overlap**1.5
            clusters[i] += cluster
            clusters[j] += cluster
            if overlap > 0.0:
                overlap_pairs += 1
            if distance <= 0.5 * radius:
                stack_pairs += 1
    count = len(objects)
    return {
        "v091_visible_object_count": count,
        "v091_visible_pair_count": visible_pairs,
        "v091_visible_overlap_load_p90": _quantile(loads, 0.90),
        "v091_visible_cluster_load_p90": _quantile(clusters, 0.90),
        "v091_visible_overlap_pair_share": (
            None if visible_pairs == 0 else overlap_pairs / visible_pairs
        ),
        "v091_visible_stack_object_share": (
            None if count == 0 else min(1.0, 2.0 * stack_pairs / count)
        ),
    }


def _mechanic_components(rows: list[dict[str, Any]]) -> dict[str, Any]:
    jump_distance: list[float] = []
    jump_velocity: list[float] = []
    jump_cs_scale: list[float] = []
    precision_tolerance: list[float] = []
    precision_settling: list[float] = []
    precision_micro: list[float] = []
    flow_chain_lengths: list[float] = []
    flow_chain_velocity: list[float] = []
    flow_chain_smoothness: list[float] = []
    flow_eligible = 0
    flow_hits = 0
    fast_novelty: list[float] = []
    fast_changes = 0
    intervals: list[float] = []

    previous_distance: float | None = None
    previous_angle: float | None = None
    flow_chain = 0
    for row in rows:
        if row.get("ls.object_type") == "spinner":
            flow_chain = 0
            previous_distance = None
            previous_angle = None
            continue
        dt = _finite(row.get("ls.minimum_jump_time_ms"))
        adjusted_dt = _finite(row.get("ls.adjusted_delta_time_ms"))
        raw_distance = _finite(row.get("ls.jump_distance_raw_px"))
        radius = _finite(row.get("ls.radius_px"))
        angle = _finite(row.get("ls.slider_aware_angle_rad"))
        cs_scale = _finite(row.get("ls.cs_scale"))

        if adjusted_dt is not None and adjusted_dt > 0.0:
            intervals.append(adjusted_dt)
        if dt is not None and dt > 0.0 and raw_distance is not None and raw_distance >= 0.0:
            velocity = raw_distance / max(dt, C.MIN_TIME_MS)
            jump_distance.append(raw_distance)
            jump_velocity.append(velocity)
            if cs_scale is not None and cs_scale > 0.0:
                jump_cs_scale.append(cs_scale)
            if radius is not None and radius > 0.0:
                tolerance = raw_distance / max(2.0 * radius, 1.0)
                settling = tolerance * math.sqrt(max(velocity, 0.0))
                precision_tolerance.append(tolerance)
                precision_settling.append(settling)
                if (
                    previous_distance is not None
                    and previous_distance >= 5.0 * radius
                    and raw_distance <= 3.0 * radius
                    and dt <= 250.0
                    and angle is not None
                    and angle <= math.pi / 2.0
                ):
                    precision_micro.append(
                        (previous_distance / max(5.0 * radius, 1.0))
                        * (1.0 - raw_distance / max(3.0 * radius, 1.0))
                        * (250.0 / max(dt, 50.0))
                    )
            previous_distance = raw_distance

            if angle is not None and adjusted_dt is not None:
                flow_eligible += 1
                angle_change = (
                    0.0
                    if previous_angle is None
                    else min(abs(angle - previous_angle), math.pi)
                )
                smooth_curve = (
                    adjusted_dt <= 300.0
                    and angle >= 3.0 * math.pi / 4.0
                    and angle_change <= math.pi / 4.0
                    and raw_distance >= 1.25 * (radius or 32.0)
                )
                if smooth_curve:
                    flow_chain += 1
                    flow_hits += 1
                    flow_chain_lengths.append(float(flow_chain))
                    flow_chain_velocity.append(
                        velocity * (1.0 + min(flow_chain, 12) / 12.0)
                    )
                    flow_chain_smoothness.append(1.0 - angle_change / (math.pi / 4.0))
                else:
                    flow_chain = 0
                previous_angle = angle
        else:
            flow_chain = 0

    for previous, current in zip(intervals, intervals[1:]):
        if max(previous, current) > 220.0:
            continue
        ratio_log = abs(math.log2(previous / current))
        # Common 1:1, 1:sqrt(2), 1:2 and their inverses do not by themselves
        # constitute finger-control evidence.  Novelty measures distance from
        # those ordinary rhythmic lattices.
        novelty = min(abs(ratio_log - lattice) for lattice in (0.0, 0.5, 1.0))
        fast_novelty.append(novelty)
        if novelty >= 0.12:
            fast_changes += 1

    result: dict[str, Any] = {
        "v091_jump_distance_raw_p90_px": _quantile(jump_distance, 0.90),
        "v091_jump_velocity_raw_p90_px_per_ms": _quantile(jump_velocity, 0.90),
        "v091_jump_cs_scale_median": _quantile(jump_cs_scale, 0.50),
        "v091_precision_tolerance_p90": _quantile(precision_tolerance, 0.90),
        "v091_precision_settling_p90": _quantile(precision_settling, 0.90),
        "v091_precision_micro_correction_p90": _quantile(precision_micro, 0.90) or 0.0,
        "v091_precision_micro_correction_count": len(precision_micro),
        "v091_flow_eligible_count": flow_eligible,
        "v091_flow_chain_share": None if flow_eligible == 0 else flow_hits / flow_eligible,
        "v091_flow_chain_length_p90": _quantile(flow_chain_lengths, 0.90),
        "v091_flow_chain_velocity_p90": _quantile(flow_chain_velocity, 0.90),
        "v091_flow_chain_smoothness_mean": (
            None if not flow_chain_smoothness else sum(flow_chain_smoothness) / len(flow_chain_smoothness)
        ),
        "v091_finger_fast_pair_count": len(fast_novelty),
        "v091_finger_nontrivial_change_share": (
            None if not fast_novelty else fast_changes / len(fast_novelty)
        ),
        "v091_finger_novelty_p90": _quantile(fast_novelty, 0.90),
    }
    result.update(_visible_overlap(rows))
    return result


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Optional[dict[str, Any]] = None,
    difficulty: Optional[dict[str, Any]] = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    rows = list(local_rows)
    components, warnings = v09.extract_components(
        rows,
        features,
        difficulty=difficulty,
        clock_rate=clock_rate,
        effective_mods=effective_mods,
    )
    private = _mechanic_components(rows)
    components.update(private)
    if private["v091_visible_object_count"] == 0:
        warnings.append("v091 reading overlap: absolute object positions unavailable")
    if private["v091_flow_eligible_count"] == 0:
        warnings.append("v091 flow: no eligible geometric transitions")
    return components, warnings


def _axis_stars(axes: dict[str, Any], axis: str) -> float | None:
    item = axes.get(axis)
    if not isinstance(item, dict) or item.get("status") != "EMITTED":
        return None
    return _finite(item.get("demand_star_equivalent"))


def _set_axis(
    axes: dict[str, Any], axis: str, stars: float, mechanism: str, evidence: dict[str, Any]
) -> None:
    item = axes.get(axis)
    old = _axis_stars(axes, axis)
    if not isinstance(item, dict) or old is None:
        return
    value = max(0.0, float(stars))
    item["demand_star_equivalent"] = value
    item["score"] = value / 10.0
    item["percentile_rank"] = None
    item["scale_method"] = "V091_PRE_ANCHOR_MECHANIC"
    item["method"] = mechanism
    item.setdefault("evidence", []).append(
        {
            "component": mechanism,
            "incoming_v09_stars": old,
            "mechanic_stars_before_anchor": value,
            **evidence,
            "evidence_tag": "HEURISTIC_V091_REQUIRES_HUMAN_VALIDATION",
        }
    )


def _jump_movement_severity(c: dict[str, Any]) -> float:
    distance = _finite(c.get("v091_jump_distance_raw_p90_px"))
    velocity = _finite(c.get("v091_jump_velocity_raw_p90_px_per_ms"))
    if distance is None or velocity is None:
        return 0.0
    distance_gate = _clamp((distance - 140.0) / 190.0, 0.0, 1.0)
    velocity_gate = _clamp((velocity - 0.90) / 2.30, 0.0, 1.0)
    return 0.35 * distance_gate + 0.65 * velocity_gate


def _jump_precision_flow_finger(
    axes: dict[str, Any], c: dict[str, Any], mod_context: dict[str, Any]
) -> None:
    anchor_hint = _estimate_anchor(axes)

    jump = _axis_stars(axes, "jump_aim")
    cs_scale = _finite(c.get("v091_jump_cs_scale_median"))
    if jump is not None and cs_scale is not None and cs_scale > 0.0:
        # V0.6 fully normalised distance by CS.  Retain only a mild 18% CS
        # exponent here; the remaining demand stays distance/time driven.
        correction = cs_scale ** -0.08
        clock_rate = _finite(mod_context.get("clock_rate")) or 1.0
        speedup_gate = _clamp((clock_rate - 1.0) / 0.5, 0.0, 1.0)
        movement_severity = _jump_movement_severity(c)
        # The calibrated percentile is already nearly saturated on extreme DT
        # jumps. Recover the otherwise invisible tail using raw distance and
        # movement speed, but never alter NM/HT through this mechanism.
        speedup_tail_multiplier = 1.0 + 0.30 * speedup_gate * movement_severity
        _set_axis(
            axes,
            "jump_aim",
            jump * correction * speedup_tail_multiplier,
            "DISTANCE_SPEED_MILD_CS_CLOCK_TAIL_JUMP_V091",
            {
                "cs_scale_median": cs_scale,
                "legacy_full_cs_correction": correction,
                "clock_rate": clock_rate,
                "speedup_gate": speedup_gate,
                "movement_severity": movement_severity,
                "speedup_tail_multiplier": speedup_tail_multiplier,
                "raw_distance_p90_px": c.get("v091_jump_distance_raw_p90_px"),
                "raw_velocity_p90_px_per_ms": c.get("v091_jump_velocity_raw_p90_px_per_ms"),
            },
        )

    tolerance = _finite(c.get("v091_precision_tolerance_p90"))
    settling = _finite(c.get("v091_precision_settling_p90"))
    micro = _finite(c.get("v091_precision_micro_correction_p90"))
    if None not in (tolerance, settling, micro) and anchor_hint is not None:
        tolerance_gate = _clamp((float(tolerance) - 1.5) / 5.0, 0.0, 1.0)
        settling_gate = _clamp((float(settling) - 0.8) / 4.0, 0.0, 1.0)
        micro_gate = _clamp(float(micro) / 1.5, 0.0, 1.0)
        precision_index = 0.55 * tolerance_gate + 0.30 * settling_gate + 0.15 * micro_gate
        legacy_precision = _axis_stars(axes, "spatial_precision")
        precision = (
            anchor_hint * (0.55 + 0.55 * precision_index)
            if legacy_precision is None
            else legacy_precision * (0.90 + 0.20 * precision_index)
        )
        _set_axis(
            axes,
            "spatial_precision",
            precision,
            "TOLERANCE_SETTLING_MICRO_PRECISION_V091",
            {
                "anchor_hint_stars": anchor_hint,
                "tolerance_p90": tolerance,
                "settling_p90": settling,
                "micro_correction_p90": micro,
                "micro_correction_count": c.get("v091_precision_micro_correction_count"),
                "precision_index": precision_index,
            },
        )

    flow = _axis_stars(axes, "flow_aim")
    chain_share = _finite(c.get("v091_flow_chain_share"))
    chain_length = _finite(c.get("v091_flow_chain_length_p90"))
    chain_velocity = _finite(c.get("v091_flow_chain_velocity_p90"))
    smoothness = _finite(c.get("v091_flow_chain_smoothness_mean"))
    if flow is not None and None not in (chain_share, chain_length, chain_velocity, smoothness):
        persistence = _clamp((float(chain_length) - 1.0) / 8.0, 0.0, 1.0)
        velocity_gate = _clamp((float(chain_velocity) - 0.45) / 1.8, 0.0, 1.0)
        morphology = (
            0.35 * _clamp(float(chain_share) / 0.45, 0.0, 1.0)
            + 0.30 * persistence
            + 0.25 * velocity_gate
            + 0.10 * _clamp(float(smoothness), 0.0, 1.0)
        )
        adjusted = flow * (0.90 + 0.15 * morphology)
        _set_axis(
            axes,
            "flow_aim",
            adjusted,
            "FAST_SMOOTH_PERSISTENT_FLOW_V091",
            {
                "chain_share": chain_share,
                "chain_length_p90": chain_length,
                "chain_velocity_p90": chain_velocity,
                "chain_smoothness_mean": smoothness,
                "flow_morphology": morphology,
            },
        )

    finger = _axis_stars(axes, "finger_control")
    raw = _axis_stars(axes, "raw_speed")
    pair_count = _finite(c.get("v091_finger_fast_pair_count"))
    change_share = _finite(c.get("v091_finger_nontrivial_change_share"))
    novelty = _finite(c.get("v091_finger_novelty_p90"))
    if finger is not None and raw is not None and None not in (pair_count, change_share, novelty):
        evidence_gate = _clamp((float(pair_count) - 12.0) / 48.0, 0.0, 1.0)
        pattern_gate = (
            evidence_gate
            * _clamp(float(change_share) / 0.35, 0.0, 1.0)
            * _clamp(float(novelty) / 0.28, 0.0, 1.0)
        )
        # V0.9 double-counted a speed floor, a pattern extension, and an
        # additive coordination bonus.  Retain its useful ordering, remove one
        # quarter of the stacked magnitude, and cap it against Raw Speed unless
        # there is actual non-trivial local pattern evidence.
        deduplicated = 0.75 * finger + 0.45 * pattern_gate
        adjusted = min(deduplicated, raw + 0.75 + 0.45 * pattern_gate)
        _set_axis(
            axes,
            "finger_control",
            adjusted,
            "FAST_NONTRIVIAL_PATTERN_FINGER_V091",
            {
                "raw_speed_stars": raw,
                "fast_pair_count": pair_count,
                "nontrivial_change_share": change_share,
                "novelty_p90": novelty,
                "pattern_gate": pattern_gate,
                "deduplication_factor": 0.75,
                "raw_speed_relative_cap": raw + 0.75 + 0.45 * pattern_gate,
            },
        )


def _reading(axes: dict[str, Any], c: dict[str, Any], mods: set[str]) -> None:
    base = _axis_stars(axes, "reading")
    if base is None:
        return
    physical = [
        value
        for axis in ("jump_aim", "flow_aim", "aim_control", "spatial_precision", "raw_speed")
        if (value := _axis_stars(axes, axis)) is not None
    ]
    if len(physical) < 3:
        return
    physical.sort(reverse=True)
    environment = sum(physical[:3]) / 3.0
    preempt = _finite(c.get("reading_preempt_median_ms"))
    overlap = _finite(c.get("v091_visible_overlap_load_p90"))
    cluster = _finite(c.get("v091_visible_cluster_load_p90"))
    overlap_share = _finite(c.get("v091_visible_overlap_pair_share"))
    stack_share = _finite(c.get("v091_visible_stack_object_share"))
    if None in (preempt, overlap, cluster, overlap_share, stack_share):
        return
    overlap_gate = _clamp(float(overlap) / 1.8, 0.0, 1.0)
    cluster_gate = _clamp((float(cluster) - 1.0) / 5.0, 0.0, 1.0)
    stack_gate = _clamp(float(stack_share) / 0.18, 0.0, 1.0)
    spatial_load = 0.55 * overlap_gate + 0.25 * cluster_gate + 0.20 * stack_gate
    required_preempt = _clamp(720.0 - 48.0 * (environment - 5.0), 320.0, 900.0)
    relative_low_ar = _clamp((float(preempt) / required_preempt - 1.0) / 0.65, 0.0, 1.0)
    floor = environment * (0.55 + 0.20 * spatial_load)
    reading = max(base, floor) + 1.10 * relative_low_ar * (0.35 + 0.65 * spatial_load)
    hd_synergy = 0.0
    if "HD" in mods:
        hd_synergy = 1.65 * (0.25 + 0.75 * spatial_load) * (
            0.35 + 0.65 * relative_low_ar
        )
        reading += hd_synergy
    _set_axis(
        axes,
        "reading",
        reading,
        "VISIBLE_OVERLAP_RELATIVE_AR_READING_V091",
        {
            "physical_environment_stars": environment,
            "actual_preempt_ms": preempt,
            "required_preempt_ms": required_preempt,
            "visible_overlap_load_p90": overlap,
            "visible_cluster_load_p90": cluster,
            "visible_overlap_pair_share": overlap_share,
            "visible_stack_object_share": stack_share,
            "spatial_visibility_load": spatial_load,
            "relative_low_ar_gate": relative_low_ar,
            "hd_overlap_low_ar_synergy_stars": hd_synergy,
        },
    )


def _estimate_anchor(axes: dict[str, Any]) -> float | None:
    values = sorted(
        (
            value
            for axis in ("jump_aim", "flow_aim", "aim_control", "spatial_precision", "raw_speed")
            if (value := _axis_stars(axes, axis)) is not None
        ),
        reverse=True,
    )
    if len(values) < 3:
        return None
    # The third-highest current physical axis is robust against one unbounded
    # calibration-tail outlier and tracks the map's general demand envelope.
    return _clamp(values[2], 0.5, 15.0)


def _resolve_anchor(
    axes: dict[str, Any], components: dict[str, Any], mod_context: dict[str, Any]
) -> tuple[float | None, str]:
    nm = _finite(components.get("v091_nm_star_anchor"))
    if nm is not None and nm > 0.0:
        mods = set(mod_context.get("effective_mods", []))
        rate = _finite(mod_context.get("clock_rate")) or 1.0
        if rate > 1.0:
            # A fixed low exponent badly underestimates DT jump maps.  The
            # anchor remains conservative on non-jump maps and approaches the
            # observed DT total-SR scaling only when raw movement warrants it.
            rate_exponent = 0.75 + 0.55 * _jump_movement_severity(components)
        else:
            rate_exponent = 0.55
        factor = rate**rate_exponent
        if "HR" in mods:
            factor *= 1.06
        if "EZ" in mods:
            factor *= 0.58
        # HD affects visibility, not the physical total-SR anchor.
        return max(0.1, nm * factor), "LOCAL_OSU_DB_NM_PLUS_STRUCTURE_AWARE_MOD_TRANSFORM"
    return _estimate_anchor(axes), "ROBUST_THIRD_HIGHEST_V091_PHYSICAL_AXIS"


def _soft_anchor(raw: float, anchor: float) -> float:
    raw = max(0.0, float(raw))
    anchor = max(0.1, float(anchor))
    delta = raw - anchor
    if delta <= 0.0:
        # The anchor is a tail limiter, not a gravity well.  Valid low axes
        # must remain low and must not be pulled toward the map's total SR.
        return raw
    headroom = min(2.5, 1.25 + 0.08 * anchor)
    return anchor + headroom * math.tanh(delta / max(headroom, 0.1))


def _apply_anchor(axes: dict[str, Any], anchor: float, source: str) -> None:
    for axis in _STAR_AXES:
        item = axes.get(axis)
        raw = _axis_stars(axes, axis)
        if not isinstance(item, dict) or raw is None:
            continue
        adjusted = _soft_anchor(raw, anchor)
        item["demand_star_equivalent"] = adjusted
        item["score"] = adjusted / 10.0
        item["percentile_rank"] = None
        item["scale_method"] = "SOFT_TOTAL_SR_ANCHOR_SATURATING_V091"
        item.setdefault("evidence", []).append(
            {
                "component": "v091_soft_total_sr_anchor",
                "pre_anchor_stars": raw,
                "anchor_stars": anchor,
                "anchor_source": source,
                "adjusted_stars": adjusted,
                "positive_headroom_stars": min(2.5, 1.25 + 0.08 * anchor),
            }
        )


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
    # V0.9 contains several human-validated orderings (especially Flow and
    # relative-AR Reading) that the frozen V0.6 atomics understate badly.  Use
    # that signal body, then replace/deduplicate the exposed mechanisms before
    # applying one shared tail limiter.  V0.9 itself remains replayable.
    output = v09.analyze_components(
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
    output["diagnostics"]["v091_base_map_demand_version"] = v09.MAP_DEMAND_VERSION
    output["diagnostics"]["v091_mechanism_spec"] = MECHANISM_SPEC
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
        C.scan_finite(output, "model_v091.output")
        return output

    axes = output["axes"]
    _jump_precision_flow_finger(axes, components, mod_context)
    _reading(axes, components, set(mod_context.get("effective_mods", [])))
    anchor, anchor_source = _resolve_anchor(axes, components, mod_context)
    if anchor is not None:
        _apply_anchor(axes, anchor, anchor_source)
    # Stamina and Endurance are bounded human scales, so calculate them after
    # star-axis anchoring and never pass them through the star scale.
    v08._bounded_stamina(axes, components)
    axes["endurance"] = v08._endurance_axis(axes, components)
    output["diagnostics"]["v091_star_anchor"] = {
        "stars": anchor,
        "source": anchor_source,
    }
    output["summaries"] = derive_summaries(axes)
    output["archetype"] = classify_axes(axes)
    C.scan_finite(output, "model_v091.output")
    return output
