"""Tolerance and rhythm public beta: three local mechanisms, no total-SR scale.

Beta.1 remains replayable. This module never mutates its dependencies.
All times are post-mod milliseconds; mapper BPM/divisors are not inputs.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Iterable

from . import contract as C
from . import model_v010_beta1 as previous
from . import model_decoupled_v01 as base

ALGORITHM_ID = "MAP_DEMAND_TOLERANCE_RHYTHM_V010_BETA2"
MAP_DEMAND_VERSION = "0.10.0-beta.2"
SCHEMA_VERSION = "map_demand_v0.10.0-beta.2"
AXIS_SCHEMA_VERSION = previous.AXIS_SCHEMA_VERSION
AXIS_ORDER = previous.AXIS_ORDER
extract_from_path = previous.extract_from_path
sha256_file_bytes = previous.sha256_file_bytes
CHANGED_AXES = ("stamina", "spatial_precision", "finger_control")
RELEASE = {
    "version": MAP_DEMAND_VERSION, "stage": "PUBLIC_BETA",
    "label": "0.10.0-beta.2 · 容错与节奏修正版", "basis": previous.MAP_DEMAND_VERSION,
    "known_limitations": [
        "Cadence bands and local rhythm windows are heuristic, not physiological measurements",
        "Group parity estimates alternating-input demand, not the player's actual fingering",
        "Three corrected axes have independent scales; other six retain beta.1 rules",
    ],
}
REF_RADIUS = (54.4 - 4.48 * 4) * 1.00041


def clamp(x: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, x))


def finite(x: Any, fallback: float = 0.0) -> float:
    value = base._finite(x)
    return fallback if value is None else value


def _events(rows: Iterable[dict]) -> list[dict]:
    """Tap-head events with explicit separators; slider ticks are never taps."""
    events = []
    clock = 0.0
    previous_end = 0.0
    separated = True
    previous_was_spinner = False
    for row in rows:
        dt = finite(row.get("ls.adjusted_delta_time_ms"))
        raw_dt = row.get("ls.delta_time_ms", dt)
        clock = finite(row.get("ls.start_time_ms"), clock + max(finite(raw_dt), 0.0))
        if row.get("ls.object_type") == "spinner":
            separated = True
            previous_was_spinner = True
            previous_end = 0.0
            continue
        if previous_was_spinner:
            # There was no tap at the spinner's start to form this pair.
            previous_was_spinner = False
            previous_end = finite(row.get("ls.end_time_ms"), clock)
            continue
        if dt <= 0 or finite(raw_dt) <= 0:
            separated = True
            previous_end = finite(row.get("ls.end_time_ms"), clock)
            continue
        # Keep duration and cadence on the real clock, not the legacy strain
        # extractor's minimum-delta floor (which changes elapsed time).
        dt = finite(raw_dt)
        events.append({
            "dt": dt, "time": clock, "break": separated or dt > 1500,
            "radius": finite(row.get("ls.radius_px")),
            "distance": max(0.0, finite(row.get("ls.jump_distance_raw_px"))),
            "angle": finite(row.get("ls.slider_aware_angle_rad"), math.pi),
            "hold": clamp((previous_end - (clock - dt)) / dt),
        })
        previous_end = finite(row.get("ls.end_time_ms"), clock)
        separated = False
    return events


def stamina_measure(events: list[dict]) -> dict:
    """Each candidate binds speed, duration and repetition to the SAME runs.

    A slower interval splits a faster band, rather than donating its length.
    Half-rate recovery may sustain the lower band, never the faster band.
    """
    best = {"value": 0.0, "rate_per_s": 0.0, "notes": 0, "duration_s": 0.0,
            "qualified_time_s": 0.0, "band_per_s": 0.0}
    for threshold in (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 28, 32, 36, 40):
        chains = []
        chain = []
        for event in events:
            if event["break"] or event["dt"] > 1000.0 / threshold * 1.015:
                if len(chain) >= 6:
                    chains.append(chain)
                chain = []
            if event["dt"] <= 1000.0 / threshold * 1.015:
                chain.append(event)
        if len(chain) >= 6:
            chains.append(chain)
        qualified_s = sum(sum(e["dt"] for e in c) for c in chains) / 1000.0
        repetition = 0.80 + 0.20 * (-math.expm1(-qualified_s / 25.0))
        for chain in chains:
            duration = sum(e["dt"] for e in chain) / 1000.0
            notes = len(chain) + 1
            rate = len(chain) / duration
            pressure = (max(0.0, rate - 4.0) / 8.0) ** 1.65
            length = ((notes - 6.0) / (notes + 18.0)) ** 0.65
            sustain = length * (-math.expm1(-duration / 4.0)) ** 0.30
            load = pressure * sustain * repetition
            value = 10.0 * (-math.expm1(-1.20 * load))
            if value > best["value"]:
                best = {"value": value, "rate_per_s": rate, "notes": notes,
                        "duration_s": duration, "qualified_time_s": qualified_s,
                        "band_per_s": threshold, "rate_pressure": pressure,
                        "sustain": sustain, "repetition": repetition,
                        "start_ms": chain[0]["time"] - chain[0]["dt"],
                        "end_ms": chain[-1]["time"]}
    return best


def _local_peak(values: list[tuple[float, float]], window_ms: float = 3000) -> dict:
    """Peak of local top-eight means, with support for isolated single events.

    Easy filler elsewhere cannot dilute the peak. No zero-filled global P90.
    """
    if not values:
        return {"value": 0.0, "peak": 0.0, "median": 0.0, "event_count": 0}
    left = 0
    peak = 0.0
    for right, (time, _) in enumerate(values):
        while values[left][0] < time - window_ms:
            left += 1
        top = sorted((v for _, v in values[left:right + 1]), reverse=True)[:8]
        evidence = 0.65 + 0.35 * min(1.0, len(top) / 6)
        peak = max(peak, statistics.fmean(top) * evidence)
    median = statistics.median(v for _, v in values)
    return {"value": 0.90 * peak + 0.10 * median, "peak": peak,
            "median": median, "event_count": len(values)}


def precision_measure(events: list[dict]) -> dict:
    values = []
    previous_distance = 0.0
    radii = []
    micro_peak = 0.0
    for event in events:
        radius = event["radius"]
        if radius <= 0:
            previous_distance = 0.0
            continue
        if event["break"]:
            previous_distance = 0.0
        distance, dt = event["distance"], event["dt"]
        acquisition = -math.expm1(-distance / 32.0)
        tempo = -math.expm1(-(1000.0 / dt) / 5.0)
        # Pattern evidence uses physical pixels, not shrinking CS-dependent
        # cutoffs. Reducing radius can NEVER remove previously counted demand.
        micro = (clamp((previous_distance - 128.0) / 128.0)
                 / (1.0 + (distance / 40.0) ** 2)
                 * clamp((math.pi / 2.0 - event["angle"]) / (math.pi / 2.0))
                 * (-math.expm1(-150.0 / dt)))
        # No relocation at all is not a high-precision acquisition.
        micro *= acquisition
        target_ratio = REF_RADIUS / radius
        small_bonus = max(1.0, 1.0 + (30.0 - radius) / 70.0)
        target_scale = target_ratio ** 1.65 * math.sqrt(small_bonus)
        value = ((1.05 + 1.65 * tempo) * acquisition + 0.65 * micro) * target_scale
        values.append((event["time"], value))
        radii.append(radius)
        micro_peak = max(micro_peak, micro)
        previous_distance = distance
    result = _local_peak(values)
    result.update(radius_median=statistics.median(radii) if radii else None,
                  micro_peak=micro_peak, total_sr_used=False)
    return result


def _cadence_groups(events: list[dict]) -> list[dict]:
    groups = []
    block = 0
    for event in events:
        if event["break"]:
            block += 1
        if event["dt"] > 1500:
            # A long rest separates phrases; it is not a slow rhythm group.
            continue
        if (groups and groups[-1]["block"] == block
                and abs(math.log2(event["dt"] / groups[-1]["dt"])) <= 0.08):
            g = groups[-1]
            g["count"] += 1
            g["sum_dt"] += event["dt"]
            g["dt"] = g["sum_dt"] / g["count"]
            g["end"] = event["time"]
            g["hold"] = max(g["hold"], event["hold"])
        else:
            groups.append({"dt": event["dt"], "sum_dt": event["dt"], "count": 1,
                           "start": event["time"] - event["dt"], "end": event["time"],
                           "block": block, "hold": event["hold"]})
    return groups


def _motif_repetition(groups: list[dict], index: int) -> float:
    """Recognise repeating cadence-and-group-length motifs, not ratio rarity."""
    neighbourhood = groups[max(0, index - 8):index + 9]
    best = 0.0
    for period in range(2, 7):
        comparisons = []
        for a, b in zip(neighbourhood, neighbourhood[period:]):
            if a["block"] != b["block"]:
                continue
            timing = abs(math.log2(a["dt"] / b["dt"]))
            length = abs(math.log2((a["count"] + 1) / (b["count"] + 1)))
            comparisons.append(math.exp(-timing / 0.10 - length / 0.30))
        if len(comparisons) >= 2 * period:
            best = max(best, statistics.fmean(comparisons))
    return best


def _pulse_predictability(groups: list[dict], index: int) -> float:
    """Evidence of an unchanged local tapping pulse with omitted beats.

    Infer the pulse from observed intervals, not mapper BPM or a whitelist of
    'easy' ratios. Several 1/2/3/4-pulse gaps on the SAME established grid are
    start/stop grouping, not repeatedly learning a new cadence. A 3:2 switch
    is not automatically free: an actual common pulse must be observed and
    supported across the neighbourhood. Residual cost retains group control.
    """
    block = groups[index]["block"]
    neighbourhood = [g for g in groups[max(0, index - 8):index + 9]
                     if g["block"] == block and g["dt"] <= 600]
    if len(neighbourhood) < 6:
        return 0.0
    # Weight groups, not run lengths: one long stream cannot certify unrelated
    # rhythm transitions as ordinary. No invented tiny greatest-common-divisor.
    candidates = [g["dt"] for g in neighbourhood if 25 <= g["dt"] <= 300]
    support = 0.0
    for pulse in candidates:
        matched = sum(abs(g["dt"] - max(1, round(g["dt"] / pulse)) * pulse)
                      <= max(1.5, pulse * .025) for g in neighbourhood)
        support = max(support, matched / len(neighbourhood))
    return .80 * support ** 4


def finger_measure(events: list[dict]) -> dict:
    groups = _cadence_groups(events)
    transitions = []
    previous_fast = None
    baseline = 0.0
    for g in groups:
        speed = (1000.0 / g["dt"] / 10.0) ** 0.65
        baseline = max(baseline, 0.85 * speed * (-math.expm1(-g["count"] / 8)))
    for i in range(1, len(groups)):
        a, b = groups[i - 1], groups[i]
        if a["block"] != b["block"]:
            previous_fast = None
            continue
        contrast = abs(math.log2(a["dt"] / b["dt"]))
        amplitude = -math.expm1(-contrast / 0.45)
        rate = 1000.0 / min(a["dt"], b["dt"])
        speed = (rate / 10.0) ** 0.65
        establishment = -math.expm1(-min(a["count"], b["count"]) / 3.0)
        parity = 0.0
        group_change = 0.0
        if a["dt"] < b["dt"]:
            if previous_fast is not None:
                group_change = clamp(abs(math.log2((a["count"] + 1) / (previous_fast["count"] + 1))))
                parity = float((a["count"] + 1) % 2 != (previous_fast["count"] + 1) % 2)
            previous_fast = a
        pulse_predictability = _pulse_predictability(groups, i)
        predictability = max(_motif_repetition(groups, i), pulse_predictability)
        # Rest provides time to reset. Unlike the old 250ms cutoff it is smooth.
        recovery = 1.0 / (1.0 + (max(a["dt"], b["dt"]) / 450.0) ** 2)
        cost = (speed * (0.25 + 1.05 * amplitude) * (0.65 + 0.35 * establishment)
                * (1.0 + 0.20 * group_change + 0.12 * parity + 0.10 * max(a["hold"], b["hold"]))
                * (1.0 - 0.75 * predictability) * recovery)
        transitions.append({"time": b["start"], "cost": cost, "rate": rate,
                            "predictability": predictability, "parity": parity,
                            "pulse_predictability": pulse_predictability,
                            "previous_notes": a["count"] + 1, "next_notes": b["count"] + 1,
                            "block": b["block"]})
    peak = 0.0
    peak_window = None
    left = 0
    # Window evidence is transition cost per REAL time, not per total map notes.
    for right, transition in enumerate(transitions):
        while (transitions[left]["time"] < transition["time"] - 6000
               or transitions[left]["block"] != transition["block"]):
            left += 1
        window = transitions[left:right + 1]
        duration = max(3.0, (window[-1]["time"] - window[0]["time"]) / 1000.0 + 0.5)
        load = sum(x["cost"] ** 1.30 for x in window) / duration
        value = 3.50 * load ** 0.60
        if value > peak:
            peak = value
            peak_window = {"start_ms": window[0]["time"], "end_ms": window[-1]["time"],
                           "transitions": len(window), "load_per_s": load,
                           "mean_predictability": statistics.fmean(x["predictability"] for x in window),
                           "mean_pulse_predictability": statistics.fmean(x["pulse_predictability"] for x in window)}
    return {"value": peak + min(1.5, baseline), "transition_peak": peak,
            "baseline": min(1.5, baseline), "group_count": len(groups),
            "transition_count": len(transitions), "peak_window": peak_window,
            "parity_changes": sum(t["parity"] for t in transitions),
            "total_sr_used": False}


def extract_components(local_rows: Iterable[dict], features=None, difficulty=None,
                       clock_rate=1.0, effective_mods=()):
    rows = list(local_rows)
    components, warnings = previous.extract_components(rows, features, difficulty, clock_rate, effective_mods)
    events = _events(rows)
    components["beta2_measures"] = {
        "stamina": stamina_measure(events), "spatial_precision": precision_measure(events),
        "finger_control": finger_measure(events),
    }
    return components, warnings


def calibration_id(base_calibration_id: str) -> str:
    return "md010beta2:local_tolerance_cadence_1:" + previous.calibration_id(base_calibration_id)


def analyze_components(**kwargs: Any) -> dict:
    output = previous.analyze_components(**kwargs)
    original_identity = dict(output["identity"])
    output["identity"] = {**original_identity, "algorithm_id": ALGORITHM_ID,
                          "map_demand_version": MAP_DEMAND_VERSION,
                          "calibration_id": calibration_id(str(kwargs["calibration"].get("calibration_id", "")))}
    output["schema_version"] = SCHEMA_VERSION
    output["release"] = {**RELEASE, "known_limitations": list(RELEASE["known_limitations"])}
    output["diagnostics"]["release_basis_identity"] = original_identity
    if output.get("status") == "OK":
        measurements = kwargs["components"].get("beta2_measures")
        if not isinstance(measurements, dict) or any(a not in measurements for a in CHANGED_AXES):
            raise ValueError("beta.2 requires its own local component extraction")
        for axis in CHANGED_AXES:
            measure = measurements[axis]
            value = measure["value"]
            output["axes"][axis].update({
                "status": "EMITTED", "demand_star_equivalent": value, "score": value / 10.0,
                "percentile_rank": None, "method": "LOCAL_TOLERANCE_CADENCE_V1",
                "scale_method": "INDEPENDENT_PHYSICAL_SCALE_NO_TOTAL_SR",
                "evidence": [{"component": "beta2_" + axis, "signals": measure,
                              "evidence_tag": "PUBLIC_BETA2"}],
            })
            output["diagnostics"].get("decoupled_axis_gates", {}).pop(axis, None)
        output["diagnostics"]["beta2_measures"] = measurements
        output["summaries"] = base.v092.derive_summaries(output["axes"])
        anchor = finite(output["diagnostics"].get("v091_star_anchor", {}).get("stars"), 5.0)
        output["archetype"] = base.v095._classify_axes_with_low_demand_abstention(output["axes"], anchor)
    C.scan_finite(output, "model_v010_beta2.output")
    return output
