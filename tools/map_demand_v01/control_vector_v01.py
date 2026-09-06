"""Experimental local Aim Control from speed changes and sharp turns.

Circle triples have a verified full-phase vector. Sliders use lazy travel plus
exit distance over the complete head interval. Comparing shortened exit phases
to whole circle movements invents changes on feasible constant-speed paths.
Slider direction remains unknown; no player trajectory or tangent is invented.
Circle turning demand depends on the actual angle, not pattern repetition.
Target-size and absolute-deadline responses remain unchanged.
Cadence and raw spacing are not independent control loads. The target-relative
adjustment deadline describes a modelling hypothesis, not measured reaction
time. Its shared scale uses development references, not held-out validation.
"""
from __future__ import annotations

from collections import Counter, deque
import math
from typing import Any, Iterable, Mapping

from . import paired_transition_geometry_v01 as geometry
from . import spatial_axes_v02 as scalar

SCHEMA_VERSION = "control_vector_v0.5.0"
SCALE = "FULL_PHASE_SHARP_TURN_TARGET_RELATIVE_LAYER_LOG_V05"
MAX_EVENTS = 8
MAX_SPAN_MS = 3000.0
SUPPORT_REFERENCE_EVENTS = 3.0
REFERENCE_RADIUS_PX = geometry.REFERENCE_RADIUS_PX
NUMERICAL_ZERO_STARS = 1e-12
ADJUSTMENT_REFERENCE_MS = 150.0
CHANGE_EXPONENT = 0.70
DEADLINE_EXPONENT = 0.65
CHANGE_GAIN = 0.84


def adjustment_pressure(time_ms: float, radius_px: float) -> float:
    """Less target tolerance leaves less usable adjustment time.

    This normalized deadline is not wall time. Equal 2:1 rhythms at 100/50
    and 180/90 ms remain distinct; shrinking a target also raises demand.
    The smooth coupling factor never makes a slow transition a hard zero.
    """
    ratio = time_ms * (radius_px / REFERENCE_RADIUS_PX) / ADJUSTMENT_REFERENCE_MS
    if not math.isfinite(ratio) or ratio <= 0.0:
        raise ValueError("Unrepresentable target-relative deadline")
    # Stable at both extremes without clipping a representable high demand.
    inverse = 1.0 / ratio
    coupling = 1.0 / (1.0 + ratio ** 4) if ratio <= 1.0 else inverse ** 4 / (1.0 + inverse ** 4)
    return inverse ** DEADLINE_EXPONENT * coupling


def full_vector(transition: Mapping[str, Any], rows: list[dict]) -> dict:
    """A displacement/adjusted-time velocity, including a known zero vector."""
    result = {"available": False, "reason": None, "velocity": None,
              "time_clamped": False}
    if transition["from_kind"] != "circle" or transition["to_kind"] != "circle":
        return {**result, "reason": "SLIDER_DIRECTION_PHASE_UNSUPPORTED"}
    full = transition["channels"][geometry.FULL_PATH_FULL_TIME]
    head = transition["channels"][geometry.HEAD_FULL]
    if not full["available"] or not head["available"]:
        return {**result, "reason": "MISSING_MATCHED_PHASE"}
    start, end = (rows[transition[key]] for key in
                  ("from_source_row_index", "to_source_row_index"))
    coords = [geometry._finite(row.get(key)) for row in (start, end)
              for key in ("v091.start_x_px", "v091.start_y_px")]
    if any(value is None for value in coords):
        return {**result, "reason": "MISSING_PHASE_POSITION"}
    dx, dy = coords[2] - coords[0], coords[3] - coords[1]
    distance = math.hypot(dx, dy)
    time = float(full["time_ms"])
    if not (math.isfinite(distance)
            and math.isclose(distance, full["distance_px"], rel_tol=1e-6, abs_tol=1e-6)
            and math.isclose(distance, head["distance_px"], rel_tol=1e-6, abs_tol=1e-6)
            and math.isclose(time, head["time_ms"], rel_tol=1e-9, abs_tol=1e-6)):
        return {**result, "reason": "VECTOR_FULL_PHASE_MISMATCH"}
    return {"available": True, "reason": None, "velocity": [dx / time, dy / time],
            "time_clamped": time > transition["wall_time_ms"] + 1e-6}


