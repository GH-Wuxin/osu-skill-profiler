"""Opt-in Flow geometry with explicit jump-phase directions.

This module does not alter Local Signal 0.4 or the frozen paired geometry.
Distances retain their original phase/time pairing.  Direction is measured
from the previous lazy end to the current head, never from the historical
``slider_aware_angle``.  It is a jump-phase proxy, not an inferred slider
tangent or a reconstructed player trajectory.  Stacking remains unmodelled.

Zero movement has known geometry but no direction.  A following movement may
refer to the nearest preceding nonzero jump within the same block; the dwell
count and elapsed time remain explicit for a consumer's continuity policy.
Missing geometry and sliders with travel but no exit jump break this history.
"""

from __future__ import annotations

from collections import Counter
import math
from typing import Any, Iterable, Mapping

from . import paired_transition_geometry_v01 as paired


SCHEMA_VERSION = "flow_geometry_v0.2.1"
LOCAL_SIGNAL_VERSION = paired.LOCAL_SIGNAL_VERSION
POSITION_EPSILON_PX = 1e-7
ANGLE_EPSILON = 1e-12
DIRECTION_SOURCE = "PREVIOUS_LAZY_END_TO_CURRENT_HEAD_JUMP_PHASE"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _position(row: Mapping[str, Any], *, lazy: bool = False) -> tuple[float, float] | None:
    keys = (
        ("ls.lazy_end_position_x_px", "ls.lazy_end_position_y_px")
        if lazy else ("v091.start_x_px", "v091.start_y_px")
    )
    x, y = (_finite(row.get(key)) for key in keys)
    return None if x is None or y is None else (x, y)


def _vector(start: tuple[float, float] | None, end: tuple[float, float] | None) -> dict[str, Any]:
    if start is None or end is None:
        return {"available": False, "missing_reason": "MISSING_PHASE_POSITION", "length_px": None, "unit_vector": None}
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if not math.isfinite(length):
        return {"available": False, "missing_reason": "NONFINITE_PHASE_VECTOR", "length_px": None, "unit_vector": None}
    if length <= POSITION_EPSILON_PX:
        return {"available": False, "missing_reason": "ZERO_PHASE_DISPLACEMENT", "length_px": length, "unit_vector": None}
    return {"available": True, "missing_reason": None, "length_px": length, "unit_vector": [dx / length, dy / length]}


def _turn(previous: list[float], current: list[float]) -> tuple[float, float | None]:
    """Return unsigned turn and its oriented value when orientation exists.

    An exact reversal has a known pi magnitude, but no geometrically defined
    left/right orientation.  Reporting its signed value as missing avoids
    signed-zero-dependent curvature-change evidence under reflection.
    """
    dot = max(-1.0, min(1.0, previous[0] * current[0] + previous[1] * current[1]))
    cross = previous[0] * current[1] - previous[1] * current[0]
    if abs(cross) <= ANGLE_EPSILON:
        return (0.0, 0.0) if dot >= 0 else (math.pi, None)
    signed = math.atan2(cross, dot)
    return abs(signed), signed


