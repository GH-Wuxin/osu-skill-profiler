"""Published Aim Control execution-time calculator, without experiment wrappers."""
from __future__ import annotations

import math
import statistics
from collections import deque

from .local_pattern_geometry import clamp

EXECUTION_REFERENCE_MS = 100.0
MIN_EXECUTION_MS = 25.0
EXECUTION_POWER = 1.5
SUPPORT_EVENTS = 8


def control_peak(records: list[dict]) -> dict:
    active = deque(maxlen=SUPPORT_EVENTS)
    last_segment = None
    best = dict(value=0.0, start_ms=None, end_ms=None, support_count=0,
                window_event_count=0, signals={})
    for record in records:
        if record["segment"] != last_segment:
            active.clear()
        last_segment = record["segment"]
        active.append(record)
        while active and active[0]["time"] < record["time"] - 3000:
            active.popleft()
        value = sum(item["value"] for item in active) / SUPPORT_EVENTS
        if value > best["value"]:
            best = dict(value=value, start_ms=active[0]["time"], end_ms=active[-1]["time"],
                        support_count=sum(item["value"] > 0 for item in active),
                        window_event_count=len(active),
                        signals={key: statistics.fmean(item["signals"][key] for item in active)
                                 for key in active[0]["signals"]})
    best.update(event_count=len(records), total_sr_used=False,
                scale="INDEPENDENT_LOCAL_MECHANISM_LOG_SCALE",
                aggregation="EIGHT_CONSECUTIVE_TRANSITIONS_WITHIN_THREE_SECONDS")
    return best


def execution_terms(a: dict, b: dict) -> dict:
    available = (max(MIN_EXECUTION_MS, a["free_time"])
                 + max(MIN_EXECUTION_MS, b["free_time"])) * .5
    return dict(execution_time_ms=available,
                execution_multiplier=(EXECUTION_REFERENCE_MS/available)**EXECUTION_POWER,
                tempo=(200.0/available)**.5)


def control_measure(objects: list[dict], novelty: list[float]) -> dict:
    records = []
    for i in range(2, len(objects)):
        a, b = objects[i-1], objects[i]
        if objects[i-2]["segment"] != b["segment"] or b["dt"] <= 0 or a["dt"] <= 0:
            continue
        va, vb = a["distance"]/a["free_time"], b["distance"]/b["free_time"]
        cadence = abs(math.log2(b["dt"]/a["dt"]))
        spacing = abs(math.log2((b["distance"]+24)/(a["distance"]+24)))
        stable_spacing = spacing * math.exp(-2.6*cadence)
        motion_pair = -math.expm1(-(min(a["distance"], b["distance"])/16.0)**2)
        speed = abs(vb-va)/(.60+.50*(va+vb))
        turn_change = abs(b["turn"]-a["turn"])
        change = max(0.0, max(min(stable_spacing, 2.0), speed, 1.20*turn_change)-.10)*motion_pair
        release = 0.0
        if a["kind"] == "slider" and a["slider_speed"] > 0:
            hold = clamp((a["end"]-a["time"])/b["dt"])
            release = (hold*abs(vb-a["slider_speed"])/(.60+.50*(vb+a["slider_speed"]))
                       * -math.expm1(-(b["distance"]/16.0)**2))
        familiarity = .90+.10*novelty[i]
        corrective = max(change, max(0.0, release-.10))*familiarity
        timing = execution_terms(a, b)
        movement = .65+.35*b["distance"]/(b["distance"]+80.0)
        geometric_effort = corrective*(.75+.55*corrective)
        effort = geometric_effort*timing["execution_multiplier"]
        value = 3.8*math.log2(1.0+2.0*effort*timing["tempo"]*movement)
        records.append(dict(time=b["time"], segment=b["segment"], value=value,
                            signals=dict(stable_spacing=stable_spacing, speed_change=speed,
                                         turn_change=turn_change, slider_release=release,
                                         novelty=novelty[i], familiarity_multiplier=familiarity,
                                         motion_pair=motion_pair, corrective=corrective,
                                         geometric_effort=geometric_effort, effort=effort, **timing)))
    result = control_peak(records)
    result["timing_model"] = "PAIR_AVAILABLE_TIME_INVERSE_SQUARE_EFFORT"
    return result
