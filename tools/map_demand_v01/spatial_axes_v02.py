"""Independent spatial-axis measures over paired Local Signal 0.4 geometry.

This opt-in module intentionally has no release/CLI integration.  All four
axes consume :mod:`paired_transition_geometry_v01`, never total star rating,
type labels, or another axis.  Values are axis-specific physical log scales;
there is no common clipping or tail compression.
"""
from __future__ import annotations

from collections import Counter, deque
import math
import statistics
from typing import Any, Callable, Iterable

from . import paired_transition_geometry_v01 as geometry


SCHEMA_VERSION = "spatial_axes_v0.3.0"
LOCAL_SIGNAL_VERSION = geometry.LOCAL_SIGNAL_VERSION
REFERENCE_RADIUS_PX = geometry.REFERENCE_RADIUS_PX

FULL_COVERAGE = 0.95
DEGRADED_COVERAGE = 0.80

# A coherent directional opportunity with weight 0.35 should contribute about
# one opportunity's worth of persistence when it is followed by another one.
# The reference is a unit conversion, not a threshold: adjacent evidence stays
# continuous all the way to zero.
FLOW_LINK_REFERENCE_WEIGHT = 0.35


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


def _positive(value: Any) -> float | None:
    number = _finite(value)
    return number if number is not None and number > 0.0 else None


def _status(coverage: float, eligible_count: int) -> tuple[str, float]:
    """Map evidence availability to status without scoring its coherence."""
    if eligible_count <= 0 or coverage < DEGRADED_COVERAGE:
        return "INSUFFICIENT", 0.0
    if coverage < FULL_COVERAGE:
        return "DEGRADED", coverage
    return "FULL", coverage


def _normalise_mods(mods: Iterable[str]) -> tuple[str, ...]:
    aliases = {"NIGHTCORE": "NC", "DOUBLETIME": "DT", "HALFTIME": "HT",
               "HARDROCK": "HR", "EASY": "EZ", "HIDDEN": "HD"}
    values = []
    for mod in mods:
        value = str(mod).strip().upper()
        if value:
            values.append(aliases.get(value, value))
    return tuple(sorted(dict.fromkeys(values)))


def _section_best(
    records: list[dict[str, Any]],
    *,
    max_events: int,
    max_span_ms: float | None,
    scorer: Callable[[list[dict[str, Any]]], dict[str, float]],
) -> dict[str, Any] | None:
    """Find a causal, contiguous local peak without map-wide quantiles."""
    active: deque[dict[str, Any]] = deque()
    active_section: Any = None
    best: dict[str, Any] | None = None
    best_rank: tuple[float, float, int, float] | None = None
    for record in records:
        if record["section"] != active_section:
            active.clear()
            active_section = record["section"]
        active.append(record)
        while len(active) > max_events:
            active.popleft()
        if max_span_ms is not None:
            while active and active[0]["time"] < record["time"] - max_span_ms:
                active.popleft()
        window = list(active)
        scored = scorer(window)
        candidate = {
            "segment": record["segment"],
            "block": record["block"],
            "run": record["section"][1],
            "start_ms": window[0]["time"],
            "end_ms": window[-1]["time"],
            "event_count": len(window),
            **scored,
        }
        rank = (
            float(candidate["value"]),
            float(candidate.get("support", 0.0)),
            int(candidate["event_count"]),
            -float(candidate["start_ms"]),
        )
        if best_rank is None or rank > best_rank:
            best = candidate
            best_rank = rank
    return best


