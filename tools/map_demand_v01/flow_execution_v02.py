"""Experimental Flow: local execution and sustained owned movement load.

No map IDs, PP, total SR, labels, or rank targets enter this module. The
parameters below define a reviewable hypothesis, not a fitted human scale.
Frozen v100 modules are read-only dependencies.
"""
from __future__ import annotations

from collections import Counter, deque
import math
import statistics
from typing import Any, Iterable

from . import flow_geometry_v02 as geometry
from . import flow_spatial_reentry_v01 as reentry_geometry
from . import flow_reentry_execution_v01 as reentry_execution
from . import flow_target_size_v01 as size
from . import paired_transition_geometry_v01 as paired
from . import spatial_axes_v02 as legacy_envelope

SCHEMA_VERSION = "flow_execution_v0.5.2"
SCALE = "EXPERIMENTAL_LOCAL_OR_SUSTAINED_FLOW_LOG_V05"
REFERENCE_RADIUS_PX = paired.REFERENCE_RADIUS_PX
REFERENCE_DISTANCE_PX = 2.0 * REFERENCE_RADIUS_PX
REFERENCE_VELOCITY = 0.65
DISTANCE_EXPONENT = 0.50
VELOCITY_EXPONENT = 0.70
TARGET_SIZE_EXPONENT = 0.70
SUPPORT_REFERENCE_LINKS = 4.0
FULL_MEMBERSHIP_QUALITY = 0.50
CONTINUITY_TIME_MS = 320.0
HISTORY_RELIEF_TIME_MS = 150.0
MIN_WINDOW_EVENTS = 4
MAX_WINDOW_EVENTS = 32
MAX_WINDOW_SPAN_MS = 4000.0
SUSTAINED_REFERENCE_MS = 1000.0
SUSTAINED_RECOVERY_MS = 4000.0
SUSTAINED_OWNERSHIP_THRESHOLD = 0.50
# Coarse, single-parameter calibration; frozen beta/v100 scales stay untouched.
# Prismatix HD ~7.2 is a training reference, not an independent validation.
FLOW_LOG_GAIN = 2.0


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _membership(transition: dict[str, Any]) -> float:
    """A directional link's membership, never a physical-intensity weight.

    A smooth bend is usable evidence. An exact reversal has no Flow direction
    continuity. Change between established turns is a local control input,
    not another chain-membership penalty. This is jump-phase
    geometry and does not claim to reconstruct a slider's internal tangent.
    """
    if not transition["execution_direction_available"]:
        return 0.0
    turn = float(transition["turn_angle_rad"])
    span = float(transition["direction_span_ms"])
    # Preserve the established directional selectivity as an evidence prior,
    # then saturate membership for genuinely gentle bends. cos(turn/2)^2
    # combined with a 0.5 saturation point would call a regular 90-degree
    # square perfect Flow (a real jump-map counterexample), so do not use it.
    bend = max(0.0, 1.0 - turn / math.pi) ** 2
    timing = 1.0 / (1.0 + (span / CONTINUITY_TIME_MS) ** 4)
    return bend * timing


def execution_intensity(distance_px: float, time_ms: float, radius_px: float) -> float:
    """Joint amplitude/deadline load; observed radius is applied once.

    The velocity reference/exponent, CS exponent and final log conversion
    retain the previous scale's conventions. Independent sqrt(amplitude)
    retains displacement information that D/T alone discarded (as in the
    existing joint spatial model). It has no distance-only load floor:
    fixed-distance demand tends to zero when its available time grows.
    """
    if distance_px == 0.0:
        return 0.0
    return (
        (distance_px / REFERENCE_DISTANCE_PX) ** DISTANCE_EXPONENT
        * (distance_px / time_ms / REFERENCE_VELOCITY) ** VELOCITY_EXPONENT
        * (REFERENCE_RADIUS_PX / radius_px) ** TARGET_SIZE_EXPONENT
    )


def _load_value(load: float) -> float:
    # Same logarithmic scale, evaluated without overflowing gain * load for
    # an otherwise finite extreme input. This is not a high-value clamp.
    logarithm = (
        math.log1p(FLOW_LOG_GAIN * load) if load <= 1.0
        else math.log(load) + math.log(FLOW_LOG_GAIN)
        + math.log1p((1.0 / load) / FLOW_LOG_GAIN)
    )
    return size.FLOW_LOG_COEFFICIENT * logarithm / math.log(2.0)


