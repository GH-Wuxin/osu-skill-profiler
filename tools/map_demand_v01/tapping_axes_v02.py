"""Independent local tapping axes with coherent time and section provenance.

This module is intentionally not wired into a historical release.  It consumes
versioned ``ls.*`` rows and exposes a replayable, total-SR-independent basis for
Raw Speed, Stamina, Finger Control and the auxiliary Endurance axis.

Two clocks are kept deliberately separate:

* ``wall_dt_ms`` is the real start-to-start elapsed time;
* ``execution_dt_ms`` is the contract-defined adjusted delta used for tapping
  cadence (including the official 25 ms simultaneous-object floor).

Missing values are never coerced to zero.  Spinners and exact simultaneous
groups are structural separators; neither they nor their adjacent objects
create an ordered tapping or movement pair.
"""

from __future__ import annotations

from collections import Counter
import math
from typing import Any, Iterable


SCHEMA_VERSION = "tapping_axes_v0.3.0"
# Backward-compatible public alias for callers of the standalone bundle.
VERSION = SCHEMA_VERSION
RAW_SPEED_SCALE = "INDEPENDENT_PHYSICAL_RATE_V03"
FULL_COVERAGE = 0.95
DEGRADED_COVERAGE = 0.80
PHRASE_GAP_MS = 1500.0

_TAP_TYPES = {"circle", "slider"}
_OBJECT_TYPES = _TAP_TYPES | {"spinner"}
_RAW_RATE_BANDS = (5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0)
_STAMINA_RATE_BANDS = (
    6.0,
    7.0,
    8.0,
    9.0,
    10.0,
    11.0,
    12.0,
    13.0,
    14.0,
    15.0,
    16.0,
    18.0,
    20.0,
    22.0,
    24.0,
    28.0,
    32.0,
    36.0,
    40.0,
)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _smoothstep(low: float, high: float, value: float) -> float:
    if high <= low:
        raise ValueError("smoothstep requires high > low")
    t = _clamp((value - low) / (high - low))
    return t * t * (3.0 - 2.0 * t)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * _clamp(q)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _weighted_quantile(values: list[tuple[float, float]], q: float) -> float:
    usable = sorted((value, weight) for value, weight in values if weight > 0.0)
    total = sum(weight for _, weight in usable)
    if total <= 0.0:
        return 0.0
    target = _clamp(q) * total
    cumulative = 0.0
    for value, weight in usable:
        cumulative += weight
        if cumulative >= target:
            return value
    return usable[-1][0]


def _coverage_status(candidate_count: int, valid_count: int) -> tuple[str, float | None]:
    if candidate_count <= 0:
        return "INSUFFICIENT", None
    ratio = _clamp(valid_count / candidate_count)
    if ratio >= FULL_COVERAGE:
        return "FULL", ratio
    if ratio >= DEGRADED_COVERAGE:
        return "DEGRADED", ratio
    return "INSUFFICIENT", ratio


def _finish_channel(channel: dict[str, Any]) -> dict[str, Any]:
    status, ratio = _coverage_status(channel["candidate_count"], channel["valid_count"])
    return {
        "status": status,
        "candidate_count": channel["candidate_count"],
        "valid_count": channel["valid_count"],
        "ratio": ratio,
        "missing_reasons": dict(sorted(channel["missing_reasons"].items())),
    }


def _missing(channel: dict[str, Any], reason: str) -> None:
    channel["missing_reasons"][reason] += 1