def build_flow_geometry(
    rows: Iterable[dict[str, Any]],
    resolved_preempt_ms: float | None = None,
) -> dict[str, Any]:
    """Return paired transitions plus invariant jump-phase direction fields.

    ``execution_direction_available`` means that a turn relative to a known
    preceding nonzero jump is available.  The first jump can instead expose
    ``jump_phase_vector_available=True`` with no turn.  All scalar direction
    magnitudes and change measures are invariant to rigid transforms; signed
    turns reverse sign on reflection.  Exact half-turns have no signed value.

    ``turn_change_rad`` is the absolute difference of consecutive signed
    jump-phase turns, not another absolute bend penalty.  Constant-curvature
    arcs therefore have near-zero change while alternating bends do not.

    ``jump_phase_turn_adjustment_ratio`` instead compares consecutive unit
    rotations q=(dot, cross): ||q_current-q_previous||/2 in [0, 1].  This
    chord measure stays continuous through the signed-angle branch cut and
    exact reversals.  A half-turn has rotation (-1, 0) even though its signed
    angle remains ambiguous under the unchanged historical field semantics.
    No score, gate, target star value, or aggregation rule is applied here.
    """
    source = [dict(row) for row in rows]
    version = getattr(rows, "local_signal_version", None)
    if version is not None and version != LOCAL_SIGNAL_VERSION:
        raise ValueError(f"Flow geometry requires Local Signal {LOCAL_SIGNAL_VERSION}, got {version!r}")
    bundle = paired.build_transition_bundle(source, resolved_preempt_ms)
    transitions: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    previous_motion: dict[str, Any] | None = None
    previous_signed_turn: float | None = None
    previous_rotation: tuple[float, float] | None = None
    previous_curvature: float | None = None
    previous_head_unit: list[float] | None = None
    last_block: Any = None
    zero_gap = 0

    for original in bundle["transitions"]:
        item = dict(original)
        if item["block"] != last_block or item.get("section_start"):
            previous_motion = None
            previous_signed_turn = None
            previous_rotation = None
            previous_curvature = None
            previous_head_unit = None
            zero_gap = 0
        last_block = item["block"]
        prior_row = source[item["from_source_row_index"]]
        row = source[item["to_source_row_index"]]
        prior_head, head = _position(prior_row), _position(row)
        is_slider = item["from_kind"] == "slider"
        origin = _position(prior_row, lazy=True) if is_slider else prior_head
        jump = _vector(origin, head)
        head_vector = _vector(prior_head, head)
        full = item["channels"][paired.FULL_PATH_FULL_TIME]
        lazy = item["channels"][paired.LAZY_FULL]
        travel = item["from_travel_px"]
        travel_time = _finite(prior_row.get("ls.lazy_travel_time_ms")) if is_slider else 0.0
        slider_tangent_unknown = bool(is_slider and (travel is None or travel > POSITION_EPSILON_PX))
        scalar_zero = bool(full["available"] and full["distance_px"] <= POSITION_EPSILON_PX)
        discrepancy = (
            abs(jump["length_px"] - lazy["distance_px"])
            if jump["length_px"] is not None and lazy["available"] else None
        )
        consistent = bool(
            discrepancy is not None
            and discrepancy <= max(1e-6, 1e-6 * float(lazy["distance_px"]))
        )
        reason = None
        if not full["available"]:
            reason = "UNAVAILABLE_FULL_PATH_PHASE"
        elif not lazy["available"]:
            reason = "UNAVAILABLE_LAZY_JUMP_PHASE"
        elif jump["length_px"] is None:
            reason = jump["missing_reason"]
        elif not consistent:
            reason = "JUMP_VECTOR_DISTANCE_MISMATCH"
        elif not jump["available"]:
            reason = "ZERO_FULL_PATH_DISPLACEMENT" if scalar_zero else "SLIDER_TRAVEL_WITHOUT_EXIT_DIRECTION"

        vector_available = reason is None
        turn = signed = change = curvature = curvature_change = span = None
        rotation: tuple[float, float] | None = None
        adjustment_ratio = None
        reference_index = None
        if vector_available and previous_motion is not None:
            turn, signed = _turn(previous_motion["unit"], jump["unit_vector"])
            previous_unit, current_unit = previous_motion["unit"], jump["unit_vector"]
            rotation = (
                previous_unit[0] * current_unit[0] + previous_unit[1] * current_unit[1],
                previous_unit[0] * current_unit[1] - previous_unit[1] * current_unit[0],
            )
            if previous_rotation is not None:
                # Unit-vector arithmetic can exceed the exact [0, 1] bound
                # by roundoff; the clamp is numerical, not an evidence gate.
                adjustment_ratio = min(1.0, max(0.0, math.hypot(
                    rotation[0] - previous_rotation[0],
                    rotation[1] - previous_rotation[1],
                ) / 2.0))
            span = item["end_time_ms"] - previous_motion["end_time_ms"]
            reference_index = previous_motion["transition_index"]
            if signed is not None:
                average_distance = (previous_motion["length_px"] + jump["length_px"]) / 2.0
                curvature = signed / average_distance
                if previous_signed_turn is not None:
                    change = abs(signed - previous_signed_turn)
                if previous_curvature is not None:
                    curvature_change = abs(curvature - previous_curvature)
        elif vector_available:
            reason = "NO_PREVIOUS_NONZERO_JUMP_DIRECTION"

        head_turn = None
        if head_vector["available"]:
            if previous_head_unit is not None:
                head_turn, _ = _turn(previous_head_unit, head_vector["unit_vector"])
            previous_head_unit = head_vector["unit_vector"]
        else:
            previous_head_unit = None

        item.update(
            execution_direction_available=turn is not None,
            direction_missing_reason=reason,
            direction_source=DIRECTION_SOURCE,
            jump_phase_vector_available=vector_available,
            jump_phase_unit_vector=jump["unit_vector"] if vector_available else None,
            jump_phase_distance_px=jump["length_px"],
            jump_phase_turn_angle_rad=turn,
            jump_phase_signed_turn_rad=signed,
            jump_phase_turn_change_rad=change,
            jump_phase_turn_adjustment_ratio=adjustment_ratio,
            jump_phase_curvature_rad_per_px=curvature,
            jump_phase_curvature_change_rad_per_px=curvature_change,
            turn_angle_rad=turn,
            signed_turn_rad=signed,
            turn_change_rad=change,
            signed_turn_ambiguous=turn is not None and signed is None,
            direction_span_ms=span,
            direction_reference_transition_index=reference_index,
            zero_gap_count=zero_gap,
            zero_displacement=scalar_zero,
            zero_jump_displacement=jump["length_px"] is not None and jump["length_px"] <= POSITION_EPSILON_PX,
            slider_tangent_unavailable=slider_tangent_unknown,
            head_phase_unit_vector=head_vector["unit_vector"],
            head_phase_turn_angle_rad=head_turn,
            phase_diagnostics={
                "jump_vector_distance_discrepancy_px": discrepancy,
                "jump_vector_distance_consistent": consistent,
                "previous_lazy_travel_px": travel,
                "previous_lazy_travel_time_ms": travel_time,
                "full_time_ms": full["time_ms"],
                "wall_time_ms": item["wall_time_ms"],
                "remaining_after_lazy_travel_ms": (
                    full["time_ms"] - travel_time
                    if full["available"] and travel_time is not None else None
                ),
                "minimum_phase_uses_its_own_time": True,
                "slider_internal_tangent_reconstructed": False,
            },
        )
        transitions.append(item)
        if reason is not None:
            reasons[reason] += 1

        if item.get("section_start"):
            # A long-gap bridge is still a paired distance/time observation,
            # but must not lend a direction to the fresh movement sequence.
            previous_motion = None
            previous_signed_turn = None
            previous_rotation = None
            previous_curvature = None
            previous_head_unit = None
            zero_gap = 0
        elif vector_available:
            previous_motion = {
                "unit": jump["unit_vector"],
                "length_px": jump["length_px"],
                "end_time_ms": item["end_time_ms"],
                "transition_index": item["transition_index"],
            }
            previous_signed_turn = signed
            previous_rotation = rotation
            previous_curvature = curvature
            zero_gap = 0
        elif scalar_zero and reason == "ZERO_FULL_PATH_DISPLACEMENT":
            zero_gap += 1
        else:
            previous_motion = None
            previous_signed_turn = None
            previous_rotation = None
            previous_curvature = None
            zero_gap = 0

    result = dict(bundle)
    result.update(
        schema_version=SCHEMA_VERSION,
        paired_geometry_schema_version=bundle["schema_version"],
        source_local_signal_version=version or LOCAL_SIGNAL_VERSION,
        transitions=transitions,
        diagnostics={
            "direction_source": DIRECTION_SOURCE,
            "direction_available_count": sum(t["execution_direction_available"] for t in transitions),
            "known_zero_displacement_count": sum(t["zero_displacement"] for t in transitions),
            "slider_internal_tangent_unavailable_count": sum(t["slider_tangent_unavailable"] for t in transitions),
            "missing_direction_reasons": dict(sorted(reasons.items())),
            "historical_slider_aware_angle_used": False,
            "stacking_applied": False,
            "zero_gap_policy": "KNOWN_ZERO_ONLY_BRIDGE_WITH_EXPLICIT_COUNT_AND_ELAPSED_TIME",
        },
    )
    return result


__all__ = ["SCHEMA_VERSION", "LOCAL_SIGNAL_VERSION", "DIRECTION_SOURCE", "build_flow_geometry"]