def _candidate(window: list[dict[str, Any]], intensity: float, links: float) -> dict[str, Any]:
    """A local execution pattern supported by its own interior movements."""
    support = -math.expm1(-((links / SUPPORT_REFERENCE_LINKS) ** 2))
    load = intensity * support
    return {
        "kind": "CONTINUOUS_FLOW",
        "value": _load_value(load),
        "support": support,
        "chain_support": support,
        "chain_establishment": support,
        "mean_direction_membership": statistics.fmean(item["membership"] for item in window[1:]),
        "owned_movement_evidence": links,
        "execution_intensity": intensity,
        "raw_peak_intensity": max(item["intensity"] for item in window),
        "supported_execution_load": intensity * support,
        "start_ms": window[0]["start_time_ms"],
        "end_ms": window[-1]["time"],
        "duration_ms": window[-1]["time"] - window[0]["start_time_ms"],
        "event_count": len(window),
        "source_index_first": window[0]["source_index"],
        "source_index_last": window[-1]["source_index"],
        "block": window[0]["block"],
        "segment": window[0]["segment"],
        "run": window[0]["run"],
        "mean_distance_px": statistics.fmean(item["distance"] for item in window),
        "mean_time_ms": statistics.fmean(item["time_ms"] for item in window),
        "mean_velocity_px_per_ms": statistics.fmean(item["distance"] / item["time_ms"] for item in window),
        "mean_radius_px": statistics.fmean(item["radius"] for item in window),
        "slider_tangent_unknown_count": sum(item["slider_tangent_unknown"] for item in window),
    }


def _history_relief(previous: dict[str, Any], current: dict[str, Any]) -> float:
    """Relieve repeated direction loss for compact, closely timed motion.

    Both neighboring movements must qualify; a cheap step cannot lend this
    relief to an adjacent large jump. The reference diameter is fixed so CS
    changes execution demand without reclassifying the same arrangement.
    This is an uncalibrated continuity hypothesis, not a reaction-time law.
    """
    spacing = max(previous["distance"], current["distance"])
    span = max(previous["time_ms"], current["time_ms"])
    discrete = (spacing / REFERENCE_DISTANCE_PX) * (span / HISTORY_RELIEF_TIME_MS)
    # Evaluate either side through a quantity <= 1, including finite inputs
    # whose product overflows. Large gaps then have zero relief, not an error.
    power = (1.0 / discrete if discrete > 1.0 else discrete) ** 4
    return power / (1.0 + power) if discrete > 1.0 else 1.0 / (1.0 + power)


def _supported_intensity(values, ownership):
    """Harder movements establish their own level; easy ones cannot dilute it.

    Each level uses only evidence reaching that intensity. A dominant single
    movement has at most the corroborating mass of all its peers.
    """
    mass = strongest = load = support = established = 0.0
    ordered = sorted(zip(values, ownership), reverse=True)
    for index, (value, weight) in enumerate(ordered):
        mass += weight
        strongest = max(strongest, weight)
        established = min(mass, 2.0 * (mass - strongest))
        support = -math.expm1(-((established / SUPPORT_REFERENCE_LINKS) ** 2))
        lower = ordered[index + 1][0] if index + 1 < len(ordered) else 0.0
        load += (value - lower) * support
    return load, load / support if support > 0 else 0.0, established