def layer_supported_effort(efforts: Iterable[float]) -> float:
    """Integrate bounded support separately at each observed effort level.

    A weak event supports only the layers it reaches. A single spike receives
    S(1), never the S(8) of its weak neighbours. Adding easy context cannot
    dilute a peak or grant high layers additional support.
    """
    values = sorted(float(value) for value in efforts if value > 0.0)
    previous = total = 0.0
    for index, value in enumerate(values):
        count = len(values) - index
        support = -math.expm1(-((count / SUPPORT_REFERENCE_EVENTS) ** 2))
        total += (value - previous) * support
        previous = value
    return total


def local_peak(records: list[dict], effort_key: str = "effort") -> dict | None:
    active: deque[dict] = deque()
    section = None
    best = None
    for record in records:
        if record["section"] != section:
            active.clear()
            section = record["section"]
        active.append(record)
        while active and (len(active) > MAX_EVENTS or
                          record["time"] - active[0]["start_ms"] > MAX_SPAN_MS):
            active.popleft()
        if not active:
            continue
        effort = layer_supported_effort(item[effort_key] for item in active)
        strongest = max(item[effort_key] for item in active)
        candidate = {
            "start_ms": active[0]["start_ms"], "end_ms": record["time"],
            "event_count": len(active), "positive_event_count": sum(
                item[effort_key] > 0 for item in active),
            "value": 5.0 * math.log2(1.0 + 1.50 * effort),
            "supported_effort": effort, "raw_peak_effort": strongest,
            "support": effort / strongest if strongest > 0.0 else 0.0,
            "direction_available_count": sum(item["direction_available"] for item in active),
            "source_transition_indices": [item["transition_index"] for item in active],
        }
        if best is None or (candidate["value"], candidate["support"]) > (best["value"], best["support"]):
            best = candidate
    return best


