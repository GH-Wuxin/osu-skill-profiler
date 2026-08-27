"""Deterministic first-pass map-type proposals for the human annotation UI.

This is deliberately a review aid, not a trained classifier.  It turns
observable object timing/geometry into editable Jump/Stream/Alt/Tech/Gimmick
proposals and preserves the underlying evidence for human correction.
"""

from __future__ import annotations

import math
from collections import Counter
from statistics import median
from typing import Any, Iterable


CLASSIFIER_VERSION = "map_type_proposal_v0.1.1-experimental"
TYPE_ORDER = ("JUMP", "STREAM", "ALT", "TECH", "GIMMICK")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _finite(values: Iterable[Any]) -> list[float]:
    result: list[float] = []
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            result.append(float(value))
    return result


def _quantile(values: Iterable[Any], q: float, default: float = 0.0) -> float:
    ordered = sorted(_finite(values))
    if not ordered:
        return default
    if len(ordered) == 1:
        return ordered[0]
    position = _clamp(q) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _cv(values: Iterable[Any]) -> float:
    rows = _finite(values)
    if len(rows) < 2:
        return 0.0
    center = sum(rows) / len(rows)
    if abs(center) < 1e-9:
        return 0.0
    variance = sum((item - center) ** 2 for item in rows) / len(rows)
    return _clamp(math.sqrt(variance) / abs(center), 0.0, 2.0)


def _longest_true_run(flags: Iterable[bool]) -> int:
    longest = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest


def _median(values: Iterable[Any], default: float = 0.0) -> float:
    rows = _finite(values)
    return float(median(rows)) if rows else default


