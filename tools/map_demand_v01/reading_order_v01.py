"""Reading measure based on local order conflict and visual memory.

The measure is published by Map Demand 0.10.0-beta.5.  It remains independent
from total star rating and from the other eight axes so its mechanism can be
reviewed and replayed without hidden cross-axis inputs.
"""
from __future__ import annotations

import bisect
import math
import statistics
from collections import deque

from .local_pattern_geometry import clamp

SUPPORT_EVENTS = 8
MAX_NEIGHBOURS = 48


def _peak(records: list[dict]) -> dict:
    active = deque(maxlen=SUPPORT_EVENTS)
    last_segment = None
    best = dict(value=0.0, start_ms=None, end_ms=None, support_count=0,
                window_event_count=0, signals={})
    for record in records:
        if record["segment"] != last_segment:
            active.clear()
        last_segment = record["segment"]
        active.append(record)
        while active and active[0]["time"] < record["time"] - 3000.0:
            active.popleft()
        value = sum(item["value"] for item in active) / SUPPORT_EVENTS
        if value > best["value"]:
            best = dict(value=value, start_ms=active[0]["time"],
                        end_ms=active[-1]["time"],
                        support_count=sum(item["value"] > 0 for item in active),
                        window_event_count=len(active),
                        signals={key: statistics.fmean(item["signals"][key]
                                                       for item in active)
                                 for key in active[0]["signals"]})
    best.update(event_count=len(records), total_sr_used=False,
                scale="INDEPENDENT_LOCAL_ORDER_MEMORY_LOG_SCALE",
                aggregation="EIGHT_CONSECUTIVE_DECISIONS_WITHIN_THREE_SECONDS")
    return best


def _path_lengths(objects: list[dict]) -> list[float]:
    lengths = [0.0] * len(objects)
    for index in range(1, len(objects)):
        if objects[index]["segment"] == objects[index - 1]["segment"]:
            lengths[index] = lengths[index - 1] + objects[index]["head_distance"]
    return lengths