def extract_control_measure(rows: Iterable[dict[str, Any]], mods: Iterable[str] = (),
                            *, resolved_preempt_ms: float | None = None) -> dict:
    version = getattr(rows, "local_signal_version", None)
    if version is not None and version != geometry.LOCAL_SIGNAL_VERSION:
        raise ValueError("Control requires Local Signal " + geometry.LOCAL_SIGNAL_VERSION)
    source = [dict(row) for row in rows]
    bundle = geometry.build_transition_bundle(source, resolved_preempt_ms)
    opportunities = scalar._directional_opportunities(bundle["transitions"])
    denominator = len(opportunities) + bundle["ambiguous_transition_count"]
    missing: Counter[str] = Counter()
    direction_missing: Counter[str] = Counter()
    records = []
    run = 0
    for previous, current in opportunities:
        prior = previous["channels"][geometry.FULL_PATH_FULL_TIME]
        now = current["channels"][geometry.FULL_PATH_FULL_TIME]
        if not prior["available"] or not now["available"]:
            for channel in (prior, now):
                if not channel["available"]:
                    missing.update(channel["missing_reasons"])
            run += 1
            continue
        radii = [geometry._finite(t.get("radius_px")) for t in (previous, current)]
        if any(radius is None or radius <= 0.0 for radius in radii):
            missing["MISSING_CONTROL_TARGET_RADIUS"] += 1
            run += 1
            continue
        radius = math.sqrt(radii[0]) * math.sqrt(radii[1])
        d0, d1 = float(prior["distance_px"]), float(now["distance_px"])
        t0, t1 = float(prior["time_ms"]), float(now["time_ms"])
        v0, v1 = float(prior["velocity_px_per_ms"]), float(now["velocity_px_per_ms"])
        try:
            radius_factor = REFERENCE_RADIUS_PX / radius
            v0, v1 = v0 * radius_factor, v1 * radius_factor
            deadline = adjustment_pressure(max(t0, t1), radius)
            if not all(math.isfinite(x) for x in (v0, v1, deadline)):
                raise ValueError("Nonfinite control scale")
        except (OverflowError, ValueError, ZeroDivisionError):
            missing["NONFINITE_CONTROL_SCALE"] += 1
            run += 1
            continue
        vectors = [full_vector(transition, source) for transition in (previous, current)]
        available = all(vector["available"] for vector in vectors)
        scalar_change = abs(math.log2((v1 + .12) / (v0 + .12)))
        speed_change = scalar_change
        internal_angle = None
        sharpness = None
        if available:
            delta = math.hypot(*(b - a for a, b in zip(vectors[0]["velocity"], vectors[1]["velocity"]))) * radius_factor
            a, b = (vector["velocity"] for vector in vectors)
            na, nb = math.hypot(*a), math.hypot(*b)
            if na > 0 and nb > 0:
                cosine = max(-1.0, min(1.0, sum((x / na) * (y / nb) for x, y in zip(a, b))))
                # Incoming/outgoing deflection is the supplement of the
                # angle at the hit circle: sharper interior angle => more
                # reversal. Apply this geometry to raw change, not stars.
                sharpness = (1.0 - cosine) / 2.0
                internal_angle = math.degrees(math.acos(-cosine))
                delta *= sharpness
            # Algebraically the old speed-change expression on a straight line.
            speed_change = max(scalar_change, math.log2(1.0 + delta / (min(v0, v1) + .12)))
        else:
            direction_missing.update(set(vector["reason"] for vector in vectors if not vector["available"]))
        presence = math.sqrt((-math.expm1(-d0 / radius)) *
                             (-math.expm1(-d1 / radius)))
        spacing = abs(math.log2((d1 + REFERENCE_RADIUS_PX) / (d0 + REFERENCE_RADIUS_PX)))
        cadence = abs(math.log2(t1 / t0))
        # D and T already determine the velocity change. Adding their raw
        # ratios again turns constant-speed rhythmic resampling into Control.
        # Sublinear change scaling must not amplify roundoff into observed
        # demand, especially when an unavailable direction has scalar zero.
        observed_change = speed_change if speed_change > 1e-12 else 0.0
        observed_scalar = scalar_change if scalar_change > 1e-12 else 0.0
        effort = CHANGE_GAIN * presence * observed_change ** CHANGE_EXPONENT * deadline
        scalar_effort = CHANGE_GAIN * presence * observed_scalar ** CHANGE_EXPONENT * deadline
        if not math.isfinite(effort):
            missing["NONFINITE_CONTROL_EFFORT"] += 1
            run += 1
            continue
        records.append({
            "time": current["end_time_ms"], "start_ms": previous["start_time_ms"],
            "section": (current["block"], run), "transition_index": current["transition_index"],
            "effort": effort, "scalar_effort": scalar_effort,
            "direction_available": available, "speed_change": speed_change,
            "internal_angle_degrees": internal_angle, "turn_sharpness": sharpness,
            "scalar_speed_change": scalar_change, "movement_presence": presence,
            "spacing_change": spacing, "cadence_change": cadence, "deadline": deadline,
            "radius_px": radius, "adjustment_time_ms": max(t0, t1),
            "time_clamped": any(vector["time_clamped"] for vector in vectors),
        })
    winner = local_peak(records)
    scalar_winner = local_peak(records, "scalar_effort")
    direction_count = sum(record["direction_available"] for record in records)
    scalar_coverage = len(records) / denominator if denominator else 0.0
    direction_coverage = direction_count / denominator if denominator else 0.0
    complete = denominator > 0 and len(records) == direction_count == denominator
    value = winner["value"] if winner else None
    # Roundoff in scalar magnitudes after a rigid transform is not observed
    # positive demand. Preserve raw diagnostics, normalise only public zero.
    if value is not None and value <= NUMERICAL_ZERO_STARS:
        value = 0.0
    status = "FULL" if complete else "DEGRADED"
    activation = scalar_coverage if winner else 0.0
    reason = "COMPLETE_DEFINED_MECHANISMS" if complete else "PARTIAL_DIRECTION_MECHANISMS"
    # Coverage elsewhere in the map cannot veto a supported local maximum.
    # It does prevent complete-mechanism or global-counterevidence claims.
    if winner is None:
        status, reason, value = "INSUFFICIENT", "NO_SUPPORTED_LOCAL_CONTROL_EVIDENCE", None
    elif value == 0.0 and not complete:
        status, reason, value = "INSUFFICIENT", "UNKNOWN_DIRECTION_IS_NOT_OBSERVED_ZERO", None
    support = (-math.expm1(-winner["supported_effort"])) * winner["support"] if winner else 0.0
    return {
        "status": status, "reason": reason, "value": value,
        "support": support, "counterevidence": (1.0 - support) if complete else None,
        "eligible_count": len(records), "coverage": scalar_coverage,
        "activation": activation, "winning_section": winner,
        "total_sr_used": False, "scale": SCALE,
        "signals": {
            "schema_version": SCHEMA_VERSION, "candidate_count": denominator,
            "direction_channel": "VERIFIED_CIRCLE_VECTOR_CHANGE_WITH_TURN_SHARPNESS",
            "angle_convention": "INTERIOR_ANGLE_AT_HIT_CIRCLE_SMALLER_IS_SHARPER",
            "turn_sharpness_policy": "HALF_ONE_MINUS_INCOMING_OUTGOING_UNIT_DOT",
            "turn_frequency_policy": "TIME_PRESSURE_AND_LAYER_SUPPORT_WITHIN_8_MOVEMENTS_3_SECONDS",
            "pattern_repetition_discount": False,
            "movement_channel": geometry.FULL_PATH_FULL_TIME,
            "time_basis": "ADJUSTED_HEAD_INTERVAL_MINIMUM_25MS",
            "adjustment_basis": "LONGER_FULL_PHASE_NORMALISED_BY_OBSERVED_TARGET_RADIUS",
            "spacing_and_cadence_are_separate_loads": False,
            "radius_source": "GEOMETRIC_MEAN_OF_TWO_OBSERVED_TRANSITION_RADII",
            "head_full_minimum_time_mixing": False,
            "mechanism_coverage": {"scalar": scalar_coverage, "direction": direction_coverage,
                                   "status": "COMPLETE_DEFINED_MECHANISMS" if complete else "PARTIAL"},
            "missing_reasons": dict(sorted(missing.items())),
            "direction_missing_reasons": dict(sorted(direction_missing.items())),
            "direction_available_count": direction_count,
            "winning_direction_coverage": (winner["direction_available_count"] / winner["event_count"])
                if winner else None,
            "time_clamped_event_count": sum(record["time_clamped"] for record in records),
            "window_events": MAX_EVENTS, "window_ms": MAX_SPAN_MS,
            "support_reference_events": SUPPORT_REFERENCE_EVENTS,
            "support_policy": "EFFORT_LAYER_LOCAL_EVENT_SUPPORT",
            "observed_value_scope": "COMPLETE_DEFINED_MECHANISMS" if complete else "PARTIAL_OBSERVED_MECHANISMS",
            "coverage_policy": "LOCAL_POSITIVE_EVIDENCE_EMITS_WITH_PARTIAL_MAP_COVERAGE",
            "numerical_zero_stars": NUMERICAL_ZERO_STARS,
            "counterevidence_scope": "DEFINED_MODEL_ONLY" if complete else "UNAVAILABLE_FOR_PARTIAL_MECHANISMS",
            "scalar_only_same_aggregation": scalar_winner,
            "effective_mods": list(scalar._normalise_mods(mods)),
            "parameters": {"adjustment_reference_ms": ADJUSTMENT_REFERENCE_MS,
                           "change_exponent": CHANGE_EXPONENT, "deadline_exponent": DEADLINE_EXPONENT,
                           "change_gain": CHANGE_GAIN, "coupling_exponent": 4.0,
                           "scale_validation": "DEVELOPMENT_REFERENCES_ONLY"},
            "known_limitations": [
                "No slider tangent, release direction, client stacking or observed cursor reconstruction",
                "Whole slider-plus-exit averages do not resolve slider-internal velocity changes",
                "Relative velocity change saturates with absolute movement speed; not a full acceleration model",
                "Inherited movement-pair presence suppresses stationary stop/go pairs",
                "Target-relative adjustment time is an unvalidated motor-control proxy, not reaction time",
                "Shared scale and three-event support reference lack independent human validation",
                "Angular sharpness weighting is an uncalibrated geometry hypothesis; no repetition discount is applied",
            ],
        },
        "records": records,
    }