def _best_candidate_ending(window: list[dict[str, Any]], *, value_only: bool = False) -> dict[str, Any] | None:
    """Bind variable-amplitude intensity to the actual local Flow chain.

    An interior movement requires direction evidence on BOTH sides. Its
    ownership is further discounted by intervening links to this endpoint,
    with local spacing/time relief from repeatedly applying direction loss.
    A non-Flow jump at a window boundary cannot lend its intensity to the
    easy chain inside. A fully supported width-varying curve retains its
    stronger movements instead of being capped at every weaker movement.

    The SAME absolute ownership mass establishes support, so normalization
    cannot turn almost-zero ownership into fully established intensity.
    """
    if len(window) < MIN_WINDOW_EVENTS:
        return None
    # Suffixes share the endpoint, so link survival and physical context are
    # identical. Compute them once, keeping the original summation order.
    history_relief = [_history_relief(a, b) for a, b in zip(window, window[1:])]
    all_links = [
        _smoothstep(current["membership"] / FULL_MEMBERSHIP_QUALITY)
        if current["direction_reference"] == previous["transition_index"] else 0.0
        for previous, current in zip(window, window[1:])
    ]
    all_ownership = [0.0] * (len(window) - 2)
    survival = 1.0
    for index in range(len(window) - 2, 0, -1):
        all_ownership[index - 1] = min(all_links[index - 1], all_links[index]) * survival
        survival *= all_links[index] + (1.0 - all_links[index]) * history_relief[index]
    all_movement_values = [item["intensity"] for item in window[1:-1]]
    all_control_ratios = [
        (window[index]["turn_adjustment_ratio"] or 0.0)
        * (math.sqrt(all_links[index - 2] * all_links[index - 1]) if index >= 2 else 0.0)
        for index in range(1, len(window) - 1)
    ]
    all_values = [value * math.hypot(1.0, ratio) for value, ratio in zip(all_movement_values, all_control_ratios)]
    best_rank = best = None
    for count in range(MIN_WINDOW_EVENTS, len(window) + 1):
        links = all_links[-(count - 1):]
        if any(link == 0.0 for link in links):
            break  # Every longer suffix contains the same broken link.
        ownership = all_ownership[-(count - 2):]
        mass = sum(ownership)
        if mass <= 0.0:
            continue
        movement_values = all_movement_values[-(count - 2):]
        control_ratios = all_control_ratios[-(count - 2):]
        values = all_values[-(count - 2):]
        # The first interior motion cannot import a turn from outside this
        # suffix; all later three-vector contexts are shared with the window.
        control_ratios[0] = 0.0
        values[0] = movement_values[0]
        # This orthogonal combination is an explicit, uncalibrated hypothesis
        # for local turn adjustment, not measured cursor acceleration. Both
        # channels use this movement's own D/T/R; no map-level axis is added.
        # Each intensity level must be established by movements reaching it.
        # Easy interior movements neither dilute nor establish a harder level;
        # a lone exceptional movement has no corroboration at its own level.
        _, intensity, supported_mass = _supported_intensity(values, ownership)
        support = -math.expm1(-((supported_mass / SUPPORT_REFERENCE_LINKS) ** 2))
        value = _load_value(intensity * support)
        rank = (value,) if value_only else (value, support, window[-count]["start_time_ms"] - window[-1]["time"])
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best = (count, links, ownership, mass, movement_values, control_ratios, values, intensity, supported_mass)
    if best is None:
        return None
    # Only the winning suffix is consumed by local, sustained and reentry
    # evaluation. Preserve its full diagnostics without building discarded ones.
    count, links, ownership, mass, movement_values, control_ratios, values, intensity, supported_mass = best
    candidate = _candidate(window[-count:], intensity, supported_mass)
    direct_ownership = [min(a, b) for a, b in zip(links, links[1:])]
    candidate["corroborating_evidence"] = sum(direct_ownership) - max(direct_ownership)
    candidate["uncapped_owned_intensity"] = sum(value * (weight / mass) for value, weight in zip(values, ownership))
    candidate["movement_execution_intensity"] = _supported_intensity(movement_values, ownership)[1]
    candidate["local_control_increment"] = max(0.0, intensity - candidate["movement_execution_intensity"])
    candidate["mean_supported_turn_adjustment_ratio"] = sum(ratio * (weight / mass) for ratio, weight in zip(control_ratios, ownership))
    candidate["control_source_within_candidate"] = True
    candidate["spatial_reentry_classified"] = False
    candidate["mean_history_relief"] = statistics.fmean(history_relief[-len(links):])
    return candidate