def suggest_sections(objects: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Propose conservative editable phrases for both API and review UI use."""

    if not objects:
        return []
    split_indices = [0]
    last_split = 0
    for index in range(1, len(objects)):
        current = objects[index]
        previous = objects[index - 1]
        recent = objects[max(last_split + 1, index - 6) : index]
        recent_deltas = [
            float(item.delta_time_ms)
            for item in recent
            if item.delta_time_ms and item.delta_time_ms > 0
        ]
        baseline_delta = _median(recent_deltas, 500.0)
        gap = max(0.0, float(current.time_ms - previous.canonical_end_time_ms()))
        count = index - last_split
        duration = current.time_ms - objects[last_split].time_ms
        pause_split = count >= 4 and gap >= max(900.0, baseline_delta * 3.5)
        cap_split = count >= 36 and duration >= 20000.0
        change_split = False
        if count >= 18 and duration >= 8000.0 and index + 6 < len(objects):
            before = objects[max(last_split, index - 7) : index]
            after = objects[index : index + 7]
            before_delta = _median(
                (
                    float(item.delta_time_ms)
                    for item in before
                    if item.delta_time_ms and item.delta_time_ms > 0
                ),
                baseline_delta,
            )
            after_delta = _median(
                (
                    float(item.delta_time_ms)
                    for item in after
                    if item.delta_time_ms and item.delta_time_ms > 0
                ),
                before_delta,
            )
            before_distance = _median(
                float(item.distance_from_previous)
                for item in before
                if item.distance_from_previous is not None
            )
            after_distance = _median(
                float(item.distance_from_previous)
                for item in after
                if item.distance_from_previous is not None
            )
            before_sliders = sum(item.raw.object_type == "slider" for item in before) / len(before)
            after_sliders = sum(item.raw.object_type == "slider" for item in after) / len(after)
            tempo_ratio = max(before_delta, after_delta) / max(
                1.0, min(before_delta, after_delta)
            )
            change_split = (
                (tempo_ratio >= 2.6 and abs(before_delta - after_delta) >= 120.0)
                or abs(before_distance - after_distance) >= 0.36
                or abs(before_sliders - after_sliders) >= 0.82
            )
        if pause_split or cap_split or change_split:
            split_indices.append(index)
            last_split = index
    split_indices.append(len(objects))

    raw_sections: list[tuple[int, int]] = []
    for start, end in zip(split_indices, split_indices[1:]):
        if raw_sections and end - start < 4:
            prior_start, _ = raw_sections[-1]
            raw_sections[-1] = (prior_start, end)
        else:
            raw_sections.append((start, end))

    sections: list[dict[str, Any]] = []
    for number, (start, end) in enumerate(raw_sections, start=1):
        rows = objects[start:end]
        start_ms = float(rows[0].time_ms)
        end_ms = float(max(item.canonical_end_time_ms() for item in rows))
        deltas = [
            float(item.delta_time_ms)
            for item in rows
            if item.delta_time_ms and item.delta_time_ms > 0
        ]
        distances = [
            float(item.distance_from_previous)
            for item in rows
            if item.distance_from_previous is not None
        ]
        type_counts = Counter(item.raw.object_type for item in rows)
        sections.append(
            {
                "section_id": f"s{number}",
                "start_ms": round(start_ms, 3),
                "end_ms": round(end_ms, 3),
                "object_start": start,
                "object_end": end,
                "stats": {
                    "objects": len(rows),
                    "circles": type_counts["circle"],
                    "sliders": type_counts["slider"],
                    "spinners": type_counts["spinner"],
                    "median_delta_ms": round(_median(deltas), 3),
                    "median_distance": round(_median(distances), 4),
                    "duration_ms": round(max(0.0, end_ms - start_ms), 3),
                },
            }
        )
    return sections


def _rhythm_novelty(deltas: list[float]) -> float:
    if len(deltas) < 4:
        return 0.0
    common = (0.5, 2.0 / 3.0, 0.75, 1.0, 4.0 / 3.0, 1.5, 2.0, 3.0)
    novelty: list[float] = []
    for left, right in zip(deltas, deltas[1:]):
        if left <= 0 or right <= 0:
            continue
        ratio = right / left
        distance = min(abs(math.log(ratio / candidate)) for candidate in common)
        novelty.append(_clamp(distance / math.log(1.25)))
    return _quantile(novelty, 0.75)


def _rhythm_family(delta_ms: float, bpm: float) -> str | None:
    """Return the editor snap family, not merely a faster/slower interval."""

    if delta_ms <= 0.0 or bpm <= 0.0 or not math.isfinite(bpm):
        return None
    beat_ms = 60000.0 / bpm
    ratio = delta_ms / beat_ms
    candidates = {
        "BINARY": (1.0, 0.5, 0.25, 0.125),
        "TERNARY": (1.0 / 3.0, 1.0 / 6.0, 1.0 / 12.0),
    }
    best_family: str | None = None
    best_error = math.inf
    for family, snaps in candidates.items():
        for snap in snaps:
            error = abs(math.log(max(ratio, 1e-9) / snap))
            if error < best_error:
                best_error = error
                best_family = family
    return best_family if best_error <= math.log(1.13) else None


def _rhythm_family_switch_count(rows: tuple[Any, ...]) -> int:
    families = [
        _rhythm_family(float(item.delta_time_ms), float(item.local_bpm))
        if item.delta_time_ms is not None
        else None
        for item in rows
    ]
    count = 0
    # A single quantisation wobble is not a speed change. Require two stable
    # intervals on both sides of a binary <-> ternary snap-family transition.
    for index in range(2, len(families) - 1):
        left = families[index - 2 : index]
        right = families[index : index + 2]
        if left[0] is not None and left[0] == left[1] and right[0] is not None and right[0] == right[1] and left[0] != right[0]:
            count += 1
    return count


def _bpm_change_count(rows: tuple[Any, ...]) -> int:
    bpms = _finite(item.local_bpm for item in rows)
    return sum(
        1
        for left, right in zip(bpms, bpms[1:])
        if min(left, right) > 0.0 and max(left, right) / min(left, right) >= 1.035
    )


def _spacing_change_count(rows: tuple[Any, ...]) -> int:
    distances = [item.distance_from_previous for item in rows]
    deltas = [item.delta_time_ms for item in rows]
    events: list[int] = []
    for index in range(4, len(rows) - 3):
        left = _finite(distances[index - 3 : index])
        right = _finite(distances[index : index + 3])
        left_dt = _finite(deltas[index - 3 : index])
        right_dt = _finite(deltas[index : index + 3])
        if min(len(left), len(right), len(left_dt), len(right_dt)) < 3:
            continue
        left_center = median(left)
        right_center = median(right)
        if min(left_center, right_center) < 0.045:
            continue
        # Keep cadence and object family stable; otherwise this is a normal
        # transition between, for example, singlet jumps and a stream.
        cadence_ratio = max(median(left_dt), median(right_dt)) / max(1.0, min(median(left_dt), median(right_dt)))
        same_objects = all(item.raw.object_type == "circle" for item in rows[index - 3 : index + 3])
        spacing_ratio = max(left_center, right_center) / min(left_center, right_center)
        if cadence_ratio <= 1.14 and same_objects and spacing_ratio >= 1.85 and _cv(left) <= 0.24 and _cv(right) <= 0.24:
            if not events or index - events[-1] >= 4:
                events.append(index)
    return len(events)


def _separation_count(rows: tuple[Any, ...]) -> int:
    distances = [item.distance_from_previous for item in rows]
    count = 0
    for index in range(3, len(rows) - 1):
        local_values = _finite(distances[index - 3 : index])
        spike_values = _finite(distances[index : index + 2])
        local_deltas = _finite(item.delta_time_ms for item in rows[index - 3 : index + 2])
        if len(local_values) < 3 or len(spike_values) < 2 or len(local_deltas) < 4:
            continue
        local = median(local_values)
        spike, following = spike_values
        compact_fast_chain = local <= 0.30 and median(local_deltas) <= 170.0
        circle_chain = all(item.raw.object_type == "circle" for item in rows[index - 3 : index + 2])
        if compact_fast_chain and circle_chain and spike >= max(0.30, local * 2.60) and following <= max(0.17, spike * 0.54):
            count += 1
    return count


def _non_adjacent_overlap(rows: tuple[Any, ...], difficulty: dict[str, Any]) -> tuple[int, float]:
    """Conservatively count near-exact non-adjacent positional reuse.

    Adjacent stream spacing is deliberately excluded. Slider-path crossings
    need a future geometry-aware detector and are not guessed here.
    """

    cs = float(difficulty.get("CircleSize", 5.0))
    radius_px = max(4.0, 54.4 - 4.48 * cs)
    ar = float(difficulty.get("ApproachRate", difficulty.get("OverallDifficulty", 5.0)))
    preempt_ms = 1200.0 - 120.0 * ar if ar <= 5.0 else 1200.0 - 150.0 * (ar - 5.0)
    events = 0
    eligible = 0
    for right in range(2, len(rows)):
        current = rows[right]
        if current.raw.object_type == "spinner":
            continue
        for left in range(max(0, right - 8), right - 1):
            previous = rows[left]
            age = float(current.time_ms - previous.time_ms)
            if age <= 0.0 or age > preempt_ms:
                continue
            eligible += 1
            dx = (float(current.x_norm) - float(previous.x_norm)) * 512.0
            dy = (float(current.y_norm) - float(previous.y_norm)) * 384.0
            if math.hypot(dx, dy) <= radius_px * 0.62:
                events += 1
    return events, events / max(1, eligible)


def _section_features(rows: tuple[Any, ...], difficulty: dict[str, Any], effective_mods: tuple[str, ...]) -> dict[str, Any]:
    count = len(rows)
    duration_ms = max(1.0, float(rows[-1].canonical_end_time_ms() - rows[0].time_ms)) if rows else 1.0
    deltas = _finite(item.delta_time_ms for item in rows if item.delta_time_ms is not None and item.delta_time_ms > 0)
    distances = _finite(item.distance_from_previous for item in rows if item.distance_from_previous is not None)
    velocities = _finite(item.movement_velocity_norm_per_s for item in rows if item.movement_velocity_norm_per_s is not None)
    angles = _finite(item.angle_deg for item in rows if item.angle_deg is not None)
    angle_changes = [abs(right - left) for left, right in zip(angles, angles[1:])]
    slider_rows = [item for item in rows if item.raw.object_type == "slider"]
    circle_count = sum(item.raw.object_type == "circle" for item in rows)
    slider_ratio = len(slider_rows) / max(1, count)
    circle_ratio = circle_count / max(1, count)
    delta_p25 = _quantile(deltas, 0.25, 1000.0)
    delta_p50 = _quantile(deltas, 0.50, 1000.0)
    distance_p50 = _quantile(distances, 0.50)
    distance_p75 = _quantile(distances, 0.75)
    distance_p90 = _quantile(distances, 0.90)
    velocity_p90 = _quantile(velocities, 0.90)
    fast_flags = [
        bool(item.delta_time_ms is not None and 25.0 <= item.delta_time_ms <= 125.0 and item.raw.object_type == "circle")
        for item in rows
    ]
    fast_share = sum(fast_flags) / max(1, count)
    longest_fast_chain = _longest_true_run(fast_flags)
    large_jump_share = sum(distance >= 0.28 for distance in distances) / max(1, len(distances))
    spacing_cv = _cv(distances)
    delta_cv = _cv(deltas)
    angle_change = _clamp(_quantile(angle_changes, 0.80) / 95.0)
    irregularity = _clamp(0.42 * angle_change + 0.36 * _clamp(spacing_cv / 0.8) + 0.22 * _clamp(delta_cv / 0.7))
    repeat_share = sum((item.slider_repeat_count or 0) > 0 for item in slider_rows) / max(1, len(slider_rows))
    slider_lengths = _finite(item.raw.slider_pixel_length for item in slider_rows if item.raw.slider_pixel_length is not None)
    slider_velocities = _finite(item.slider_velocity_px_per_s for item in slider_rows if item.slider_velocity_px_per_s is not None)
    slider_length = _clamp(_quantile(slider_lengths, 0.75) / 320.0)
    slider_speed = _clamp((_quantile(slider_velocities, 0.75) - 220.0) / 520.0)
    sv_cv = _cv(item.local_sv for item in slider_rows)
    slider_complexity = _clamp(0.34 * repeat_share + 0.30 * slider_length + 0.22 * _clamp(sv_cv / 0.65) + 0.14 * angle_change)
    density_values = _finite(item.local_density_per_s for item in rows)
    density_center = _quantile(density_values, 0.50, 0.0)
    density_peak_ratio = _quantile(density_values, 0.90, 0.0) / max(0.5, density_center)
    separation_count = _separation_count(rows)
    spacing_change_count = _spacing_change_count(rows)
    rhythm_switch_count = _rhythm_family_switch_count(rows)
    bpm_change_count = _bpm_change_count(rows)
    overlap_count, overlap_share = _non_adjacent_overlap(rows, difficulty)
    rhythm_novelty = _rhythm_novelty(deltas)
    object_rate = count / max(0.5, duration_ms / 1000.0)

    cadence = _clamp(1.0 - abs(delta_p50 - 175.0) / 130.0)
    medium_spacing = _clamp(1.0 - abs(distance_p75 - 0.30) / 0.28)
    jump_regularity = 1.0 - _clamp(0.58 * spacing_cv + 0.42 * delta_cv)
    fastness = _clamp((155.0 - delta_p50) / 85.0)
    stream_chain = _clamp((longest_fast_chain - 4.0) / 14.0)
    compact_flow = 1.0 - _clamp((distance_p75 - 0.38) / 0.28)

    jump = _clamp(
        0.28 * _clamp((distance_p75 - 0.14) / 0.42)
        + 0.22 * large_jump_share
        + 0.20 * _clamp(velocity_p90 / 3.8)
        + 0.16 * jump_regularity
        + 0.14 * circle_ratio
    )
    jump *= 1.0 - 0.38 * slider_ratio
    jump *= 1.0 - 0.22 * stream_chain

    stream = _clamp(
        0.28 * fast_share
        + 0.30 * stream_chain
        + 0.16 * fastness
        + 0.12 * compact_flow
        + 0.14 * circle_ratio
    )
    if longest_fast_chain < 5:
        stream *= 0.52

    alt = _clamp(
        0.24 * cadence
        + 0.20 * medium_spacing
        + 0.31 * irregularity
        + 0.15 * circle_ratio
        + 0.10 * _clamp(delta_cv / 0.55)
    )
    alt *= 1.0 - 0.46 * slider_ratio
    alt *= 1.0 - 0.30 * stream_chain
    if large_jump_share >= 0.68:
        alt *= 0.74

    slider_foundation = _clamp((slider_ratio - 0.10) / 0.58)
    slider_action_gate = _clamp(0.68 * slider_speed + 0.32 * max(repeat_share, _clamp(sv_cv / 0.65)))
    tech = _clamp(
        (0.43 * slider_foundation + 0.25 * slider_complexity + 0.22 * irregularity + 0.10 * _clamp(velocity_p90 / 3.6))
        * (0.42 + 0.58 * slider_foundation)
        * (0.42 + 0.58 * slider_action_gate)
    )

    pressure = _clamp(
        0.18 * _clamp(object_rate / 7.0)
        + 0.22 * _clamp(velocity_p90 / 4.5)
        + 0.18 * _clamp(distance_p90 / 0.65)
        + 0.16 * fast_share
        + 0.14 * irregularity
        + 0.12 * slider_complexity
    )
    ar = float(difficulty.get("ApproachRate", difficulty.get("OverallDifficulty", 5.0)))
    expected_ar = 7.6 + 2.7 * pressure
    raw_low_ar = _clamp((expected_ar - ar - 0.35) / 1.65)
    object_activity = _clamp((object_rate - 0.75) / 2.25)
    movement_activity = _clamp((velocity_p90 - 0.75) / 2.75) * _clamp(
        (object_rate - 0.35) / 1.25
    )
    low_ar_activity = max(object_activity, movement_activity)
    low_ar = raw_low_ar * low_ar_activity
    raw_odd_rhythm = _clamp((rhythm_novelty - 0.16) / 0.55) * _clamp(
        (delta_cv - 0.14) / 0.70
    )
    odd_rhythm = raw_odd_rhythm * low_ar_activity
    # The first experimental overlap detector still confused regular stacked
    # triples and recurring pattern positions with reading gimmicks. Preserve
    # the diagnostic counts, but abstain from proposing OVERLAP until a
    # pattern-novelty/slider-path-aware detector exists. False negatives are
    # preferable to turning ordinary streams and jumps into Gimmick maps.
    overlap = 0.0
    ez_reading = (
        _clamp(0.38 + 0.62 * pressure) * low_ar_activity
        if "EZ" in effective_mods and pressure >= 0.20
        else 0.0
    )
    slider_reading = raw_low_ar * tech * max(low_ar_activity, slider_action_gate)
    gimmick_components = {
        "LOW_AR_READING": low_ar,
        "ODD_RHYTHM": odd_rhythm,
        "OVERLAP": overlap,
        "SLIDER_TECH": slider_reading,
        "EZ_READING": ez_reading,
    }
    gimmick_subtype, gimmick = max(gimmick_components.items(), key=lambda item: (item[1], item[0]))
    # EZ is reported explicitly because it changes the visibility mechanic;
    # the structural Jump/Stream/Alt/Tech proposal is still retained beside it.
    if ez_reading >= 0.32:
        gimmick_subtype = "EZ_READING"
        gimmick = max(gimmick, ez_reading)
    gimmick = _clamp(gimmick)

    scores = {"JUMP": jump, "STREAM": stream, "ALT": alt, "TECH": tech, "GIMMICK": gimmick}
    tags: list[str] = []
    relative_burst_bpm = 15000.0 / max(delta_p25, 25.0)
    burst_threshold_bpm = 190.0 + 55.0 * pressure
    if 6 <= longest_fast_chain <= 16 and fast_share >= 0.12 and relative_burst_bpm >= burst_threshold_bpm:
        tags.append("BURST_HEAVY")
    if tech >= 0.48 and slider_ratio >= 0.20 and slider_action_gate >= 0.35:
        tags.append("SLIDER_TECH")
    if rhythm_switch_count > 0 or bpm_change_count > 0:
        tags.append("SPEED_CHANGE")
    if angle_change >= 0.48:
        tags.append("ANGLE_CHANGE")
    if spacing_change_count > 0:
        tags.append("SPACING_CHANGE")
    if separation_count >= max(2, round(count * 0.025)):
        tags.append("SEPARATION")
    if density_peak_ratio >= 1.55 and _cv(density_values) >= 0.32:
        tags.append("DENSITY_SPIKE")

    evidence = {
        "JUMP": f"大间距移动占比 {large_jump_share:.0%}，移动距离 P75={distance_p75:.2f}",
        "STREAM": f"快速连续链最长 {longest_fast_chain} 个，快速物件占比 {fast_share:.0%}",
        "ALT": f"中速移动与变角/变距不规则度 {irregularity:.2f}",
        "TECH": f"滑条占比 {slider_ratio:.0%}，滑条结构复杂度 {slider_complexity:.2f}",
        "GIMMICK": {
            "LOW_AR_READING": f"AR {ar:.1f} 低于该段压力对应的可读性环境",
            "ODD_RHYTHM": f"非常规节奏指数 {rhythm_novelty:.2f}",
            "OVERLAP": f"检测到 {overlap_count} 次非相邻物件近似叠位",
            "SLIDER_TECH": "低 AR 与 Slider Tech 结构叠加",
            "EZ_READING": "EZ 改变可见时间，同时保留谱面原有结构",
        }[gimmick_subtype],
    }
    return {
        "count": count,
        "duration_ms": duration_ms,
        "pressure": pressure,
        "scores": scores,
        "tags": tags,
        "gimmick_subtype": gimmick_subtype if gimmick >= 0.32 else None,
        "evidence": evidence,
        "metrics": {
            "object_rate": object_rate,
            "delta_p50": delta_p50,
            "distance_p75": distance_p75,
            "longest_fast_chain": longest_fast_chain,
            "slider_ratio": slider_ratio,
            "irregularity": irregularity,
            "overlap_share": overlap_share,
            "overlap_count": overlap_count,
            "rhythm_family_switch_count": rhythm_switch_count,
            "bpm_change_count": bpm_change_count,
            "spacing_change_count": spacing_change_count,
            "separation_count": separation_count,
            "slider_action_gate": slider_action_gate,
            "rhythm_novelty": rhythm_novelty,
            "raw_low_ar": raw_low_ar,
            "low_ar_activity": low_ar_activity,
            "raw_odd_rhythm": raw_odd_rhythm,
        },
    }


def _proposal_from_features(features: dict[str, Any]) -> dict[str, Any]:
    ranking = sorted(features["scores"].items(), key=lambda item: (-item[1], TYPE_ORDER.index(item[0])))
    primary, top = ranking[0]
    if features["count"] < 4 or top < 0.34:
        return {
            "status": "ABSTAINED",
            "primary_type": "NONE",
            "secondary_types": [],
            "gimmick_subtype": None,
            "structural_tags": list(features["tags"]),
            "evidence": ["这一段的结构证据不足，等待人工判断"],
            "scores": {key: round(value, 4) for key, value in features["scores"].items()},
            "pressure": round(features["pressure"], 4),
        }
    threshold = max(0.34, top * 0.66)
    secondary = [name for name, score in ranking[1:] if score >= threshold][:3]
    has_gimmick = primary == "GIMMICK" or "GIMMICK" in secondary
    if has_gimmick and features["gimmick_subtype"] is None:
        secondary = [name for name in secondary if name != "GIMMICK"]
        if primary == "GIMMICK":
            primary, top = next((name, score) for name, score in ranking if name != "GIMMICK")
    selected = [primary, *secondary]
    return {
        "status": "PROPOSED",
        "primary_type": primary,
        "secondary_types": secondary,
        "gimmick_subtype": features["gimmick_subtype"] if "GIMMICK" in selected else None,
        "structural_tags": list(features["tags"]),
        "evidence": [features["evidence"][name] for name in selected[:3]],
        "scores": {key: round(value, 4) for key, value in features["scores"].items()},
        "pressure": round(features["pressure"], 4),
    }


def propose_type_annotations(
    objects: tuple[Any, ...],
    sections: list[dict[str, Any]],
    difficulty: dict[str, Any],
    effective_mods: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach editable machine proposals and build an independent map summary."""

    mods = tuple(str(item).upper() for item in effective_mods)
    features: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    for section in sections:
        rows = objects[int(section["object_start"]) : int(section["object_end"])]
        item = _section_features(rows, difficulty, mods)
        features.append(item)
        proposals.append(_proposal_from_features(item))

    pressures = [item["pressure"] for item in features]
    ordered_pressure = sorted(pressures, reverse=True)
    maximum = ordered_pressure[0] if ordered_pressure else 0.0
    second = ordered_pressure[1] if len(ordered_pressure) > 1 else 0.0
    center = _quantile(pressures, 0.50)
    upper = _quantile(pressures, 0.75)
    decisive_index = None
    if pressures and maximum >= 0.42 and maximum >= second * 1.22 and maximum >= center * 1.30:
        decisive_index = pressures.index(maximum)
    for index, (section, proposal, item) in enumerate(zip(sections, proposals, features)):
        pressure = item["pressure"]
        if index == decisive_index:
            contribution = "DECISIVE"
        elif maximum > 0 and (pressure >= upper and pressure >= maximum * 0.72):
            contribution = "MAJOR"
        elif maximum > 0 and pressure <= maximum * 0.42:
            contribution = "SETUP"
        else:
            contribution = "NORMAL"
        proposal["contribution"] = contribution
        if contribution in {"MAJOR", "DECISIVE"} and "DIFFICULTY_SPIKE" not in proposal["structural_tags"]:
            proposal["structural_tags"].append("DIFFICULTY_SPIKE")
        section["machine_proposal"] = proposal

    aggregate = {name: 0.0 for name in TYPE_ORDER}
    composition = Counter()
    subtype_weights = Counter()
    total_section_weight = 0.0
    for proposal, item in zip(proposals, features):
        weight = math.sqrt(max(1, item["count"])) * (0.28 + item["pressure"] ** 1.65)
        total_section_weight += weight
        for name, score in item["scores"].items():
            aggregate[name] += score * weight
        if proposal["status"] == "PROPOSED":
            composition[proposal["primary_type"]] += item["count"]
            if proposal["gimmick_subtype"]:
                subtype_weights[proposal["gimmick_subtype"]] += weight * item["scores"]["GIMMICK"]
    normalized_scores = {
        name: (value / total_section_weight if total_section_weight else 0.0)
        for name, value in aggregate.items()
    }
    summary_features = {
        "count": sum(item["count"] for item in features),
        "pressure": maximum,
        "scores": normalized_scores,
        "tags": [],
        "gimmick_subtype": subtype_weights.most_common(1)[0][0] if subtype_weights else None,
        "evidence": {
            name: f"该类型在高压力区段中的综合贡献为 {normalized_scores[name]:.0%}" for name in TYPE_ORDER
        },
    }
    summary = _proposal_from_features(summary_features)
    total_composition = sum(composition.values())
    composition_types = [
        name
        for name, count in composition.most_common()
        if total_composition and count / total_composition >= 0.16
    ][:3]
    if not composition_types and composition:
        composition_types = [composition.most_common(1)[0][0]]
    summary["composition_types"] = composition_types
    summary["classifier_version"] = CLASSIFIER_VERSION
    for section in sections:
        section["machine_proposal"]["classifier_version"] = CLASSIFIER_VERSION
    return sections, summary