def reading_measure(objects: list[dict], novelty: list[float], mods=()) -> dict:
    """Measure local ordering conflict, relative visibility and HD memory.

    Merely packing many adjacent heads into a small area is not Reading.  The
    score rises when non-adjacent order folds back onto itself, when the visible
    sequence is locally unpredictable, or when HD makes unresolved conflicting
    heads depend on memory.  Preempt affects which objects coexist rather than
    contributing a standalone AR bonus.
    """
    if len(objects) != len(novelty):
        raise ValueError("Reading requires one predictability value per object")
    if not objects:
        return _peak([])

    hidden = "HD" in {str(mod).upper() for mod in mods}
    times = [obj["time"] for obj in objects]
    path_lengths = _path_lengths(objects)
    records = []
    sustained_ms = 0.0
    truncated = 0

    for index, obj in enumerate(objects):
        if obj["dt"] <= 0:
            sustained_ms = 0.0
            continue

        preempt = obj["preempt"]
        # Sample while the target is still readable, not at hit time.  Longer
        # preempt naturally exposes more future order without an AR score bonus.
        decision = obj["time"] - .42 * preempt
        first = bisect.bisect_left(times, decision)
        last = bisect.bisect_right(times, decision + preempt)
        if last - first > MAX_NEIGHBOURS:
            truncated += 1
            first = max(first, index - MAX_NEIGHBOURS // 2)
            last = min(last, first + MAX_NEIGHBOURS)

        visible_heads = 0.0
        order_conflict = 0.0
        remembered_conflict = 0.0
        scene_novelty = 0.0
        scene_weight = 0.0
        target_radius = obj["radius"]

        for other_index in range(first, last):
            if other_index == index:
                continue
            other = objects[other_index]
            if other["segment"] != obj["segment"]:
                continue
            appearance = other["time"] - other["preempt"]
            if appearance > decision or other["time"] < decision:
                continue

            separation = abs(other_index - index)
            radius = (target_radius + other["radius"]) * .5
            distance = math.hypot(other["x"] - obj["x"], other["y"] - obj["y"])
            proximity = math.exp(-((distance / max(3.0 * radius, 1.0)) ** 2))
            visible_heads += 1.0

            recency = 1.0 / math.sqrt(max(1, separation))
            local_novelty = max(novelty[index], novelty[other_index])
            scene_novelty += recency * local_novelty
            scene_weight += recency

            # Consecutive touching heads state the immediate path and are not
            # ambiguous by themselves.  Non-adjacent spatial returns can hide
            # which object comes next even when the raw density is identical.
            fold = 0.0
            if separation > 1:
                path = abs(path_lengths[other_index] - path_lengths[index])
                if path > radius:
                    fold = clamp(1.0 - distance / path)
                order_conflict += proximity * fold * recency

            if hidden:
                vanish = other["time"] - .30 * other["preempt"]
                if decision >= vanish:
                    # Memory only becomes difficult when the vanished head is
                    # part of a nonlocal fold or a surprising local order.  A
                    # sparse straight line therefore receives almost no HD tax.
                    remembered_conflict += proximity * recency * max(fold, .35 * local_novelty)

        novelty_mean = scene_novelty / scene_weight if scene_weight else novelty[index]
        surprise = clamp(.65 * novelty[index] + .35 * novelty_mean)
        fold_load = math.log2(1.0 + order_conflict)
        memory_load = math.log2(1.0 + remembered_conflict)

        # Visible count matters only to the extent that its order is not already
        # learnable.  This is the key relief for regular close streams/stacks.
        visible_order = math.log2(1.0 + visible_heads) * surprise
        conflict = fold_load * (.30 + .70 * surprise)
        # Ordinary simultaneous heads are weak evidence.  The same local order
        # becomes materially harder at either end: a long preempt requires the
        # player to retain a larger pending sequence, while a very short object
        # interval requires that sequence to be decoded unusually quickly.
        information_rate = clamp((300.0 - obj["dt"]) / 180.0)
        retention = (visible_order * clamp((preempt - 500.0) / 500.0)
                     * information_rate)
        rapid_gate = clamp((105.0 - obj["dt"]) / 45.0) ** 2
        # Very fast compact streams primarily test Flow/Tapping.  Rapid visual
        # decoding becomes Reading only when each decision also relocates the
        # target by a meaningful amount relative to the circle size.
        recent = [objects[k]["distance"] for k in range(max(0, index - 2), index + 1)
                  if objects[k]["segment"] == obj["segment"] and objects[k]["dt"] > 0]
        relocation_distance = statistics.fmean(recent) if recent else obj["distance"]
        relocation = clamp((relocation_distance / max(obj["radius"], 1.0) - .70) / 1.30)
        # Medium-speed wide aim is partly cursor placement even when the next
        # direction changes.  Give that common jump shape a small smooth relief;
        # extreme-speed decoding and low-AR retention stay separate.
        reading_protection = max(clamp(fold_load / .50), clamp(retention))
        aim_read_relief = (.20 * clamp((obj["dt"] - 85.0) / 65.0) * relocation
                           * (1.0 - reading_protection))
        ordinary_order = visible_order * (1.0 - aim_read_relief)
        rapid_decode = visible_order * rapid_gate * relocation * (1.0 - aim_read_relief)
        # Long-horizon retention and rapid decoding are two explanations for
        # the same pending order, not two independent piles of difficulty.
        order_extreme = max(.55 * retention, 1.60 * rapid_decode)
        local_pressure = 1.15 * conflict + .34 * ordinary_order + order_extreme
        if hidden:
            local_pressure += 1.05 * memory_load * (.25 + .75 * surprise)

        if local_pressure > .55:
            sustained_ms = min(5000.0, sustained_ms + min(obj["dt"], 500.0))
        else:
            sustained_ms = max(0.0, sustained_ms - 2.0 * min(obj["dt"], 500.0))
        sustained = 1.0 + .28 * (-math.expm1(-sustained_ms / 1200.0))

        # A very short response window matters only when there is actual order
        # evidence.  High AR alone cannot create a high Reading value.
        response = clamp((450.0 - preempt) / 225.0) * surprise * min(1.0, local_pressure)
        pressure = local_pressure * sustained + .35 * response
        value = 4.05 * math.log2(1.0 + pressure)
        records.append(dict(time=obj["time"], segment=obj["segment"], value=value,
                            signals=dict(visible_heads=visible_heads,
                                         order_conflict=order_conflict,
                                         remembered_conflict=remembered_conflict,
                                         novelty=surprise, fold_load=fold_load,
                                         visible_order=visible_order,
                                         ordinary_order=ordinary_order,
                                         information_rate=information_rate,
                                         retention_order=retention,
                                         relocation_distance=relocation_distance,
                                         relocation=relocation,
                                         reading_protection=reading_protection,
                                         aim_read_relief=aim_read_relief,
                                         rapid_decode=rapid_decode,
                                         order_extreme=order_extreme,
                                         memory_load=memory_load,
                                         local_pressure=local_pressure,
                                         sustained_multiplier=sustained,
                                         high_ar_response=response,
                                         preempt_ms=preempt)))

    result = _peak(records)
    result.update(visibility="LOCAL_HEAD_ORDER_AND_HD_UNRESOLVED_MEMORY",
                  neighbourhood_truncated_events=truncated)
    return result