def _sustained_flow(records, local_by_end, transitions, reentry_candidates):
    """Accumulate each owned movement once, independently of window overlap.

    A fourth-power time norm emphasizes maintained high load. It does not
    transfer load from another axis or sum the scores of local windows.
    Reference time, recovery and ownership threshold remain uncalibrated.
    Known slider motion can relieve load despite lacking an exit direction;
    unknown geometry and structural breaks never carry evidence across them.
    """
    reentries = {}
    for section in reentry_candidates:
        indices = section["anchor_transition_indices"] + section["bridge_transition_indices"]
        for index in indices:
            reentries[index] = max(reentries.get(index, 0.0), section["supported_execution_load"])
    retained = 0.0
    last = start = first = block = None
    count = charged = 0
    winner = None
    for transition in transitions:
        index = transition["transition_index"]
        sample = records.get(index)
        current, previous = records.get(index + 1), records.get(index - 1)
        if transition["block"] != block or transition.get("section_start"):
            retained, last, start, first, count = 0.0, None, None, None, 0
            block = transition["block"]
        if sample is None:
            phase = transition["channels"][paired.FULL_PATH_FULL_TIME]
            recoverable = (
                transition["from_kind"] == "slider"
                and transition.get("direction_missing_reason") == "SLIDER_TRAVEL_WITHOUT_EXIT_DIRECTION"
            ) or transition.get("zero_displacement")
            radius = _finite(transition.get("radius_px"))
            if recoverable and phase["available"] and radius is not None and radius > 0:
                retained *= math.exp(-phase["time_ms"] / SUSTAINED_RECOVERY_MS)
                last = transition["end_time_ms"]
            else:
                retained, last, start, first, count = 0.0, None, None, None, 0
            continue
        if start is None:
            start, first = sample["start_time_ms"], sample["source_index"]
        elapsed = sample["time_ms"] if last is None else sample["time"] - last
        last = sample["time"]
        count += 1
        slider = transition["from_kind"] == "slider"
        local = local_by_end.get(index + 1)
        load = 0.0
        if (local and previous and current and not slider
                and current["direction_reference"] == index
                and sample["direction_reference"] == index - 1):
            quality = min(_smoothstep(sample["membership"] / FULL_MEMBERSHIP_QUALITY),
                          _smoothstep(current["membership"] / FULL_MEMBERSHIP_QUALITY))
            # A longer transfer between faster phrases has extra adjustment
            # time. Similar directions alone do not make it sustained Flow.
            times = (previous["time_ms"], sample["time_ms"], current["time_ms"])
            quality *= min(times) / max(times)
            relief = min(_history_relief(previous, sample), _history_relief(sample, current))
            # Compactness can preserve existing directional evidence, but
            # cannot manufacture it at a reversal or a missing boundary.
            evidence_span = quality + (1.0 - relief)
            preserved = quality / evidence_span if evidence_span > 0 else 0.0
            ownership = quality + (1.0 - quality) * relief * preserved
            credit = _smoothstep((ownership - SUSTAINED_OWNERSHIP_THRESHOLD)
                                 / (1.0 - SUSTAINED_OWNERSHIP_THRESHOLD))
            turn_context = math.sqrt(
                _smoothstep(sample["membership"] / FULL_MEMBERSHIP_QUALITY)
                * _smoothstep(current["membership"] / FULL_MEMBERSHIP_QUALITY)
            )
            intensity = min(sample["intensity"], max(previous["intensity"], current["intensity"])) * math.hypot(
                1.0, (current["turn_adjustment_ratio"] or 0.0) * turn_context
            )
            # Local support describes a bounded window, not the burden of
            # these already-owned movements over time. Applying it here
            # again erases repeated tight bends as their history rolls out.
            # A neighboring movement must corroborate this physical level;
            # easy movements elsewhere in the window cannot average it down.
            load = intensity * credit * _smoothstep(
                local["corroborating_evidence"]
            )
        if not slider:
            load = max(load, min(sample["intensity"], reentries.get(index, 0.0)))
        if not slider and local and previous and current and load <= 0:
            # A known non-Flow circle transfer ends sustained Flow. Fast
            # tapping alone must not carry this load across unrelated runs.
            retained = 0.0
            start, first, count = sample["time"], sample["source_index"], 0
        # Established circle Flow does not recover merely for being slower:
        # otherwise its length response would asymptote again at low BPM.
        rest = elapsed if slider else max(0.0, elapsed - HISTORY_RELIEF_TIME_MS) if load <= 0 else 0.0
        retained *= math.exp(-rest / SUSTAINED_RECOVERY_MS)
        added = load * (sample["time_ms"] / SUSTAINED_REFERENCE_MS) ** 0.25
        hi, lo = max(retained, added), min(retained, added)
        retained = hi * (1.0 + (lo / hi) ** 4) ** 0.25 if hi else 0.0
        if not math.isfinite(retained):
            return {"status": "UNAVAILABLE", "reason": "NONFINITE_SUSTAINED_LOAD", "winner": None}
        if load > 0:
            charged += 1
        if not local or load <= 0:
            continue
        value = _load_value(retained)
        if winner is None or value > winner["value"]:
            winner = {
                "kind": "SUSTAINED_FLOW", "value": value,
                "supported_execution_load": retained,
                "support": local["support"], "chain_support": local["support"],
                "start_ms": start, "end_ms": sample["time"],
                "duration_ms": sample["time"] - start, "event_count": count,
                "source_index_first": first, "source_index_last": sample["source_index"],
                "execution_intensity": local["execution_intensity"],
                "raw_peak_intensity": local["raw_peak_intensity"], "local_section": local,
            }
    return {"status": "AVAILABLE", "winner": winner, "charged_movements": charged,
            "remaining_load": retained, "power": 4.0,
            "reference_ms": SUSTAINED_REFERENCE_MS, "recovery_ms": SUSTAINED_RECOVERY_MS,
            "ownership_threshold": SUSTAINED_OWNERSHIP_THRESHOLD}


