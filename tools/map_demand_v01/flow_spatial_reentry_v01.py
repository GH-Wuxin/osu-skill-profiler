"""Circle-only spatial reentry evidence, independent of a difficulty scale.

A candidate is one observed bridge movement, with alternative local phrase
contexts.  Candidate existence is NOT a Flow classification.  Geometry,
phrase evidence, rhythmic continuity, and boundary changes remain separate;
no product of these quantities, star score, map label, or frozen Flow support
is used here.  Multiple contexts of the same bridge are not separate events.

The minimum two movements per side supplies one internally observed turn.
This permits short phrases without pretending that one arbitrary jump proves
a Flow phrase.  Sliders, zero displacement, missing geometry, and structural
breaks cannot supply this specific circle-tapping mechanism's context.
"""
from __future__ import annotations

from collections import Counter
import math
import statistics
from typing import Any, Mapping

from . import flow_geometry_v02 as geometry
from . import paired_transition_geometry_v01 as paired


SCHEMA_VERSION = "flow_spatial_reentry_v0.2.0"
MIN_SIDE_MOVEMENTS = 2
MAX_SIDE_MOVEMENTS = 4
NUMERIC_EPSILON = 1e-12


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _ratio(numerator: float, denominator: float) -> float | None:
    """An unrepresentable diagnostic ratio is missing, never infinity."""
    result = numerator / denominator
    return result if math.isfinite(result) else None


def _rotation(first: list[float], second: list[float]) -> list[float]:
    return [
        max(-1.0, min(1.0, first[0] * second[0] + first[1] * second[1])),
        max(-1.0, min(1.0, first[0] * second[1] - first[1] * second[0])),
    ]


def _angle(rotation: list[float]) -> float:
    return math.atan2(abs(rotation[1]), rotation[0])


def _rotation_change(first: list[float], second: list[float]) -> float:
    result = min(1.0, math.hypot(first[0] - second[0], first[1] - second[1]) / 2.0)
    return 0.0 if result < NUMERIC_EPSILON else result


def _positive_excess(value: float, reference: float) -> float:
    result = max(0.0, value - reference)
    return 0.0 if result < NUMERIC_EPSILON else result