def build_event_bundle(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return serialisable tapping events and channel-specific coverage.

    A structural candidate is any adjacent, ordered, non-spinner singleton
    pair.  Invalid candidate rows remain in the denominator, so appending
    malformed filler cannot retain full confidence.  Exact simultaneous groups
    have no unique temporal order, so the group and both of its boundaries are
    isolated.  Positive sub-25 ms intervals remain ordered observations and use
    adjusted execution time.
    """

    source = list(rows)
    finite_start_counts = Counter(
        start
        for row in source
        if (start := _finite(row.get("ls.start_time_ms"))) is not None
    )
    simultaneous_times = {
        start for start, count in finite_start_counts.items() if count > 1
    }
    simultaneous_group_count = len(simultaneous_times)
    simultaneous_object_count = sum(
        count
        for start, count in finite_start_counts.items()
        if start in simultaneous_times
    )
    channels: dict[str, dict[str, Any]] = {
        name: {"candidate_count": 0, "valid_count": 0, "missing_reasons": Counter()}
        for name in ("timeline", "tap_execution", "double_tap", "motion")
    }
    events: list[dict[str, Any]] = []
    separator_intervals: list[dict[str, Any]] = []
    timeline_wall_ms = 0.0
    block_id = 0
    previous: dict[str, Any] | None = None
    previous_type: str | None = None

    for index, row in enumerate(source):
        object_type_raw = row.get("ls.object_type")
        object_type = str(object_type_raw) if object_type_raw is not None else None
        start_ms = _finite(row.get("ls.start_time_ms"))
        raw_dt = _finite(row.get("ls.delta_time_ms"))

        timeline = channels["timeline"]
        timeline["candidate_count"] += 1
        timeline_valid = object_type in _OBJECT_TYPES and start_ms is not None
        if index > 0:
            timeline_valid = timeline_valid and raw_dt is not None and raw_dt >= 0.0
        if object_type not in _OBJECT_TYPES:
            _missing(timeline, "object_type_missing_or_invalid")
        if start_ms is None:
            _missing(timeline, "start_time_missing_or_nonfinite")
        if index > 0 and raw_dt is None:
            _missing(timeline, "wall_delta_missing_or_nonfinite")
        elif index > 0 and raw_dt is not None and raw_dt < 0.0:
            _missing(timeline, "negative_wall_delta")
        if timeline_valid:
            timeline["valid_count"] += 1
            if index > 0 and raw_dt is not None:
                timeline_wall_ms += raw_dt

        current_is_spinner = object_type == "spinner"
        previous_is_spinner = previous_type == "spinner"
        current_is_simultaneous = start_ms in simultaneous_times
        previous_start = (
            _finite(previous.get("ls.start_time_ms"))
            if previous is not None
            else None
        )
        previous_is_simultaneous = previous_start in simultaneous_times
        if previous is None:
            previous = row
            previous_type = object_type
            if current_is_spinner or current_is_simultaneous:
                block_id += 1
            continue

        if (
            current_is_spinner
            or previous_is_spinner
            or current_is_simultaneous
            or previous_is_simultaneous
        ):
            if current_is_spinner:
                separator_reason = "current_spinner"
            elif previous_is_spinner:
                separator_reason = "post_spinner"
            elif current_is_simultaneous and previous_is_simultaneous:
                separator_reason = "within_simultaneous_group"
            elif current_is_simultaneous:
                separator_reason = "current_simultaneous_group"
            else:
                separator_reason = "post_simultaneous_group"
            if raw_dt is not None and raw_dt >= 0.0:
                separator_intervals.append(
                    {
                        "wall_dt_ms": raw_dt,
                        "reason": separator_reason,
                    }
                )
            else:
                _missing(timeline, f"{separator_reason}_wall_delta_missing")
            if (
                current_is_spinner
                or (current_is_simultaneous and not previous_is_simultaneous)
                or (previous_is_simultaneous and not current_is_simultaneous)
            ):
                block_id += 1
            previous = row
            previous_type = object_type
            continue

        tap_channel = channels["tap_execution"]
        tap_channel["candidate_count"] += 1
        adjusted_dt = _finite(row.get("ls.adjusted_delta_time_ms"))
        type_valid = object_type in _TAP_TYPES and previous_type in _TAP_TYPES
        wall_valid = raw_dt is not None and raw_dt >= 0.0
        execution_valid = adjusted_dt is not None and adjusted_dt > 0.0
        starts_valid = start_ms is not None and previous_start is not None
        if not type_valid:
            _missing(tap_channel, "tap_object_type_missing_or_invalid")
        if not starts_valid:
            _missing(tap_channel, "tap_start_time_missing_or_nonfinite")
        if not wall_valid:
            _missing(tap_channel, "tap_wall_delta_missing_or_negative")
        if not execution_valid:
            _missing(tap_channel, "adjusted_delta_missing_or_nonpositive")
        if wall_valid and execution_valid and adjusted_dt + 1e-9 < max(raw_dt, 25.0):
            execution_valid = False
            _missing(tap_channel, "adjusted_delta_below_contract_floor")
        if starts_valid and wall_valid:
            observed = start_ms - previous_start
            if abs(observed - raw_dt) > max(0.01, abs(raw_dt) * 1e-9):
                wall_valid = False
                _missing(tap_channel, "wall_delta_start_time_mismatch")
        tap_valid = type_valid and starts_valid and wall_valid and execution_valid
        if tap_valid:
            tap_channel["valid_count"] += 1

        double_tap_channel = channels["double_tap"]
        double_tap_channel["candidate_count"] += 1
        double_tap_feasibility = _finite(row.get("ls.double_tap_feasibility"))
        double_tap_valid = (
            tap_valid
            and double_tap_feasibility is not None
            and 0.0 <= double_tap_feasibility <= 1.0
        )
        if not tap_valid:
            _missing(double_tap_channel, "tap_pair_invalid")
        elif double_tap_feasibility is None:
            _missing(double_tap_channel, "double_tap_feasibility_missing_or_nonfinite")
        elif not 0.0 <= double_tap_feasibility <= 1.0:
            _missing(double_tap_channel, "double_tap_feasibility_out_of_range")
        if double_tap_valid:
            double_tap_channel["valid_count"] += 1

        motion_channel = channels["motion"]
        motion_candidate = type_valid and starts_valid and wall_valid and raw_dt > 0.0
        previous_travel = _finite(previous.get("ls.lazy_travel_distance_cs_normalised"))
        lazy_jump = _finite(row.get("ls.lazy_jump_distance_cs_normalised"))
        motion_valid = False
        path_distance: float | None = None
        if motion_candidate:
            motion_channel["candidate_count"] += 1
            if previous_travel is None:
                _missing(motion_channel, "previous_lazy_travel_missing_or_nonfinite")
            elif previous_travel < 0.0:
                _missing(motion_channel, "previous_lazy_travel_negative")
            if lazy_jump is None:
                _missing(motion_channel, "lazy_jump_missing_or_nonfinite")
            elif lazy_jump < 0.0:
                _missing(motion_channel, "lazy_jump_negative")
            if (
                previous_travel is not None
                and previous_travel >= 0.0
                and lazy_jump is not None
                and lazy_jump >= 0.0
            ):
                motion_valid = True
                path_distance = previous_travel + lazy_jump
                motion_channel["valid_count"] += 1

        phrase_break = bool(wall_valid and raw_dt > PHRASE_GAP_MS)
        previous_end = _finite(previous.get("ls.end_time_ms"))
        hold_ratio = 0.0
        if previous_end is not None and previous_start is not None and adjusted_dt is not None:
            hold_ratio = _clamp((previous_end - previous_start) / max(adjusted_dt, 1e-9))
        event = {
            "row_index": index,
            "block_id": block_id,
            "phrase_break": phrase_break,
            "pair_eligible": True,
            "tap_valid": tap_valid,
            "motion_valid": motion_valid,
            "previous_object_type": previous_type,
            "object_type": object_type,
            "previous_start_ms": previous_start,
            "start_ms": start_ms,
            "wall_dt_ms": raw_dt if wall_valid else None,
            "execution_dt_ms": adjusted_dt if execution_valid else None,
            "hold_ratio": hold_ratio,
            "full_path_distance_cs_normalised": path_distance,
            "full_path_time_ms": raw_dt if motion_valid else None,
            "angle_rad": _finite(row.get("ls.slider_aware_angle_rad")),
            "double_tap_feasibility": (
                double_tap_feasibility if double_tap_valid else None
            ),
            "double_tap_valid": double_tap_valid,
        }
        events.append(event)
        if phrase_break or not tap_valid:
            block_id += 1
        previous = row
        previous_type = object_type

    coverage = {name: _finish_channel(channel) for name, channel in channels.items()}
    return {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "events": events,
        "coverage": coverage,
        "timeline": {
            "row_count": len(source),
            "wall_duration_ms": timeline_wall_ms,
            "separator_wall_duration_ms": sum(item["wall_dt_ms"] for item in separator_intervals),
            "separator_interval_count": len(separator_intervals),
            "separator_intervals": separator_intervals,
            "simultaneous_group_count": simultaneous_group_count,
            "simultaneous_object_count": simultaneous_object_count,
        },
    }


def _coverage_view(
    bundle: dict[str, Any],
    *,
    include_double_tap: bool = False,
    include_motion: bool = False,
) -> dict[str, Any]:
    names = ["timeline", "tap_execution"]
    if include_double_tap:
        names.append("double_tap")
    statuses = [bundle["coverage"][name]["status"] for name in names]
    rank = {"FULL": 2, "DEGRADED": 1, "INSUFFICIENT": 0}
    status = min(statuses, key=rank.__getitem__)
    ratios = [
        bundle["coverage"][name]["ratio"]
        for name in names
        if bundle["coverage"][name]["ratio"] is not None
    ]
    result = {
        "status": status,
        "ratio": min(ratios) if ratios else None,
        "channels": {name: dict(bundle["coverage"][name]) for name in names},
    }
    if include_motion:
        result["channels"]["motion"] = dict(bundle["coverage"]["motion"])
        result["active_motion_channel"] = (
            bundle["coverage"]["motion"]["status"] != "INSUFFICIENT"
        )
    return result


def _empty_measure(status: str, coverage: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "value": 0.0,
        "support": 0.0,
        "counterevidence": 0.0 if status == "INSUFFICIENT" else 1.0,
        "activation": 0.0,
        "evidence_count": 0,
        "coverage": coverage,
        "winning_run": None,
        "winning_window": None,
        "total_sr_used": False,
        "signals": {},
    }


def _tap_blocks(bundle: dict[str, Any]) -> list[list[dict[str, Any]]]:
    blocks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_id: int | None = None
    for event in bundle["events"]:
        if not event["tap_valid"] or event["phrase_break"]:
            if current:
                blocks.append(current)
                current = []
            current_id = None
            continue
        if current_id is None or event["block_id"] != current_id:
            if current:
                blocks.append(current)
            current = []
            current_id = event["block_id"]
        current.append(event)
    if current:
        blocks.append(current)
    return blocks


def _speed_weight(rate: float, threshold: float) -> float:
    return _smoothstep(0.82 * threshold, 1.02 * threshold, rate)


def _weighted_segments(
    block: list[dict[str, Any]], threshold: float
) -> list[list[tuple[dict[str, Any], float, float]]]:
    segments: list[list[tuple[dict[str, Any], float, float]]] = []
    current: list[tuple[dict[str, Any], float, float]] = []
    for event in block:
        execution_dt = float(event["execution_dt_ms"])
        rate = 1000.0 / execution_dt
        weight = _speed_weight(rate, threshold)
        if weight <= 0.0:
            if current:
                segments.append(current)
                current = []
            continue
        current.append((event, weight, rate))
    if current:
        segments.append(current)
    return segments


def _segment_facts(
    segment: list[tuple[dict[str, Any], float, float]],
    threshold: float,
    *,
    apply_double_tap: bool = False,
) -> dict[str, Any]:
    opportunity_pairs = sum(weight for _, weight, _ in segment)
    double_tap_weight = 0.0
    double_tap_valid_weight = 0.0
    effective_pairs = 0.0
    for event, weight, _ in segment:
        feasibility = event.get("double_tap_feasibility")
        if feasibility is not None:
            double_tap_weight += weight * float(feasibility)
            double_tap_valid_weight += weight
        difficulty_weight = (
            1.0 - float(feasibility)
            if apply_double_tap and feasibility is not None
            else (0.0 if apply_double_tap else 1.0)
        )
        effective_pairs += weight * difficulty_weight
    execution_seconds = sum(
        weight * float(event["execution_dt_ms"]) / 1000.0
        for event, weight, _ in segment
    )
    wall_seconds = sum(
        weight * max(0.0, float(event["wall_dt_ms"])) / 1000.0
        for event, weight, _ in segment
    )
    rate = effective_pairs / execution_seconds if execution_seconds > 0.0 else 0.0
    first = segment[0][0]
    last = segment[-1][0]
    start_ms = float(first["start_ms"]) - max(0.0, float(first["wall_dt_ms"]))
    return {
        "block_id": first["block_id"],
        "start_ms": start_ms,
        "end_ms": float(last["start_ms"]),
        "wall_duration_s": wall_seconds,
        "execution_duration_s": execution_seconds,
        "effective_pairs": effective_pairs,
        "opportunity_pairs": opportunity_pairs,
        "observed_pairs": len(segment),
        "rate_per_s": rate,
        "rate_band_per_s": threshold,
        "double_tap_feasibility_mean": (
            double_tap_weight / double_tap_valid_weight
            if double_tap_valid_weight > 0.0
            else None
        ),
        "double_tap_valid_weight": double_tap_valid_weight,
    }


def _raw_speed_measure(bundle: dict[str, Any]) -> dict[str, Any]:
    coverage = _coverage_view(bundle, include_double_tap=True)
    if coverage["status"] == "INSUFFICIENT":
        return _empty_measure("INSUFFICIENT", coverage)
    best: dict[str, Any] | None = None
    for block in _tap_blocks(bundle):
        for threshold in _RAW_RATE_BANDS:
            for segment in _weighted_segments(block, threshold):
                facts = _segment_facts(
                    segment,
                    threshold,
                    apply_double_tap=True,
                )
                effective_pairs = facts["effective_pairs"]
                rate = facts["rate_per_s"]
                # A single isolated interval is not enough to establish a Raw
                # Speed mechanic.  Evidence grows continuously from a burst;
                # four pairs already retain a strong short-burst response.
                sustain = 1.0 - math.exp(-max(0.0, effective_pairs - 1.0) / 2.0)
                repetition = 1.0 - math.exp(-max(0.0, effective_pairs - 4.0) / 20.0)
                rate_activation = _smoothstep(4.8, 7.0, rate)
                activation = rate_activation * sustain
                physical_rate_stars = max(0.0, rate - 4.5) / 1.15
                value = (
                    physical_rate_stars
                    * sustain
                    * (0.85 + 0.15 * repetition)
                    * rate_activation
                )
                candidate = dict(facts)
                candidate.update(
                    {
                        "value": value,
                        "activation": activation,
                        "sustain": sustain,
                        "repetition": repetition,
                        "physical_rate_stars": physical_rate_stars,
                    }
                )
                if best is None or candidate["value"] > best["value"]:
                    best = candidate
    if best is None:
        result = _empty_measure(coverage["status"], coverage)
        result["signals"] = {"run_count": 0, "scale": RAW_SPEED_SCALE}
        return result
    support = _clamp(best["activation"] * (0.70 + 0.30 * best["repetition"]))
    return {
        "status": coverage["status"],
        "value": best["value"],
        "support": support,
        "counterevidence": 1.0 - support,
        "activation": best["activation"],
        "evidence_count": best["observed_pairs"],
        "coverage": coverage,
        "winning_run": best,
        "winning_window": None,
        "total_sr_used": False,
        "signals": {
            "rate_per_s": best["rate_per_s"],
            "effective_pairs": best["effective_pairs"],
            "opportunity_pairs": best["opportunity_pairs"],
            "double_tap_feasibility_mean": best[
                "double_tap_feasibility_mean"
            ],
            "sustain": best["sustain"],
            "repetition": best["repetition"],
            "scale": RAW_SPEED_SCALE,
        },
    }


def _stamina_measure(bundle: dict[str, Any]) -> dict[str, Any]:
    coverage = _coverage_view(bundle)
    if coverage["status"] == "INSUFFICIENT":
        return _empty_measure("INSUFFICIENT", coverage)
    best: dict[str, Any] | None = None
    for block in _tap_blocks(bundle):
        for threshold in _STAMINA_RATE_BANDS:
            for segment in _weighted_segments(block, threshold):
                facts = _segment_facts(segment, threshold)
                effective_pairs = facts["effective_pairs"]
                rate = facts["rate_per_s"]
                wall_s = facts["wall_duration_s"]
                notes_activation = 1.0 - math.exp(-max(0.0, effective_pairs - 4.0) / 8.0)
                duration_activation = 1.0 - math.exp(-wall_s / 4.0)
                speed_activation = _smoothstep(5.0, 7.0, rate)
                repetition = 0.85 + 0.15 * (1.0 - math.exp(-wall_s / 25.0))
                speed_pressure = (max(0.0, rate - 4.0) / 8.0) ** 1.55
                load = (
                    speed_pressure
                    * notes_activation**0.65
                    * duration_activation**0.35
                    * repetition
                )
                value = 10.0 * (1.0 - math.exp(-0.75 * load))
                activation = speed_activation * notes_activation * duration_activation
                candidate = dict(facts)
                candidate.update(
                    {
                        "value": _clamp(value, 0.0, 10.0),
                        "activation": activation,
                        "notes_activation": notes_activation,
                        "duration_activation": duration_activation,
                        "speed_pressure": speed_pressure,
                        "repetition": repetition,
                    }
                )
                if best is None or candidate["value"] > best["value"]:
                    best = candidate
    if best is None:
        result = _empty_measure(coverage["status"], coverage)
        result["signals"] = {"run_count": 0, "scale": "BOUNDED_0_10"}
        return result
    support = _clamp(best["value"] / 10.0)
    return {
        "status": coverage["status"],
        "value": best["value"],
        "support": support,
        "counterevidence": 1.0 - support,
        "activation": best["activation"],
        "evidence_count": best["observed_pairs"],
        "coverage": coverage,
        "winning_run": best,
        "winning_window": None,
        "total_sr_used": False,
        "signals": {
            "rate_per_s": best["rate_per_s"],
            "wall_duration_s": best["wall_duration_s"],
            "effective_pairs": best["effective_pairs"],
            "notes_activation": best["notes_activation"],
            "duration_activation": best["duration_activation"],
            "repetition_within_winning_run": best["repetition"],
            "scale": "BOUNDED_0_10",
        },
    }


def _cadence_similarity(a: float, b: float) -> float:
    if a <= 0.0 or b <= 0.0:
        return 0.0
    distance = abs(math.log2(a / b))
    return math.exp(-((distance / 0.08) ** 2))


def _cadence_strength(dts: list[float], index: int) -> float:
    strength = 1.0
    product = 1.0
    for cursor in range(index - 1, max(-1, index - 9), -1):
        product *= _cadence_similarity(dts[cursor], dts[cursor + 1])
        strength += product
    product = 1.0
    for cursor in range(index + 1, min(len(dts), index + 9)):
        product *= _cadence_similarity(dts[cursor - 1], dts[cursor])
        strength += product
    return strength


def _motif_predictability(dts: list[float], index: int) -> float:
    low = max(0, index - 8)
    high = min(len(dts), index + 9)
    best = 0.0
    for period in range(2, 7):
        comparisons = []
        for cursor in range(low + period, high):
            distance = abs(math.log2(dts[cursor] / dts[cursor - period]))
            comparisons.append(math.exp(-distance / 0.10))
        if len(comparisons) >= 2 * period:
            best = max(best, sum(comparisons) / len(comparisons))
    return best


def _pulse_predictability(dts: list[float], index: int) -> float:
    neighbourhood = dts[max(0, index - 8) : min(len(dts), index + 9)]
    candidates = [dt for dt in neighbourhood if 25.0 <= dt <= 300.0]
    if len(neighbourhood) < 6 or not candidates:
        return 0.0
    best = 0.0
    for pulse in candidates:
        matches = []
        tolerance = max(1.5, pulse * 0.025)
        for dt in neighbourhood:
            multiple = max(1, round(dt / pulse))
            residual = abs(dt - multiple * pulse)
            matches.append(math.exp(-((residual / tolerance) ** 2)))
        best = max(best, sum(matches) / len(matches))
    return 0.80 * best**4


def _finger_measure(bundle: dict[str, Any]) -> dict[str, Any]:
    coverage = _coverage_view(bundle)
    if coverage["status"] == "INSUFFICIENT":
        return _empty_measure("INSUFFICIENT", coverage)
    best: dict[str, Any] | None = None
    total_transition_count = 0
    for block in _tap_blocks(bundle):
        if len(block) < 2:
            continue
        dts = [float(event["execution_dt_ms"]) for event in block]
        strengths = [_cadence_strength(dts, index) for index in range(len(dts))]
        baselines = [
            0.85
            * (1000.0 / dt / 10.0) ** 0.65
            * (1.0 - math.exp(-max(0.0, strength - 1.0) / 8.0))
            for dt, strength in zip(dts, strengths)
        ]
        transitions: list[dict[str, Any]] = []
        for index in range(1, len(block)):
            a = block[index - 1]
            b = block[index]
            contrast = abs(math.log2(dts[index - 1] / dts[index]))
            amplitude = 1.0 - math.exp(-contrast / 0.45)
            if amplitude <= 0.0:
                continue
            rate = 1000.0 / min(dts[index - 1], dts[index])
            speed = (rate / 10.0) ** 0.65
            establishment = 1.0 - math.exp(
                -min(strengths[index - 1], strengths[index]) / 3.0
            )
            motif = _motif_predictability(dts, index)
            pulse = _pulse_predictability(dts, index)
            predictability = max(motif, pulse)
            recovery = 1.0 / (1.0 + (max(dts[index - 1], dts[index]) / 450.0) ** 2)
            hold = max(float(a["hold_ratio"]), float(b["hold_ratio"]))
            cost = (
                speed
                * (0.25 + 1.05 * amplitude)
                * (0.65 + 0.35 * establishment)
                * (1.0 + 0.10 * hold)
                * (1.0 - 0.75 * predictability)
                * recovery
            )
            transitions.append(
                {
                    "time_ms": float(b["start_ms"]),
                    "event_index": index,
                    "cost": cost,
                    "rate_per_s": rate,
                    "contrast_octaves": contrast,
                    "amplitude": amplitude,
                    "predictability": predictability,
                    "pulse_predictability": pulse,
                }
            )
        total_transition_count += len(transitions)
        left = 0
        for right, transition in enumerate(transitions):
            while transitions[left]["time_ms"] < transition["time_ms"] - 6000.0:
                left += 1
            window = transitions[left : right + 1]
            first_event_index = max(0, window[0]["event_index"] - 1)
            last_event_index = window[-1]["event_index"]
            local_baseline = min(1.5, max(baselines[first_event_index : last_event_index + 1]))
            duration_s = max(
                3.0,
                (window[-1]["time_ms"] - window[0]["time_ms"]) / 1000.0 + 0.5,
            )
            load = sum(item["cost"] ** 1.30 for item in window) / duration_s
            transition_peak = 3.50 * load**0.60
            value = transition_peak + local_baseline
            mean_predictability = sum(item["predictability"] for item in window) / len(window)
            activation = 1.0 - math.exp(
                -sum(item["amplitude"] for item in window) / 3.0
            )
            candidate = {
                "block_id": block[0]["block_id"],
                "start_ms": window[0]["time_ms"],
                "end_ms": window[-1]["time_ms"],
                "transition_count": len(window),
                "load_per_s": load,
                "transition_peak": transition_peak,
                "local_baseline": local_baseline,
                "mean_predictability": mean_predictability,
                "activation": activation,
                "value": value,
            }
            if best is None or candidate["value"] > best["value"]:
                best = candidate
    if best is None:
        result = _empty_measure(coverage["status"], coverage)
        result["signals"] = {
            "transition_count": 0,
            "cadence_membership": "CONTINUOUS_LOG_RATIO",
            "scale": "INDEPENDENT_LOCAL_TRANSITION_LOAD",
        }
        return result
    support = _clamp(best["activation"] * (1.0 - 0.50 * best["mean_predictability"]))
    return {
        "status": coverage["status"],
        "value": best["value"],
        "support": support,
        "counterevidence": 1.0 - support,
        "activation": best["activation"],
        "evidence_count": total_transition_count,
        "coverage": coverage,
        "winning_run": None,
        "winning_window": best,
        "total_sr_used": False,
        "signals": {
            "transition_count": total_transition_count,
            "winning_transition_count": best["transition_count"],
            "transition_peak": best["transition_peak"],
            "winning_window_baseline": best["local_baseline"],
            "mean_predictability": best["mean_predictability"],
            "cadence_membership": "CONTINUOUS_LOG_RATIO",
            "scale": "INDEPENDENT_LOCAL_TRANSITION_LOAD",
        },
    }


def _endurance_measure(bundle: dict[str, Any]) -> dict[str, Any]:
    coverage = _coverage_view(bundle, include_motion=True)
    if coverage["status"] == "INSUFFICIENT":
        return _empty_measure("INSUFFICIENT", coverage)
    motion_enabled = bool(coverage["active_motion_channel"])
    active_duration_ms = float(bundle["timeline"]["wall_duration_ms"])
    effective_ms = 0.0
    high_pressure_ms = 0.0
    weighted_pressures: list[tuple[float, float]] = []
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    pressure_event_count = 0

    def finish_segment() -> None:
        nonlocal current
        if current is not None and current["effective_ms"] > 0.0:
            segments.append(current)
        current = None

    for event in bundle["events"]:
        wall_dt = _finite(event.get("wall_dt_ms"))
        if event["phrase_break"] or wall_dt is None or wall_dt <= 0.0:
            finish_segment()
            continue
        tapping = 0.0
        if event["tap_valid"]:
            tapping_rate = 1000.0 / float(event["execution_dt_ms"])
            tapping = _clamp((tapping_rate - 2.5) / 7.5, 0.0, 1.25)
        movement = 0.0
        if motion_enabled and event["motion_valid"]:
            distance = float(event["full_path_distance_cs_normalised"])
            velocity = distance / wall_dt
            movement_speed = _clamp((velocity - 0.25) / 2.5, 0.0, 1.25)
            movement_spacing = _clamp((distance - 50.0) / 250.0, 0.0, 1.20)
            movement = 0.68 * movement_speed + 0.32 * movement_spacing
        angle = _finite(event.get("angle_rad"))
        turn = 0.0 if angle is None else _clamp(1.0 - angle / math.pi)
        control = movement * (0.35 + 0.65 * turn)
        pressure = max(tapping, 0.72 * movement + 0.28 * control, 0.55 * tapping + 0.45 * movement)
        pressure_gate = _clamp((pressure - 0.15) / 0.85)
        support_ms = min(wall_dt, 500.0)
        weighted_pressures.append((pressure, support_ms))
        effective = support_ms * pressure_gate
        effective_ms += effective
        pressure_event_count += int(pressure_gate > 0.0)
        if pressure_gate >= 0.40:
            high_pressure_ms += support_ms

        continuity = (1.0 - _smoothstep(500.0, 900.0, wall_dt)) * pressure_gate
        segment_effective = support_ms * continuity
        if segment_effective <= 0.0:
            finish_segment()
            continue
        if current is None or current["block_id"] != event["block_id"]:
            finish_segment()
            current = {
                "block_id": event["block_id"],
                "start_ms": float(event["start_ms"]) - wall_dt,
                "end_ms": float(event["start_ms"]),
                "effective_ms": 0.0,
                "wall_ms": 0.0,
                "event_count": 0,
            }
        current["effective_ms"] += segment_effective
        current["wall_ms"] += support_ms
        current["end_ms"] = float(event["start_ms"])
        current["event_count"] += 1
    finish_segment()

    if active_duration_ms <= 0.0:
        pressure_coverage = 0.0
        recovery_ratio = 1.0
    else:
        pressure_coverage = _clamp(effective_ms / active_duration_ms)
        recovery_ratio = _clamp(1.0 - effective_ms / active_duration_ms)
    repeated_ms = sum(
        segment["effective_ms"]
        * (1.0 - math.exp(-segment["effective_ms"] / 750.0))
        for segment in segments
    )
    longest_ms = max((segment["effective_ms"] for segment in segments), default=0.0)
    pressure_p90 = _weighted_quantile(weighted_pressures, 0.90)
    intensity = _clamp((pressure_p90 - 0.20) / 0.95)
    effective_s = effective_ms / 1000.0
    repeated_s = repeated_ms / 1000.0
    longest_s = longest_ms / 1000.0
    duration_activation = 1.0 - math.exp(-effective_s / 5.0)
    duration = effective_s / (effective_s + 120.0)
    repeated = repeated_s / (repeated_s + 75.0)
    continuous = longest_s / (longest_s + 20.0)
    duration_shape = duration_activation * _clamp(
        0.38 * duration
        + 0.28 * repeated
        + 0.20 * math.sqrt(pressure_coverage)
        + 0.14 * continuous
    )
    support = duration_shape * (0.34 + 0.66 * math.sqrt(intensity))
    counter = _clamp(
        0.45 * (1.0 - duration_activation)
        + 0.30 * recovery_ratio
        + 0.25 * (1.0 - pressure_coverage)
    )
    attenuation = 1.0 - 0.30 * counter * (1.0 - support**2)
    value = 0.0 if support <= 0.0 else _clamp(10.0 * support**0.88 * attenuation, 0.0, 10.0)
    winning = max(segments, key=lambda item: item["effective_ms"], default=None)
    activation = duration_activation * math.sqrt(intensity)
    return {
        "status": coverage["status"],
        "value": value,
        "support": support,
        "counterevidence": counter,
        "activation": activation,
        "evidence_count": pressure_event_count,
        "coverage": coverage,
        "winning_run": winning,
        "winning_window": None,
        "total_sr_used": False,
        "signals": {
            "active_duration_s": active_duration_ms / 1000.0,
            "effective_duration_s": effective_s,
            "repeated_effective_s": repeated_s,
            "longest_continuous_effective_s": longest_s,
            "pressure_coverage": pressure_coverage,
            "recovery_ratio": recovery_ratio,
            "pressure_p90": pressure_p90,
            "intensity": intensity,
            "duration_activation": duration_activation,
            "duration_shape": duration_shape,
            "motion_channel_used": motion_enabled,
            "movement_pair_count": bundle["coverage"]["motion"]["valid_count"],
            "scale": "BOUNDED_0_10",
        },
    }


def extract_tapping_measures(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Extract four total-SR-independent tapping/global measures."""

    bundle = build_event_bundle(rows)
    measures = {
        "raw_speed": _raw_speed_measure(bundle),
        "stamina": _stamina_measure(bundle),
        "finger_control": _finger_measure(bundle),
        "endurance": _endurance_measure(bundle),
    }
    for measure in measures.values():
        measure["schema_version"] = SCHEMA_VERSION
    return measures


__all__ = [
    "DEGRADED_COVERAGE",
    "FULL_COVERAGE",
    "RAW_SPEED_SCALE",
    "SCHEMA_VERSION",
    "VERSION",
    "build_event_bundle",
    "extract_tapping_measures",
]