def _base_measure(
    *,
    axis: str,
    denominator: int,
    eligible_count: int,
    winning: dict[str, Any] | None,
    signals: dict[str, Any],
    scale: str,
) -> dict[str, Any]:
    coverage = eligible_count / denominator if denominator > 0 else 0.0
    status, activation = _status(coverage, eligible_count)
    if status == "FULL":
        reason = "COMPLETE_EVIDENCE"
    elif status == "DEGRADED":
        reason = "PARTIAL_EVIDENCE"
    elif denominator <= 0:
        reason = "NO_SPATIAL_OPPORTUNITY"
    elif eligible_count <= 0:
        reason = "NO_VALID_SPATIAL_EVIDENCE"
    else:
        reason = "INSUFFICIENT_EVIDENCE_COVERAGE"
    observed_support = (
        _clamp(float(winning.get("support", 0.0))) if winning else 0.0
    )
    value = float(winning.get("value", 0.0)) if winning else 0.0
    return {
        "status": status,
        "reason": reason,
        "value": value if status != "INSUFFICIENT" else None,
        "support": observed_support,
        "counterevidence": _clamp((1.0 - observed_support) * coverage),
        "eligible_count": eligible_count,
        "coverage": coverage,
        "activation": activation,
        "winning_section": winning,
        "total_sr_used": False,
        "scale": scale,
        "signals": {
            "axis": axis,
            "candidate_count": denominator,
            "coverage_policy": {
                "full_at_or_above": FULL_COVERAGE,
                "degraded_at_or_above": DEGRADED_COVERAGE,
                "below_degraded": "INSUFFICIENT",
            },
            **signals,
        },
    }


def _transition_runs(
    transitions: list[dict[str, Any]],
    availability: Callable[[dict[str, Any]], bool],
) -> list[tuple[dict[str, Any], tuple[int, int]]]:
    """Assign run ids so a missing transition cannot bridge two sections."""
    result: list[tuple[dict[str, Any], tuple[int, int]]] = []
    last_block: Any = None
    run = 0
    for transition in transitions:
        block = transition["block"]
        if block != last_block:
            run = 0
            last_block = block
        if availability(transition):
            result.append((transition, (int(block), run)))
        else:
            run += 1
    return result


