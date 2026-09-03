"""Versioned paired transition geometry for Local Signal 0.4 rows.

The module is intentionally release-agnostic.  It turns the row-oriented
Local Signal contract into explicit, same-phase transition channels without
reading star rating, labels, or any model output.  A numeric zero is valid
geometry; unavailable geometry always carries a missing reason instead.

``objects`` is a compatibility view for the beta.4/beta.5 local-pattern
consumers.  New consumers should use ``transitions`` and ``channels``.  The
compatibility ``distance``/``free_time`` values are safe numeric placeholders
when the corresponding phase is missing, while ``phase_channels`` preserves
the actual availability distinction.
"""
from __future__ import annotations

from collections import Counter
import math
import statistics
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "paired_transition_geometry_v0.1.0"
LOCAL_SIGNAL_VERSION = "0.4.0"
REFERENCE_RADIUS_PX = (54.4 - 4.48 * 4.0) * 1.00041
LONG_GAP_MS = 1500.0

HEAD_FULL = "head_full"
MINIMUM_MINIMUM = "minimum_minimum"
LAZY_FULL = "lazy_full"
FULL_PATH_FULL_TIME = "full_path_full_time"
CHANNEL_NAMES = (
    HEAD_FULL,
    MINIMUM_MINIMUM,
    LAZY_FULL,
    FULL_PATH_FULL_TIME,
)

PAIRING_POLICIES = {
    HEAD_FULL: "jump_distance_raw_px / adjusted_delta_time_ms",
    MINIMUM_MINIMUM: (
        "minimum_jump_distance_cs_normalised / cs_scale "
        "over minimum_jump_time_ms"
    ),
    LAZY_FULL: (
        "lazy_jump_distance_cs_normalised / cs_scale "
        "over adjusted_delta_time_ms"
    ),
    FULL_PATH_FULL_TIME: (
        "(previous lazy_travel_distance_cs_normalised / previous cs_scale + "
        "current lazy_jump_distance_cs_normalised / current cs_scale) "
        "over adjusted_delta_time_ms"
    ),
}


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


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def _angle_delta(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2.0 * math.pi) - math.pi) / math.pi


def _kind(row: Mapping[str, Any]) -> str:
    return str(row.get("ls.object_type", "circle")).strip().lower() or "circle"


def _channel_unavailable(*reasons: str) -> dict[str, Any]:
    reasons = tuple(dict.fromkeys(reason for reason in reasons if reason))
    return {
        "available": False,
        "distance_px": None,
        "time_ms": None,
        "velocity_px_per_ms": None,
        "missing_reason": reasons[0] if reasons else "UNAVAILABLE",
        "missing_reasons": list(reasons or ("UNAVAILABLE",)),
    }


def _channel(
    distance: Any,
    time: Any,
    *,
    distance_reason: str,
    time_reason: str,
    distance_source: str,
    time_source: str,
) -> dict[str, Any]:
    """Build one phase-coherent pair, preserving a real zero distance."""
    raw_distance = _finite(distance)
    raw_time = _finite(time)
    reasons: list[str] = []
    if raw_distance is None:
        reasons.append(distance_reason)
    elif raw_distance < 0.0:
        reasons.append("NEGATIVE_DISTANCE")
    if raw_time is None:
        reasons.append(time_reason)
    elif raw_time <= 0.0:
        reasons.append("NONPOSITIVE_TIME")
    if reasons:
        result = _channel_unavailable(*reasons)
        result.update(
            distance_source=distance_source,
            time_source=time_source,
        )
        return result
    assert raw_distance is not None and raw_time is not None
    return {
        "available": True,
        "distance_px": raw_distance,
        "time_ms": raw_time,
        "velocity_px_per_ms": raw_distance / raw_time,
        "missing_reason": None,
        "missing_reasons": [],
        "distance_source": distance_source,
        "time_source": time_source,
    }


def _scaled_distance(
    row: Mapping[str, Any],
    signal: str,
) -> tuple[float | None, list[str]]:
    distance = _finite(row.get(signal))
    scale = _finite(row.get("ls.cs_scale"))
    reasons: list[str] = []
    if distance is None:
        reasons.append("MISSING_DISTANCE")
    elif distance < 0.0:
        reasons.append("NEGATIVE_DISTANCE")
    if scale is None:
        reasons.append("MISSING_CS_SCALE")
    elif scale <= 0.0:
        reasons.append("NONPOSITIVE_CS_SCALE")
    if reasons:
        return None, reasons
    assert distance is not None and scale is not None
    return distance / scale, []