def extract_flow_measure(
    rows: Iterable[dict[str, Any]],
    effective_mods: Iterable[str] = (),
    *,
    circle_size: float | None = None,
    resolved_preempt_ms: float | None = None,
) -> dict[str, Any]:
    """Extract a raw axis measure from already transformed Local 0.4 rows.

    Mod labels and nominal CS are provenance only. Geometry already contains
    modded times/positions/radii; they must never be transformed a second time.
    Known zero movement is observed zero; missing phase data is unavailable.
    """
    bundle = geometry.build_flow_geometry(rows, resolved_preempt_ms)
    mods = tuple(sorted(str(mod) for mod in effective_mods))
    denominator = bundle["candidate_transition_count"]
    eligible = 0
    missing: Counter[str] = Counter()
    active: deque[dict[str, Any]] = deque()
    run = 0
    last_block = None
    candidates: list[dict[str, Any]] = []
    winner = None
    raw_peak = 0.0
    raw_peak_time = None
    observed_radii: list[float] = []
    observed_records: dict[int, dict[str, Any]] = {}
    local_by_end: dict[int, dict[str, Any]] = {}

    for transition in bundle["transitions"]:
        if transition["block"] != last_block or transition.get("section_start"):
            active.clear()
            run += 1
        last_block = transition["block"]
        phase = transition["channels"][paired.FULL_PATH_FULL_TIME]
        radius = _finite(transition["radius_px"])
        known_zero = bool(
            transition["zero_displacement"]
            and transition["direction_missing_reason"] == "ZERO_FULL_PATH_DISPLACEMENT"
        )
        available = bool(
            phase["available"] and radius is not None and radius > 0
            and (transition["jump_phase_vector_available"] or known_zero)
        )
        if not available:
            reason = "MISSING_RADIUS" if radius is None or radius <= 0 else transition["direction_missing_reason"]
            missing[str(reason or "MISSING_FLOW_GEOMETRY")] += 1
            active.clear()
            run += 1
            continue
        eligible += 1
        observed_radii.append(radius)
        # Long-gap transitions are visible geometry, never a connection into
        # the next Flow chain. The next real movement starts its own evidence.
        if transition.get("section_start"):
            continue
        distance = float(phase["distance_px"])
        time_ms = float(phase["time_ms"])
        try:
            intensity = execution_intensity(distance, time_ms, radius)
        except (OverflowError, ValueError):
            intensity = math.inf
        # The continuous baseline is <= sqrt(2)*M; bounded reentry adds at
        # most M/2 where M is the largest source movement load. A conservative
        # 2*M guard leaves finite headroom for either channel's diagnostics.
        if not math.isfinite(intensity * 2.0):
            # Finite-but-extreme source fields may overflow a joint load.
            # This is unavailable evidence, never an invented zero demand.
            eligible -= 1
            observed_radii.pop()
            missing["NONFINITE_EXECUTION_INTENSITY"] += 1
            active.clear()
            run += 1
            continue
        # A known dwell contributes neither movement intensity nor a fake
        # direction. The next nonzero jump carries its actual elapsed span.
        if known_zero:
            continue
        if intensity > raw_peak:
            raw_peak, raw_peak_time = intensity, transition["end_time_ms"]
        record = {
            "time": transition["end_time_ms"],
            "start_time_ms": transition["end_time_ms"] - time_ms,
            "time_ms": time_ms,
            "distance": distance,
            "radius": radius,
            "intensity": intensity,
            "membership": _membership(transition),
            "turn_adjustment_ratio": transition["jump_phase_turn_adjustment_ratio"],
            "direction_reference": transition["direction_reference_transition_index"],
            "transition_index": transition["transition_index"],
            "source_index": transition["to_source_row_index"],
            "block": transition["block"],
            "segment": transition["segment"],
            "run": run,
            "slider_tangent_unknown": transition["slider_tangent_unavailable"],
        }
        observed_records[record["transition_index"]] = record
        active.append(record)
        while active and (len(active) > MAX_WINDOW_EVENTS or record["time"] - active[0]["start_time_ms"] > MAX_WINDOW_SPAN_MS):
            active.popleft()
        recent = list(active)
        # Every bounded suffix can compete, with intensity owned by the same
        # continuous chain that establishes it.
        best_at_end = _best_candidate_ending(recent)
        if best_at_end is not None:
            rank = (best_at_end["value"], best_at_end["support"], -best_at_end["duration_ms"])
            if winner is None or rank > (winner["value"], winner["support"], -winner["duration_ms"]):
                winner = best_at_end
            candidates.append(best_at_end)
            local_by_end[record["transition_index"]] = best_at_end

    spatial_evidence = reentry_geometry.extract_spatial_reentry_evidence(bundle)

    def local_baseline(first: int, last: int, bridge: int) -> dict[str, Any] | None:
        local = [dict(observed_records[index]) for index in range(first, last + 1)]
        # Rotation changes at b, b+1, b+2 each contain the bridge vector.
        # The new reentry term owns that adjustment, so do not also include
        # the earlier local-turn hypothesis for those same source vectors.
        for record in local:
            if bridge <= record["transition_index"] <= bridge + 2:
                record["turn_adjustment_ratio"] = None
        best = None
        for end in range(MIN_WINDOW_EVENTS, len(local) + 1):
            candidate = _best_candidate_ending(local[:end], value_only=True)
            if candidate is not None and (best is None or candidate["value"] > best["value"]):
                best = candidate
        return best

    spatial_result = reentry_execution.build_reentry_candidates(
        spatial_evidence, observed_records, local_baseline,
        max_span_ms=MAX_WINDOW_SPAN_MS, max_movements=MAX_WINDOW_EVENTS,
    )
    # Reentry's geometry module retains its original unit conversion. Rebase
    # its shared candidates once before comparing them with local/sustained
    # candidates; monotonic conversion preserves its internal winner.
    for candidate in spatial_result["candidates"]:
        candidate["value"] = _load_value(candidate["supported_execution_load"])
    candidates.extend(spatial_result["candidates"])
    spatial_winner = spatial_result["winner"]
    if spatial_winner is not None and (winner is None or spatial_winner["value"] > winner["value"]):
        winner = spatial_winner

    local_winner = winner
    sustained = _sustained_flow(observed_records, local_by_end, bundle["transitions"], spatial_result["candidates"])
    sustained_winner = sustained["winner"]
    if sustained_winner is not None:
        candidates.append(sustained_winner)
        if winner is None or sustained_winner["value"] > winner["value"]:
            winner = sustained_winner

    separated = []
    for candidate in sorted(candidates, key=lambda item: item["value"], reverse=True):
        if candidate["value"] <= 0:
            break
        if all(candidate["end_ms"] <= other["start_ms"] or candidate["start_ms"] >= other["end_ms"] for other in separated):
            separated.append(candidate)
        if len(separated) >= 5:
            break
    return legacy_envelope._base_measure(
        axis="flow_aim", denominator=denominator, eligible_count=eligible,
        winning=winner, scale=SCALE,
        signals={
            "schema_version": SCHEMA_VERSION,
            "effective_mods": list(mods),
            "nominal_circle_size": _finite(circle_size),
            "radius_source": "OBSERVED_LOCAL_ROW_RADIUS_APPLIED_ONCE",
            "observed_radius_range_px": [min(observed_radii), max(observed_radii)] if observed_radii else None,
            "pairing": paired.FULL_PATH_FULL_TIME,
            "direction_source": geometry.DIRECTION_SOURCE,
            "geometry": bundle["diagnostics"],
            "missing_reasons": dict(sorted(missing.items())),
            "individual_execution_intensity_multiplied_by_morphology": False,
            "local_turn_adjustment_combination": "MOVEMENT_LOAD_TIMES_HYPOT_ONE_AND_CONTEXTUAL_ROTATION_CHANGE",
            "control_source_policy": "TWO_SUPPORTED_DIRECTION_LINKS_WITHIN_CURRENT_CANDIDATE",
            "turn_change_reduces_membership": False,
            "control_is_measured_cursor_acceleration": False,
            "spatial_reentry_classified": True,
            "spatial_reentry": {
                "geometry": spatial_evidence["diagnostics"],
                "geometry_parameters": spatial_evidence["parameters"],
                "execution": spatial_result["diagnostics"],
                "best_candidate": spatial_winner,
                "continuous_and_reentry_candidates_are_summed": False,
            },
            "local_intensity_aggregation": "OWN_INTENSITY_LEVEL_SUPPORT_WITH_SPACING_TIME_HISTORY_RELIEF",
            "chain_length_multiplies_unbounded_load": True,
            "local_peak": local_winner,
            "sustained_flow": sustained,
            "local_and_sustained_policy": "MAXIMUM_NOT_SUM",
            "distance_relief_in_flow_membership": False,
            "raw_peak_intensity": raw_peak,
            "raw_peak_time_ms": raw_peak_time,
            "raw_peak_is_public_value": False,
            "separated_local_sections": separated,
            "sections_are_summed": False,
            "parameters": {
                "flow_log_gain": FLOW_LOG_GAIN,
                "flow_log_coefficient": size.FLOW_LOG_COEFFICIENT,
                "reference_distance_px": REFERENCE_DISTANCE_PX,
                "reference_velocity_px_per_ms": REFERENCE_VELOCITY,
                "distance_exponent": DISTANCE_EXPONENT,
                "velocity_exponent": VELOCITY_EXPONENT,
                "target_size_exponent": TARGET_SIZE_EXPONENT,
                "support_reference_links": SUPPORT_REFERENCE_LINKS,
                "full_membership_quality": FULL_MEMBERSHIP_QUALITY,
                "continuity_time_ms": CONTINUITY_TIME_MS,
                "history_relief_time_ms": HISTORY_RELIEF_TIME_MS,
                "history_relief_distance_px": REFERENCE_DISTANCE_PX,
                "window_events_min": MIN_WINDOW_EVENTS,
                "window_events_max": MAX_WINDOW_EVENTS,
                "window_span_ms_max": MAX_WINDOW_SPAN_MS,
                "intensity_support_policy": "SAME_ABSOLUTE_OWNERSHIP_MASS_ESTABLISHES_LOCAL_INTENSITY",
                "isolated_peak_policy": "DOMINANT_LEVEL_EVIDENCE_BOUNDED_BY_CORROBORATING_MOVEMENTS",
                "membership_policy": "SMOOTHSTEP_DIRECTION_QUALITY_SATURATES_AT_FULL_MEMBERSHIP_QUALITY",
                "scale_validation": "EXPERIMENTAL_NOT_FITTED_TO_TARGET_MAPS",
            },
        },
    )