def _atom(transition: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if transition.get("from_kind") != "circle" or transition.get("to_kind") != "circle":
        return None, "NON_CIRCLE_TRANSITION"
    if transition.get("section_start"):
        return None, "STRUCTURAL_SECTION_START"
    if transition.get("to_source_row_index") != transition.get("from_source_row_index", -2) + 1:
        return None, "NONCONSECUTIVE_SOURCE_OBJECTS"
    if not transition.get("jump_phase_vector_available"):
        return None, str(transition.get("direction_missing_reason") or "MISSING_JUMP_VECTOR")
    channel = transition.get("channels", {}).get(paired.FULL_PATH_FULL_TIME, {})
    distance = _finite(channel.get("distance_px"))
    interval = _finite(channel.get("time_ms"))
    start = _finite(transition.get("start_time_ms"))
    end = _finite(transition.get("end_time_ms"))
    if not channel.get("available") or distance is None or interval is None or distance <= 0.0 or interval <= 0.0:
        return None, "MISSING_OR_NONPOSITIVE_CIRCLE_PHASE"
    if start is None or end is None or end <= start:
        return None, "MISSING_OR_NONPOSITIVE_CIRCLE_WALL_TIME"
    if abs((end - start) - interval) > max(1e-6, interval * 1e-6):
        return None, "CIRCLE_PHASE_WALL_TIME_MISMATCH"
    raw_unit = transition.get("jump_phase_unit_vector")
    if not isinstance(raw_unit, (list, tuple)) or len(raw_unit) != 2:
        return None, "MISSING_JUMP_VECTOR"
    unit = [_finite(component) for component in raw_unit]
    if any(component is None for component in unit):
        return None, "NONFINITE_JUMP_VECTOR"
    norm = math.hypot(*unit)
    if abs(norm - 1.0) > 1e-6:
        return None, "NONUNIT_JUMP_VECTOR"
    return {
        "transition_index": transition["transition_index"],
        "from_source_row_index": transition["from_source_row_index"],
        "to_source_row_index": transition["to_source_row_index"],
        "block": transition["block"],
        "segment": transition["segment"],
        "start_ms": start,
        "end_ms": end,
        "distance_px": distance,
        "interval_ms": interval,
        "radius_px": _finite(transition.get("radius_px")),
        "unit_vector": [component / norm for component in unit],
        "direction_reference_transition_index": transition.get("direction_reference_transition_index"),
    }, None


def _adjacent(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return bool(
        first["block"] == second["block"]
        and first["segment"] == second["segment"]
        and second["from_source_row_index"] == first["to_source_row_index"]
        and second["transition_index"] == first["transition_index"] + 1
        and second["direction_reference_transition_index"] == first["transition_index"]
        and second["start_ms"] == first["end_ms"]
    )


def _side(motions: list[dict[str, Any]]) -> dict[str, Any]:
    units = [motion["unit_vector"] for motion in motions]
    rotations = [_rotation(first, second) for first, second in zip(units, units[1:])]
    turns = [_angle(rotation) for rotation in rotations]
    mean_vector = [statistics.fmean(unit[axis] for unit in units) for axis in (0, 1)]
    coherence = min(1.0, math.hypot(*mean_vector))
    mean_unit = [component / coherence for component in mean_vector] if coherence > NUMERIC_EPSILON else None
    forward = statistics.fmean(rotation[0] for rotation in rotations)
    return {
        "movement_count": len(motions),
        "transition_indices": [motion["transition_index"] for motion in motions],
        "source_index_first": motions[0]["from_source_row_index"],
        "source_index_last": motions[-1]["to_source_row_index"],
        "start_ms": motions[0]["start_ms"],
        "end_ms": motions[-1]["end_ms"],
        "median_step_px": statistics.median(motion["distance_px"] for motion in motions),
        "median_interval_ms": statistics.median(motion["interval_ms"] for motion in motions),
        "mean_unit_vector": mean_unit,
        "direction_coherence": coherence,
        "internal_rotations": rotations,
        "internal_turns_rad": turns,
        "mean_forward_dot": forward,
        "mean_forward_alignment": 0.0 if forward < NUMERIC_EPSILON else max(0.0, forward),
        "soft_alignment": 0.0 if forward < NUMERIC_EPSILON else max(0.0, forward),
        "internal_rotation_adjustment_mean": statistics.fmean(
            _rotation_change(first, second) for first, second in zip(rotations, rotations[1:])
        ) if len(rotations) > 1 else None,
    }


def _context(left: list[dict[str, Any]], bridge: dict[str, Any], right: list[dict[str, Any]]) -> dict[str, Any]:
    chain = [*left, bridge, *right]
    left_evidence, right_evidence = _side(left), _side(right)
    intervals = [motion["interval_ms"] for motion in chain]
    log_intervals = [math.log(interval) for interval in intervals]
    rhythm_change = math.sqrt(statistics.fmean(
        (second - first) ** 2 for first, second in zip(log_intervals, log_intervals[1:])
    ))
    side_median_interval = statistics.median([motion["interval_ms"] for motion in [*left, *right]])
    bridge_log_ratio = math.log(bridge["interval_ms"]) - math.log(side_median_interval)
    # Relative timing is kept apart from actual deadlines. Globally slowing
    # every circle preserves rhythm evidence; a scorer uses the stored times.
    timing = {
        "intervals_ms": intervals,
        "median_interval_ms": statistics.median(intervals),
        "adjacent_log_ratio_rms": rhythm_change,
        "continuity_evidence": math.exp(-(rhythm_change ** 2)),
        "bridge_over_side_median_interval": _ratio(bridge["interval_ms"], side_median_interval),
        "bridge_log_interval_ratio": bridge_log_ratio,
        "bridge_timing_match_evidence": math.exp(-(bridge_log_ratio ** 2)),
        "max_interval_over_median": _ratio(max(intervals), statistics.median(intervals)),
        "source_time_quantization_tolerance_used": False,
    }

    # Reconstruct relative positions from the already transformed, validated
    # circle vectors. Normalization avoids overflowing cumulative coordinates.
    coordinate_scale = max(motion["distance_px"] for motion in chain)
    points = [[0.0, 0.0]]
    for motion in chain:
        relative_distance = motion["distance_px"] / coordinate_scale
        points.append([points[-1][axis] + relative_distance * motion["unit_vector"][axis] for axis in (0, 1)])
    left_points, right_points = points[:len(left) + 1], points[len(left) + 1:]
    minimum_between = min(math.dist(first, second) for first in left_points for second in right_points) * coordinate_scale
    typical_step = max(left_evidence["median_step_px"], right_evidence["median_step_px"])
    bridge_ratio = _ratio(bridge["distance_px"], typical_step)
    gap_ratio = _ratio(minimum_between, typical_step)
    # The bounded field stays representable even for extreme spacing ratios.
    # It is zero at/below ordinary within-phrase spacing, continuously rising
    # above it. The uncapped physical distances remain available separately.
    gap_excess = max(0.0, (minimum_between - typical_step) / max(minimum_between, typical_step))
    # A later part of a phrase can revisit an earlier position. That overlap
    # does not shorten the actual movement at the temporal cut. Preserve the
    # global chunk distance as a diagnostic, not a veto on the boundary.
    bridge_distance = bridge["distance_px"]
    boundary_excess = max(0.0, (bridge_distance - typical_step) / max(bridge_distance, typical_step))
    spatial = {
        "reference_step_px": typical_step,
        "bridge_distance_px": bridge["distance_px"],
        "bridge_over_larger_side_median": bridge_ratio,
        "minimum_between_chunks_px": minimum_between,
        "chunk_gap_over_larger_side_median": gap_ratio,
        "gap_excess_ratio": 0.0 if gap_excess < NUMERIC_EPSILON else gap_excess,
        "boundary_step_excess_ratio": 0.0 if boundary_excess < NUMERIC_EPSILON else boundary_excess,
        "coordinate_source": "RELATIVE_SUM_OF_MODDED_CIRCLE_PHASE_VECTORS",
    }
    enter = _rotation(left[-1]["unit_vector"], bridge["unit_vector"])
    leave = _rotation(bridge["unit_vector"], right[0]["unit_vector"])
    boundary_turns = [_angle(enter), _angle(leave)]
    internal_reference = [statistics.fmean(left_evidence["internal_turns_rad"]), statistics.fmean(right_evidence["internal_turns_rad"])]
    direction = {
        "boundary_rotations": [enter, leave],
        "boundary_turns_rad": boundary_turns,
        "boundary_turn_excess_rad": [_positive_excess(turn, baseline) for turn, baseline in zip(boundary_turns, internal_reference)],
        "rotation_change_at_boundary": [
            _rotation_change(left_evidence["internal_rotations"][-1], enter),
            _rotation_change(leave, right_evidence["internal_rotations"][0]),
        ],
        "bridge_rotation_change": _rotation_change(enter, leave),
        "average_direction_change_rad": _angle(_rotation(left_evidence["mean_unit_vector"], right_evidence["mean_unit_vector"]))
        if left_evidence["mean_unit_vector"] is not None and right_evidence["mean_unit_vector"] is not None else None,
        "boundary_reversal_continuity": [max(0.0, min(1.0, (rotation[0] + 1.0) / 2.0)) for rotation in (enter, leave)],
    }
    return {
        "context_id": f"L{len(left)}R{len(right)}",
        "source_index_first": chain[0]["from_source_row_index"],
        "source_index_last": chain[-1]["to_source_row_index"],
        "transition_index_first": chain[0]["transition_index"],
        "transition_index_last": chain[-1]["transition_index"],
        "start_ms": chain[0]["start_ms"],
        "end_ms": chain[-1]["end_ms"],
        "circle_count": len(chain) + 1,
        "slider_count": 0,
        "left": left_evidence,
        "right": right_evidence,
        "timing": timing,
        "spatial": spatial,
        "direction": direction,
    }


def extract_spatial_reentry_evidence(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return bridge-unique raw candidates from a Flow geometry v0.2 bundle.

    Every context is independently source-complete and circle-only. Consumers
    may select a context per bridge but must not add its alternative scales as
    separate events. Neighboring bridges can share phrase context; that does
    not make the same bridge occur twice. ``events`` is deliberately a raw
    candidate inventory, not a count of classified spatial separations.
    """
    if bundle.get("schema_version") != geometry.SCHEMA_VERSION:
        raise ValueError(f"Spatial reentry requires {geometry.SCHEMA_VERSION}, got {bundle.get('schema_version')!r}")
    reasons: Counter[str] = Counter()
    motions: list[dict[str, Any]] = []
    runs: list[list[dict[str, Any]]] = []
    active: list[dict[str, Any]] = []
    for transition in bundle["transitions"]:
        atom, reason = _atom(transition)
        if atom is None:
            reasons[str(reason)] += 1
            if active:
                runs.append(active)
                active = []
            continue
        if active and not _adjacent(active[-1], atom):
            reasons["NONCONTIGUOUS_DIRECTION_OR_SOURCE"] += 1
            runs.append(active)
            active = []
        active.append(atom)
        motions.append(atom)
    if active:
        runs.append(active)

    events = []
    for circle_run_id, run in enumerate(runs):
        for motion in run:
            motion["circle_run_id"] = circle_run_id
        for index in range(MIN_SIDE_MOVEMENTS, len(run) - MIN_SIDE_MOVEMENTS):
            bridge = run[index]
            contexts = []
            for left_count in range(MIN_SIDE_MOVEMENTS, min(MAX_SIDE_MOVEMENTS, index) + 1):
                for right_count in range(MIN_SIDE_MOVEMENTS, min(MAX_SIDE_MOVEMENTS, len(run) - index - 1) + 1):
                    contexts.append(_context(run[index - left_count:index], bridge, run[index + 1:index + right_count + 1]))
            events.append({
                "event_id": f"{bridge['block']}:{bridge['from_source_row_index']}:{bridge['to_source_row_index']}",
                "bridge_transition_index": bridge["transition_index"],
                "circle_run_id": circle_run_id,
                "bridge": dict(bridge),
                "contexts": contexts,
                "classified_as_spatial_reentry": None,
            })
    return {
        "schema_version": SCHEMA_VERSION,
        "source_geometry_schema_version": bundle["schema_version"],
        "motions": motions,
        "events": events,
        "diagnostics": {
            "source_transition_count": len(bundle["transitions"]),
            "eligible_circle_movement_count": len(motions),
            "circle_run_count": len(runs),
            "bridge_candidate_count": len(events),
            "context_count": sum(len(event["contexts"]) for event in events),
            "excluded_transition_reasons": dict(sorted(reasons.items())),
            "candidates_are_classified_events": False,
            "contexts_are_independent_events": False,
            "slider_bridges_excluded": True,
            "frozen_flow_support_used": False,
            "score_computed": False,
            "reading_or_tapping_errors_observed": False,
            "stacking_applied": bool(bundle.get("diagnostics", {}).get("stacking_applied", False)),
        },
        "parameters": {
            "minimum_side_movements": MIN_SIDE_MOVEMENTS,
            "maximum_side_movements": MAX_SIDE_MOVEMENTS,
            "minimum_is_observed_internal_turn_requirement": True,
            "fixed_rhythm_tolerance_ms": None,
            "soft_timing_policy": "EXP_NEGATIVE_SQUARED_LOG_INTERVAL_CHANGE",
            "gap_excess_policy": "POSITIVE_GAP_MINUS_TYPICAL_STEP_DIVIDED_BY_LARGER",
        },
    }


__all__ = ["SCHEMA_VERSION", "extract_spatial_reentry_evidence"]