def _phase_channels(
    previous_row: Mapping[str, Any],
    current_row: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    full_time = current_row.get("ls.adjusted_delta_time_ms")
    head_full = _channel(
        current_row.get("ls.jump_distance_raw_px"),
        full_time,
        distance_reason="MISSING_HEAD_DISTANCE",
        time_reason="MISSING_FULL_TIME",
        distance_source="ls.jump_distance_raw_px",
        time_source="ls.adjusted_delta_time_ms",
    )

    minimum_distance, minimum_reasons = _scaled_distance(
        current_row,
        "ls.minimum_jump_distance_cs_normalised",
    )
    minimum_minimum = _channel(
        minimum_distance,
        current_row.get("ls.minimum_jump_time_ms"),
        distance_reason=(
            minimum_reasons[0] if minimum_reasons else "MISSING_MINIMUM_DISTANCE"
        ),
        time_reason="MISSING_MINIMUM_TIME",
        distance_source=(
            "ls.minimum_jump_distance_cs_normalised/ls.cs_scale"
        ),
        time_source="ls.minimum_jump_time_ms",
    )
    if not minimum_minimum["available"] and len(minimum_reasons) > 1:
        minimum_minimum["missing_reasons"] = list(
            dict.fromkeys(
                [*minimum_reasons, *minimum_minimum["missing_reasons"]]
            )
        )
        minimum_minimum["missing_reason"] = minimum_minimum[
            "missing_reasons"
        ][0]

    lazy_distance, lazy_reasons = _scaled_distance(
        current_row,
        "ls.lazy_jump_distance_cs_normalised",
    )
    lazy_full = _channel(
        lazy_distance,
        full_time,
        distance_reason=(lazy_reasons[0] if lazy_reasons else "MISSING_LAZY_DISTANCE"),
        time_reason="MISSING_FULL_TIME",
        distance_source="ls.lazy_jump_distance_cs_normalised/ls.cs_scale",
        time_source="ls.adjusted_delta_time_ms",
    )
    if not lazy_full["available"] and len(lazy_reasons) > 1:
        lazy_full["missing_reasons"] = list(
            dict.fromkeys([*lazy_reasons, *lazy_full["missing_reasons"]])
        )
        lazy_full["missing_reason"] = lazy_full["missing_reasons"][0]

    previous_travel: float | None
    previous_travel_reasons: list[str]
    if _kind(previous_row) != "slider":
        # This is a structural zero, not an imputed missing signal.
        previous_travel = 0.0
        previous_travel_reasons = []
        previous_travel_source = "NON_SLIDER_STRUCTURAL_ZERO"
    else:
        previous_travel, previous_travel_reasons = _scaled_distance(
            previous_row,
            "ls.lazy_travel_distance_cs_normalised",
        )
        previous_travel_source = (
            "previous.ls.lazy_travel_distance_cs_normalised/"
            "previous.ls.cs_scale"
        )
        previous_travel_reasons = [
            (
                "MISSING_PREVIOUS_TRAVEL"
                if reason == "MISSING_DISTANCE"
                else f"PREVIOUS_TRAVEL_{reason}"
            )
            for reason in previous_travel_reasons
        ]

    full_path_reasons = [*previous_travel_reasons, *lazy_reasons]
    full_path_distance = (
        previous_travel + lazy_distance
        if previous_travel is not None and lazy_distance is not None
        else None
    )
    full_path = _channel(
        full_path_distance,
        full_time,
        distance_reason=(
            full_path_reasons[0]
            if full_path_reasons
            else "MISSING_FULL_PATH_DISTANCE"
        ),
        time_reason="MISSING_FULL_TIME",
        distance_source=f"{previous_travel_source}+current.lazy_jump",
        time_source="ls.adjusted_delta_time_ms",
    )
    if not full_path["available"] and len(full_path_reasons) > 1:
        full_path["missing_reasons"] = list(
            dict.fromkeys([*full_path_reasons, *full_path["missing_reasons"]])
        )
        full_path["missing_reason"] = full_path["missing_reasons"][0]

    return {
        HEAD_FULL: head_full,
        MINIMUM_MINIMUM: minimum_minimum,
        LAZY_FULL: lazy_full,
        FULL_PATH_FULL_TIME: full_path,
    }


def _empty_phase_channels(reason: str) -> dict[str, dict[str, Any]]:
    return {name: _channel_unavailable(reason) for name in CHANNEL_NAMES}


def predictability(objects_: list[dict[str, Any]]) -> list[float]:
    """Return causal motif novelty, preserving the historical API semantics.

    The old helper was named ``predictability`` although its numeric result is
    novelty (larger means less predictable).  Keeping that meaning avoids a
    silent inversion in Reading.  Bundle objects also expose the less
    ambiguous ``novelty`` and ``motif_predictability`` fields.
    """
    history: list[tuple[float, float, float, str]] = []
    novelties: list[float] = []
    last_segment: Any = None
    for obj in objects_:
        segment = obj.get("segment")
        if segment != last_segment:
            history = []
        last_segment = segment
        dt = _positive(obj.get("dt")) or 25.0
        distance = _nonnegative(obj.get("distance")) or 0.0
        turn = _finite(obj.get("signed_turn")) or 0.0
        kind = str(obj.get("kind", "circle"))
        signature = (
            math.log2(max(dt, 25.0)),
            math.log2(distance + 24.0),
            turn,
            kind,
        )
        history.append(signature)
        errors: list[float] = []
        for lag in range(1, 5):
            span = max(2, lag)
            if len(history) < span + lag + 1:
                continue
            terms = []
            for offset in range(1, span + 1):
                current, prior = history[-offset], history[-offset - lag]
                terms.append(
                    0.28 * abs(current[0] - prior[0])
                    + 0.30 * abs(current[1] - prior[1])
                    + 0.34 * _angle_delta(current[2], prior[2])
                    + 0.08 * (current[3] != prior[3])
                )
            errors.append(statistics.fmean(terms))
        novelty = 0.35 if not errors else -math.expm1(-4.0 * min(errors))
        novelties.append(_clamp(novelty))
        history = history[-12:]
    return novelties


def _coordinate(row: Mapping[str, Any], key: str) -> float | None:
    return _finite(row.get(key))


def _compat_object(
    row: Mapping[str, Any],
    *,
    object_index: int,
    source_row_index: int,
    segment: int,
    block: int,
    dt: float,
    previous_object: Mapping[str, Any] | None,
    phase_channels: dict[str, dict[str, Any]],
    resolved_preempt_ms: float | None,
    structural_status: str,
    simultaneous_group_id: int | None,
) -> dict[str, Any]:
    time = _finite(row.get("ls.start_time_ms"))
    x = _coordinate(row, "v091.start_x_px")
    y = _coordinate(row, "v091.start_y_px")
    radius = _positive(row.get("ls.radius_px"))
    preempt = _positive(row.get("ls.preempt_ms"))
    if preempt is None:
        preempt = _positive(resolved_preempt_ms)

    geometry_missing = []
    if time is None:
        geometry_missing.append("MISSING_START_TIME")
    if x is None or y is None:
        geometry_missing.append("MISSING_ABSOLUTE_POSITION")
    if radius is None:
        geometry_missing.append("MISSING_RADIUS")
    if preempt is None:
        geometry_missing.append("MISSING_PREEMPT")

    # Compatibility consumers require finite coordinates.  These values are
    # deliberately accompanied by geometry_available=False and an isolated
    # structural status when source geometry is unavailable.
    safe_time = time if time is not None else 0.0
    safe_x = x if x is not None else 0.0
    safe_y = y if y is not None else 0.0
    safe_radius = radius if radius is not None else REFERENCE_RADIUS_PX
    safe_preempt = preempt if preempt is not None else 750.0

    head_distance = 0.0
    signed_turn = 0.0
    heading: float | None = None
    if previous_object is not None and not geometry_missing:
        previous_x = _finite(previous_object.get("x"))
        previous_y = _finite(previous_object.get("y"))
        if previous_x is not None and previous_y is not None:
            dx, dy = safe_x - previous_x, safe_y - previous_y
            head_distance = math.hypot(dx, dy)
            heading = (
                math.atan2(dy, dx)
                if head_distance > 0.01
                else _finite(previous_object.get("heading_rad"))
            )
            previous_heading = _finite(previous_object.get("heading_rad"))
            if heading is not None and previous_heading is not None:
                signed_turn = (
                    (heading - previous_heading + math.pi)
                    % (2.0 * math.pi)
                    - math.pi
                )

    preferred = phase_channels[MINIMUM_MINIMUM]
    if not preferred["available"]:
        preferred = phase_channels[HEAD_FULL]
    distance = preferred["distance_px"] if preferred["available"] else 0.0
    free_time = preferred["time_ms"] if preferred["available"] else 0.0
    angle = _finite(row.get("ls.slider_aware_angle_rad"))
    turn = 0.0 if angle is None else _clamp(1.0 - angle / math.pi)

    return {
        "object_index": object_index,
        "source_row_index": source_row_index,
        "time": safe_time,
        "x": safe_x,
        "y": safe_y,
        "radius": safe_radius,
        "preempt": safe_preempt,
        "dt": max(0.0, dt),
        "segment": segment,
        "block": block,
        "distance": float(distance),
        "head_distance": head_distance,
        "free_time": float(free_time),
        "turn": turn,
        "signed_turn": signed_turn,
        "heading_rad": heading,
        "kind": _kind(row),
        "slider_speed": _nonnegative(
            row.get("ls.slider_velocity_px_per_ms")
        )
        or 0.0,
        "end": max(
            safe_time,
            _finite(row.get("ls.end_time_ms")) or safe_time,
        ),
        "phase_channels": phase_channels,
        "geometry_available": not geometry_missing,
        "geometry_missing_reasons": geometry_missing,
        "structural_status": structural_status,
        "simultaneous_group_id": simultaneous_group_id,
    }


def _group_consecutive_equal_times(
    rows: list[Mapping[str, Any]],
) -> list[list[tuple[int, Mapping[str, Any]]]]:
    groups: list[list[tuple[int, Mapping[str, Any]]]] = []
    for index, row in enumerate(rows):
        time = _finite(row.get("ls.start_time_ms"))
        if (
            groups
            and time is not None
            and _finite(groups[-1][0][1].get("ls.start_time_ms")) == time
        ):
            groups[-1].append((index, row))
        else:
            groups.append([(index, row)])
    return groups


def build_transition_bundle(
    rows: Iterable[dict[str, Any]],
    resolved_preempt_ms: float | None = None,
) -> dict[str, Any]:
    """Build an immutable-by-convention Local 0.4 transition bundle.

    Spinner boundaries, the first object after a spinner, long gaps, invalid
    chronology, and equal-time groups never become movement transitions.
    Equal-time objects remain visible in ``objects`` and ``groups`` as an
    isolated structured group, so adversarial maps do not raise or silently
    invent an ordering.
    """
    source_version = getattr(rows, "local_signal_version", None)
    if source_version is not None and source_version != LOCAL_SIGNAL_VERSION:
        raise ValueError(
            f"paired geometry requires Local Signal {LOCAL_SIGNAL_VERSION}, "
            f"got {source_version!r}"
        )
    source_rows: list[Mapping[str, Any]] = [dict(row) for row in rows]
    row_groups = _group_consecutive_equal_times(source_rows)

    objects: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    segment = 0
    block = 0
    previous_row: Mapping[str, Any] | None = None
    previous_object: dict[str, Any] | None = None
    pending_separator: str | None = "START_OF_MAP"
    simultaneous_group_count = 0
    simultaneous_object_count = 0
    spinner_count = 0
    separator_count = 0
    ambiguous_opportunity_count = 0

    for group_index, group in enumerate(row_groups):
        group_rows = [item[1] for item in group]
        group_indices = [item[0] for item in group]
        kinds = [_kind(row) for row in group_rows]
        time = _finite(group_rows[0].get("ls.start_time_ms"))
        contains_spinner = "spinner" in kinds
        nonspinner = [item for item in group if _kind(item[1]) != "spinner"]
        is_simultaneous = len(nonspinner) > 1

        if contains_spinner:
            spinner_count += sum(kind == "spinner" for kind in kinds)
            separator_count += 1
            segment += 1
            block += 1
            previous_row = None
            previous_object = None
            pending_separator = "POST_SPINNER_SEPARATOR"
            groups.append(
                {
                    "group_id": group_index,
                    "time_ms": time,
                    "source_row_indices": group_indices,
                    "object_indices": [],
                    "kinds": kinds,
                    "status": "SPINNER_SEPARATOR",
                    "segment": segment,
                    "block": block,
                }
            )
            # Non-spinners sharing a timestamp with a spinner are adversarial;
            # preserve them as isolated objects below rather than dropping them.
            if not nonspinner:
                continue
            is_simultaneous = True

        if time is None:
            separator_count += 1
            segment += 1
            block += 1
            previous_row = None
            previous_object = None
            pending_separator = "INVALID_TIME_SEPARATOR"

        if is_simultaneous:
            simultaneous_group_count += 1
            simultaneous_object_count += len(nonspinner)
            ambiguous_opportunity_count += max(1, len(nonspinner) - 1)
            separator_count += 1
            segment += 1
            block += 1
            group_object_indices: list[int] = []
            for source_index, row in nonspinner:
                channels = _empty_phase_channels("SIMULTANEOUS_GROUP")
                obj = _compat_object(
                    row,
                    object_index=len(objects),
                    source_row_index=source_index,
                    segment=segment,
                    block=block,
                    dt=0.0,
                    previous_object=None,
                    phase_channels=channels,
                    resolved_preempt_ms=resolved_preempt_ms,
                    structural_status="SIMULTANEOUS_ISOLATED",
                    simultaneous_group_id=group_index,
                )
                group_object_indices.append(len(objects))
                objects.append(obj)
            groups.append(
                {
                    "group_id": group_index,
                    "time_ms": time,
                    "source_row_indices": [item[0] for item in nonspinner],
                    "object_indices": group_object_indices,
                    "kinds": [_kind(item[1]) for item in nonspinner],
                    "status": "SIMULTANEOUS_ISOLATED",
                    "segment": segment,
                    "block": block,
                }
            )
            segment += 1
            block += 1
            previous_row = None
            previous_object = None
            pending_separator = "POST_SIMULTANEOUS_SEPARATOR"
            continue

        # A spinner-only group was already handled above.
        if not nonspinner:
            continue
        source_index, row = nonspinner[0]
        current_time = _finite(row.get("ls.start_time_ms"))
        structural_status = "ELIGIBLE"
        dt = 0.0
        channels = _empty_phase_channels(pending_separator or "NO_PREVIOUS_OBJECT")
        can_pair = False

        if current_time is None:
            structural_status = "INVALID_TIME_ISOLATED"
        elif previous_row is not None and previous_object is not None:
            previous_time = _finite(previous_row.get("ls.start_time_ms"))
            wall_dt = (
                current_time - previous_time
                if previous_time is not None
                else None
            )
            if wall_dt is None or wall_dt <= 0.0:
                separator_count += 1
                segment += 1
                block += 1
                structural_status = "NONMONOTONIC_TIME_ISOLATED"
                channels = _empty_phase_channels("NONMONOTONIC_TIME_SEPARATOR")
                previous_row = None
                previous_object = None
                pending_separator = "POST_NONMONOTONIC_SEPARATOR"
            elif wall_dt > LONG_GAP_MS:
                separator_count += 1
                segment += 1
                block += 1
                structural_status = "LONG_GAP_SECTION_START"
                # The transition is valid counterevidence (a large movement
                # over ten seconds is not fast Jump).  Give it a fresh local
                # section instead of discarding it or allowing either side to
                # lend persistence to the other.
                dt = wall_dt
                channels = _phase_channels(previous_row, row)
                can_pair = True
                pending_separator = None
            else:
                dt = wall_dt
                channels = _phase_channels(previous_row, row)
                can_pair = True
                pending_separator = None
        elif pending_separator:
            structural_status = pending_separator

        obj = _compat_object(
            row,
            object_index=len(objects),
            source_row_index=source_index,
            segment=segment,
            block=block,
            dt=dt if can_pair else 0.0,
            previous_object=previous_object if can_pair else None,
            phase_channels=channels,
            resolved_preempt_ms=resolved_preempt_ms,
            structural_status=structural_status,
            simultaneous_group_id=None,
        )
        object_index = len(objects)
        objects.append(obj)
        groups.append(
            {
                "group_id": group_index,
                "time_ms": current_time,
                "source_row_indices": [source_index],
                "object_indices": [object_index],
                "kinds": [_kind(row)],
                "status": structural_status,
                "segment": segment,
                "block": block,
            }
        )

        if can_pair and previous_object is not None:
            angle = _finite(row.get("ls.slider_aware_angle_rad"))
            angle_available = (
                angle is not None and 0.0 <= angle <= math.pi
            )
            transition = {
                "transition_index": len(transitions),
                "from_object_index": previous_object["object_index"],
                "to_object_index": object_index,
                "from_source_row_index": previous_object["source_row_index"],
                "to_source_row_index": source_index,
                "start_time_ms": previous_object["time"],
                "end_time_ms": obj["time"],
                "wall_time_ms": dt,
                "segment": segment,
                "block": block,
                "from_kind": previous_object["kind"],
                "to_kind": obj["kind"],
                "channels": channels,
                "angle_rad": angle if angle_available else None,
                "angle_available": angle_available,
                "angle_missing_reason": (
                    None
                    if angle_available
                    else (
                        "MISSING_SLIDER_AWARE_ANGLE"
                        if angle is None
                        else "OUT_OF_RANGE_SLIDER_AWARE_ANGLE"
                    )
                ),
                # Keep phase-specific availability independent: missing AR or
                # absolute coordinates must not erase a valid circle radius.
                "radius_px": _positive(row.get("ls.radius_px")),
                "preempt_ms": (
                    _positive(row.get("ls.preempt_ms"))
                    or _positive(resolved_preempt_ms)
                ),
                "signed_turn": obj["signed_turn"],
                "head_distance_px": obj["head_distance"],
                "from_travel_px": (
                    channels[FULL_PATH_FULL_TIME]["distance_px"]
                    - channels[LAZY_FULL]["distance_px"]
                    if channels[FULL_PATH_FULL_TIME]["available"]
                    and channels[LAZY_FULL]["available"]
                    else None
                ),
                "structural_status": "ELIGIBLE",
                "section_start": structural_status == "LONG_GAP_SECTION_START",
            }
            transitions.append(transition)

        # A valid singleton becomes the next causal predecessor even if some
        # signal channels are missing.  Structural and signal coverage remain
        # independent.
        if current_time is not None:
            previous_row = row
            previous_object = obj
            pending_separator = None
        else:
            previous_row = None
            previous_object = None

    novelty = predictability(objects)
    for obj, value in zip(objects, novelty):
        obj["novelty"] = value
        obj["predictability"] = value  # historical spelling/meaning
        obj["motif_predictability"] = 1.0 - value
    for transition in transitions:
        target = objects[transition["to_object_index"]]
        transition["novelty"] = target["novelty"]
        transition["predictability"] = target["motif_predictability"]

    structural_denominator = len(transitions) + ambiguous_opportunity_count
    structural_coverage = (
        len(transitions) / structural_denominator
        if structural_denominator
        else 0.0
    )
    channel_summaries: dict[str, dict[str, Any]] = {}
    for name in CHANNEL_NAMES:
        available = sum(
            bool(transition["channels"][name]["available"])
            for transition in transitions
        )
        reasons: Counter[str] = Counter()
        for transition in transitions:
            channel = transition["channels"][name]
            if not channel["available"]:
                reasons.update(channel["missing_reasons"])
        if ambiguous_opportunity_count:
            reasons["SIMULTANEOUS_GROUP"] += ambiguous_opportunity_count
        candidate_count = structural_denominator
        channel_summaries[name] = {
            "pairing_policy": PAIRING_POLICIES[name],
            "candidate_count": candidate_count,
            "structurally_eligible_count": len(transitions),
            "available_count": available,
            "coverage": available / candidate_count if candidate_count else 0.0,
            "signal_coverage": (
                available / len(transitions) if transitions else 0.0
            ),
            "structural_coverage": structural_coverage,
            "missing_reasons": dict(sorted(reasons.items())),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "local_signal_version": LOCAL_SIGNAL_VERSION,
        "source_local_signal_version": source_version,
        "objects": objects,
        "transitions": transitions,
        "groups": groups,
        "channels": channel_summaries,
        "source_row_count": len(source_rows),
        "object_count": len(objects),
        "nonspinner_object_count": len(objects),
        "transition_count": len(transitions),
        "candidate_transition_count": structural_denominator,
        "ambiguous_transition_count": ambiguous_opportunity_count,
        "structural_coverage": structural_coverage,
        "simultaneous_group_count": simultaneous_group_count,
        "simultaneous_object_count": simultaneous_object_count,
        "spinner_count": spinner_count,
        "separator_count": separator_count,
    }


__all__ = [
    "SCHEMA_VERSION",
    "LOCAL_SIGNAL_VERSION",
    "REFERENCE_RADIUS_PX",
    "HEAD_FULL",
    "MINIMUM_MINIMUM",
    "LAZY_FULL",
    "FULL_PATH_FULL_TIME",
    "CHANNEL_NAMES",
    "PAIRING_POLICIES",
    "predictability",
    "build_transition_bundle",
]