def _jump_axis(bundle: dict[str, Any], mods: tuple[str, ...]) -> dict[str, Any]:
    transitions = bundle["transitions"]
    denominator = bundle["candidate_transition_count"]
    channel_counts: Counter[str] = Counter()

    def selected(transition: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
        channels = transition["channels"]
        if channels[geometry.MINIMUM_MINIMUM]["available"]:
            return geometry.MINIMUM_MINIMUM, channels[geometry.MINIMUM_MINIMUM]
        if channels[geometry.HEAD_FULL]["available"]:
            return geometry.HEAD_FULL, channels[geometry.HEAD_FULL]
        return None, None

    available = lambda transition: selected(transition)[1] is not None
    records: list[dict[str, Any]] = []
    for transition, section in _transition_runs(transitions, available):
        channel_name, channel = selected(transition)
        assert channel_name is not None and channel is not None
        channel_counts[channel_name] += 1
        distance = float(channel["distance_px"])
        time = float(channel["time_ms"])
        velocity = float(channel["velocity_px_per_ms"])
        # The load is genuinely joint: increasing time drives it continuously
        # to zero even if distance is huge.  There is no distance-only floor.
        distance_load = distance / (4.0 * REFERENCE_RADIUS_PX)
        velocity_load = velocity / 1.15
        joint_load = math.sqrt(max(0.0, distance_load)) * velocity_load
        support_signal = -math.expm1(-(joint_load ** 1.35))
        records.append(
            {
                "time": transition["end_time_ms"],
                "segment": transition["segment"],
                "block": transition["block"],
                "section": section,
                "joint_load": joint_load,
                "support_signal": support_signal,
                "distance_px": distance,
                "time_ms": time,
                "velocity": velocity,
                "channel": channel_name,
            }
        )

    def score(window: list[dict[str, Any]]) -> dict[str, float]:
        # Six strongest members inside a short contiguous window retain a real
        # burst while preventing a single transition from claiming persistence.
        strongest = sorted(
            window,
            key=lambda item: item["joint_load"],
            reverse=True,
        )[:6]
        load = statistics.fmean(item["joint_load"] for item in strongest)
        observed = statistics.fmean(item["support_signal"] for item in strongest)
        effective_events = sum(item["support_signal"] for item in window)
        evidence = 0.35 + 0.65 * (
            1.0 - math.exp(-effective_events / 3.0)
        )
        return {
            "value": 3.2 * math.log2(1.0 + 1.60 * load) * evidence,
            "support": _clamp(observed * evidence),
            "effective_events": effective_events,
            "joint_load": load,
            "mean_distance_px": statistics.fmean(
                item["distance_px"] for item in strongest
            ),
            "mean_time_ms": statistics.fmean(item["time_ms"] for item in strongest),
            "mean_velocity_px_per_ms": statistics.fmean(
                item["velocity"] for item in strongest
            ),
        }

    winning = _section_best(records, max_events=8, max_span_ms=None, scorer=score)
    return _base_measure(
        axis="jump_aim",
        denominator=denominator,
        eligible_count=len(records),
        winning=winning,
        scale="LOCAL_JOINT_DISTANCE_TIME_PHYSICAL_LOG_V02",
        signals={
            "pairing_priority": [
                geometry.MINIMUM_MINIMUM,
                geometry.HEAD_FULL,
            ],
            "channel_counts": dict(sorted(channel_counts.items())),
            "window_events": 8,
            "window_ms": None,
            "distance_only_floor": False,
            "effective_mods": list(mods),
        },
    )


def _directional_opportunities(
    transitions: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    opportunities: list[tuple[dict[str, Any], dict[str, Any]]] = []
    previous: dict[str, Any] | None = None
    for transition in transitions:
        if previous is None or previous["block"] != transition["block"]:
            previous = transition
            continue
        if previous.get("section_start"):
            previous = transition
            continue
        opportunities.append((previous, transition))
        previous = transition
    return opportunities


def _flow_axis(bundle: dict[str, Any], mods: tuple[str, ...]) -> dict[str, Any]:
    transitions = bundle["transitions"]
    opportunities = _directional_opportunities(transitions)
    denominator = len(opportunities) + bundle["ambiguous_transition_count"]
    records: list[dict[str, Any]] = []
    last_block: Any = None
    run = 0
    missing_reasons: Counter[str] = Counter()

    for previous, current in opportunities:
        block = current["block"]
        if block != last_block:
            run = 0
            last_block = block
        previous_path = previous["channels"][geometry.FULL_PATH_FULL_TIME]
        current_path = current["channels"][geometry.FULL_PATH_FULL_TIME]
        reasons = []
        if not previous_path["available"]:
            reasons.extend(previous_path["missing_reasons"])
        if not current_path["available"]:
            reasons.extend(current_path["missing_reasons"])
        if not current["angle_available"]:
            reasons.append(current["angle_missing_reason"])
        if reasons:
            missing_reasons.update(reason for reason in reasons if reason)
            run += 1
            continue

        distance = float(current_path["distance_px"])
        time = float(current_path["time_ms"])
        velocity = float(current_path["velocity_px_per_ms"])
        angle = float(current["angle_rad"])
        ref_radii = distance / REFERENCE_RADIUS_PX

        # Morphology is continuous.  Angle/spacing/time can weaken coherence,
        # but never turn an otherwise available row into missing evidence.
        angle_weight = (angle / math.pi) ** 2.0
        spacing_weight = -math.expm1(-((distance / (1.10 * REFERENCE_RADIUS_PX)) ** 1.35))
        wide_relief = 1.0 / math.sqrt(1.0 + (ref_radii / 7.0) ** 2.0)
        timing_weight = 1.0 / (1.0 + (time / 320.0) ** 3.0)
        coherence = angle_weight * spacing_weight * wide_relief
        effective_weight = coherence * timing_weight
        records.append(
            {
                "time": current["end_time_ms"],
                "segment": current["segment"],
                "block": block,
                "section": (int(block), run),
                "effective_weight": effective_weight,
                "coherence": coherence,
                "angle_weight": angle_weight,
                "spacing_weight": spacing_weight,
                "timing_weight": timing_weight,
                "velocity": velocity,
                "distance_px": distance,
                "ref_radii": ref_radii,
            }
        )

    def score(window: list[dict[str, Any]]) -> dict[str, float]:
        individual_weight_sum = sum(item["effective_weight"] for item in window)
        links = [
            (
                previous,
                current,
                previous["effective_weight"] * current["effective_weight"],
            )
            for previous, current in zip(window, window[1:])
        ]
        linked_pair_mass = sum(link[2] for link in links)
        effective_pairs = linked_pair_mass / FLOW_LINK_REFERENCE_WEIGHT
        if linked_pair_mass > 0.0:
            coherence = sum(
                math.sqrt(previous["coherence"] * current["coherence"])
                * link_weight
                for previous, current, link_weight in links
            ) / linked_pair_mass
            velocity = sum(
                0.5 * (previous["velocity"] + current["velocity"])
                * link_weight
                for previous, current, link_weight in links
            ) / linked_pair_mass
            spacing = sum(
                0.5 * (previous["ref_radii"] + current["ref_radii"])
                * link_weight
                for previous, current, link_weight in links
            ) / linked_pair_mass
        else:
            coherence = 0.0
            velocity = 0.0
            spacing = 0.0
        persistence = 1.0 - math.exp(-((effective_pairs / 4.5) ** 2.0))
        kinematic = -math.expm1(-((velocity / 0.75) ** 1.20)) if velocity else 0.0
        support = persistence * coherence * (0.35 + 0.65 * kinematic)
        flow_load = (
            math.sqrt(max(0.0, effective_pairs) / 4.0)
            * ((velocity / 0.65) ** 0.70 if velocity else 0.0)
            * (0.35 + 0.65 * coherence)
        )
        return {
            "value": 3.5 * math.log2(1.0 + 1.55 * flow_load),
            "support": _clamp(support),
            "individual_weight_sum": individual_weight_sum,
            "linked_pair_mass": linked_pair_mass,
            "effective_pairs": effective_pairs,
            "coherence": coherence,
            "persistence": persistence,
            "mean_velocity_px_per_ms": velocity,
            "mean_spacing_ref_radii": spacing,
        }

    winning = _section_best(records, max_events=48, max_span_ms=None, scorer=score)
    return _base_measure(
        axis="flow_aim",
        denominator=denominator,
        eligible_count=len(records),
        winning=winning,
        scale="LOCAL_DIRECTIONAL_PATH_COHERENCE_PHYSICAL_LOG_V03",
        signals={
            "pairing": geometry.FULL_PATH_FULL_TIME,
            "directional_opportunity_count": len(opportunities),
            "missing_reasons": dict(sorted(missing_reasons.items())),
            "availability_is_separate_from_coherence": True,
            "angle_weight": "(angle/pi)^2",
            "spacing_weight": "1-exp(-(distance/(1.10*reference_radius))^1.35)",
            "timing_weight": "1/(1+(time/320ms)^3)",
            "continuity_link": "previous_effective_weight*current_effective_weight",
            "link_reference_weight": FLOW_LINK_REFERENCE_WEIGHT,
            "window_events": 48,
            "window_ms": None,
            "effective_mods": list(mods),
        },
    )


def _control_axis(bundle: dict[str, Any], mods: tuple[str, ...]) -> dict[str, Any]:
    transitions = bundle["transitions"]
    opportunities = _directional_opportunities(transitions)
    denominator = len(opportunities) + bundle["ambiguous_transition_count"]
    records: list[dict[str, Any]] = []
    last_block: Any = None
    run = 0
    missing_reasons: Counter[str] = Counter()

    for previous, current in opportunities:
        block = current["block"]
        if block != last_block:
            run = 0
            last_block = block
        prior = previous["channels"][geometry.MINIMUM_MINIMUM]
        now = current["channels"][geometry.MINIMUM_MINIMUM]
        if not prior["available"] or not now["available"]:
            if not prior["available"]:
                missing_reasons.update(prior["missing_reasons"])
            if not now["available"]:
                missing_reasons.update(now["missing_reasons"])
            run += 1
            continue

        prior_distance = float(prior["distance_px"])
        distance = float(now["distance_px"])
        prior_time = float(prior["time_ms"])
        time = float(now["time_ms"])
        prior_velocity = float(prior["velocity_px_per_ms"])
        velocity = float(now["velocity_px_per_ms"])
        movement_presence = math.sqrt(
            (-math.expm1(-prior_distance / REFERENCE_RADIUS_PX))
            * (-math.expm1(-distance / REFERENCE_RADIUS_PX))
        )
        spacing_change = abs(
            math.log2(
                (distance + REFERENCE_RADIUS_PX)
                / (prior_distance + REFERENCE_RADIUS_PX)
            )
        )
        speed_change = abs(
            math.log2((velocity + 0.12) / (prior_velocity + 0.12))
        )
        cadence_change = abs(math.log2(time / prior_time))
        morphology_change = movement_presence * (
            0.36 * spacing_change
            + 0.42 * speed_change
            + 0.22 * cadence_change
        )
        deadline = (150.0 / ((time + prior_time) * 0.5)) ** 0.65
        effort = morphology_change * deadline
        records.append(
            {
                "time": current["end_time_ms"],
                "segment": current["segment"],
                "block": block,
                "section": (int(block), run),
                "effort": effort,
                "movement_presence": movement_presence,
                "spacing_change": spacing_change,
                "speed_change": speed_change,
                "cadence_change": cadence_change,
                "deadline": deadline,
            }
        )

    def score(window: list[dict[str, Any]]) -> dict[str, float]:
        efforts = sorted((item["effort"] for item in window), reverse=True)[:6]
        effort = statistics.fmean(efforts)
        effective_events = sum(-math.expm1(-item["effort"]) for item in window)
        evidence = 0.35 + 0.65 * (
            1.0 - math.exp(-effective_events / 3.0)
        )
        return {
            "value": 5.0 * math.log2(1.0 + 1.50 * effort) * evidence,
            "support": _clamp((-math.expm1(-effort)) * evidence),
            "effective_events": effective_events,
            "morphology_effort": effort,
            "mean_movement_presence": statistics.fmean(
                item["movement_presence"] for item in window
            ),
            "mean_spacing_change": statistics.fmean(
                item["spacing_change"] for item in window
            ),
            "mean_speed_change": statistics.fmean(
                item["speed_change"] for item in window
            ),
            "mean_cadence_change": statistics.fmean(
                item["cadence_change"] for item in window
            ),
        }

    winning = _section_best(records, max_events=8, max_span_ms=None, scorer=score)
    return _base_measure(
        axis="aim_control",
        denominator=denominator,
        eligible_count=len(records),
        winning=winning,
        scale="MINIMUM_PHASE_LOCAL_MORPHOLOGY_CHANGE_LOG_V02",
        signals={
            "pairing": geometry.MINIMUM_MINIMUM,
            "opportunity_count": len(opportunities),
            "missing_reasons": dict(sorted(missing_reasons.items())),
            "head_full_minimum_time_mixing": False,
            "direction_channel": "UNAVAILABLE_WITHOUT_MINIMUM_PHASE_VECTOR",
            "window_events": 8,
            "window_ms": None,
            "effective_mods": list(mods),
        },
    )


def _precision_axis(bundle: dict[str, Any], mods: tuple[str, ...]) -> dict[str, Any]:
    transitions = bundle["transitions"]
    denominator = bundle["candidate_transition_count"]
    records: list[dict[str, Any]] = []
    last_block: Any = None
    run = 0
    previous_distance: float | None = None
    missing_reasons: Counter[str] = Counter()

    for transition in transitions:
        block = transition["block"]
        if block != last_block:
            run = 0
            previous_distance = None
            last_block = block
        channel = transition["channels"][geometry.MINIMUM_MINIMUM]
        radius = _positive(transition.get("radius_px"))
        if not channel["available"] or radius is None:
            if not channel["available"]:
                missing_reasons.update(channel["missing_reasons"])
            if radius is None:
                missing_reasons["MISSING_RADIUS"] += 1
            run += 1
            previous_distance = None
            continue

        distance = float(channel["distance_px"])
        time = float(channel["time_ms"])
        acquisition = -math.expm1(
            -((distance / (0.90 * REFERENCE_RADIUS_PX)) ** 1.40)
        )
        temporal = math.log2(1.0 + (1000.0 / time) / 4.0)
        # Ordinary CS4 movement is Aim/Flow evidence, not Precision merely
        # because it is fast.  Precision needs a signed loss of target
        # tolerance or a same-phase large-to-micro correction.
        target_tightness = max(
            0.0,
            math.log2(REFERENCE_RADIUS_PX / radius),
        )
        target_effort = acquisition * temporal * target_tightness
        micro_correction = 0.0
        if previous_distance is not None:
            large_setup = -math.expm1(
                -((previous_distance / (4.0 * REFERENCE_RADIUS_PX)) ** 3.0)
            )
            micro_landing = math.exp(
                -((distance / (1.60 * REFERENCE_RADIUS_PX)) ** 2.0)
            )
            timing_weight = 1.0 / (1.0 + (time / 220.0) ** 3.0)
            micro_correction = (
                large_setup * micro_landing * timing_weight
            )
        effort = target_effort + 1.50 * micro_correction
        records.append(
            {
                "time": transition["end_time_ms"],
                "segment": transition["segment"],
                "block": block,
                "section": (int(block), run),
                "effort": effort,
                "acquisition": acquisition,
                "temporal": temporal,
                "target_tightness": target_tightness,
                "target_effort": target_effort,
                "micro_correction": micro_correction,
                "distance_px": distance,
                "time_ms": time,
                "radius_px": radius,
            }
        )
        previous_distance = distance

    def score(window: list[dict[str, Any]]) -> dict[str, float]:
        strongest = sorted(window, key=lambda item: item["effort"], reverse=True)[:6]
        effort = statistics.fmean(item["effort"] for item in strongest)
        effective_events = sum(-math.expm1(-item["effort"]) for item in window)
        evidence = 0.35 + 0.65 * (
            1.0 - math.exp(-effective_events / 3.0)
        )
        return {
            "value": 5.0 * math.log2(1.0 + 1.20 * effort) * evidence,
            "support": _clamp((-math.expm1(-effort)) * evidence),
            "effective_events": effective_events,
            "precision_effort": effort,
            "mean_acquisition": statistics.fmean(
                item["acquisition"] for item in strongest
            ),
            "mean_time_ms": statistics.fmean(item["time_ms"] for item in strongest),
            "mean_radius_px": statistics.fmean(
                item["radius_px"] for item in strongest
            ),
            "mean_target_tightness_octaves": statistics.fmean(
                item["target_tightness"] for item in strongest
            ),
            "mean_target_effort": statistics.fmean(
                item["target_effort"] for item in strongest
            ),
            "mean_micro_correction": statistics.fmean(
                item["micro_correction"] for item in strongest
            ),
        }

    winning = _section_best(records, max_events=8, max_span_ms=None, scorer=score)
    return _base_measure(
        axis="spatial_precision",
        denominator=denominator,
        eligible_count=len(records),
        winning=winning,
        scale="MINIMUM_PHASE_TARGET_ACQUISITION_PHYSICAL_LOG_V02",
        signals={
            "pairing": geometry.MINIMUM_MINIMUM,
            "missing_reasons": dict(sorted(missing_reasons.items())),
            "head_full_minimum_time_mixing": False,
            "radius_direction": "smaller radius increases demand",
            "ordinary_cs4_speed_is_not_precision": True,
            "micro_correction": (
                "same minimum/minimum phase: large setup -> close landing"
            ),
            "window_events": 8,
            "window_ms": None,
            "effective_mods": list(mods),
        },
    )


def extract_spatial_measures(
    rows: Iterable[dict[str, Any]],
    resolved_preempt_ms: float | None = None,
    effective_mods: Iterable[str] = (),
) -> dict[str, Any]:
    """Return four independent spatial measures from Local Signal 0.4 rows."""
    bundle = geometry.build_transition_bundle(rows, resolved_preempt_ms)
    mods = _normalise_mods(effective_mods)
    return {
        "schema_version": SCHEMA_VERSION,
        "local_signal_version": LOCAL_SIGNAL_VERSION,
        "geometry_schema_version": bundle["schema_version"],
        "effective_mods": list(mods),
        "jump_aim": _jump_axis(bundle, mods),
        "flow_aim": _flow_axis(bundle, mods),
        "aim_control": _control_axis(bundle, mods),
        "spatial_precision": _precision_axis(bundle, mods),
        "geometry": {
            "source_row_count": bundle["source_row_count"],
            "object_count": bundle["object_count"],
            "transition_count": bundle["transition_count"],
            "candidate_transition_count": bundle["candidate_transition_count"],
            "structural_coverage": bundle["structural_coverage"],
            "simultaneous_group_count": bundle["simultaneous_group_count"],
            "simultaneous_object_count": bundle["simultaneous_object_count"],
            "spinner_count": bundle["spinner_count"],
            "separator_count": bundle["separator_count"],
            "channels": bundle["channels"],
        },
    }


__all__ = [
    "SCHEMA_VERSION",
    "LOCAL_SIGNAL_VERSION",
    "REFERENCE_RADIUS_PX",
    "FULL_COVERAGE",
    "DEGRADED_COVERAGE",
    "extract_spatial_measures",
]
