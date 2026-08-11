"""Independent reimplementation of pinned ppy/osu per-object evaluators.

All evaluators follow the audited upstream semantics at commit
``b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`` (difficulty version 20260706).
They operate on file-order ``RefObject`` records (the difficulty row for raw
object ``i`` is ``objects[i].row_index = i - 1``).

Return contract:

  - ``None`` for raw object 0 (upstream never creates a difficulty row);
  - ``0.0`` only when the upstream gate itself returns 0;
  - ``None`` with provenance when required inputs are unavailable or the
    computation is non-finite on pathological finite inputs (never a silent
    clip, never a fabricated ordinary difficulty value).

No final skill aggregation, strain decay, star rating or PP is computed.
"""

from __future__ import annotations

import math
from typing import Optional

from .diff_utils import (
    clamp,
    lerp,
    logistic,
    ms_to_bpm,
    bpm_to_ms,
    norm,
    reverse_lerp,
    smoothstep,
    smootherstep,
    smoothstep_bell_curve_unit,
)
from .preprocess import RefObject

_MAX_DELTA = 2**31 - 1


def _prev(objects: list[RefObject], i: int, skip: int = 0) -> Optional[RefObject]:
    index = i - 1 - skip
    if index < 1:
        # Upstream difficulty rows start at raw object 1; Previous() never
        # resolves to raw object 0.
        return None
    return objects[index] if 0 <= index < len(objects) else None


def _next(objects: list[RefObject], i: int, skip: int = 0) -> Optional[RefObject]:
    index = i + 1 + skip
    return objects[index] if 0 <= index < len(objects) else None


def _num(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _angle_acuteness(angle: float) -> float:
    return smoothstep(angle, math.radians(140.0), math.radians(40.0))


def _angle_wideness(angle: float) -> float:
    return smoothstep(angle, math.radians(40.0), math.radians(140.0))


def _high_bpm_snap(ms: float) -> float:
    return 1.0 / (1.0 - 0.03 ** ((ms / 1000.0) ** 0.65))


def _high_bpm_agility(ms: float) -> float:
    return 1.0 / (1.0 - 0.2 ** (ms / 1000.0))


def _high_bpm_speed(ms: float) -> float:
    return 1.0 / (1.0 - 0.3 ** (ms / 1000.0))


def _high_bpm_reading(ms: float) -> float:
    return 1.0 / (1.0 - 0.8 ** (ms / 1000.0))


def _vector_angle_repetition(objects: list[RefObject], i: int, curr: RefObject, prev: RefObject) -> Optional[float]:
    if curr.angle_rad is None or prev.angle_rad is None:
        return 1.0

    constant_angle_count = 0.0
    for skip in range(6):
        prev_obj = _prev(objects, i, skip)
        if prev_obj is None:
            break
        curr_adj = _num(curr.adjusted_delta_time_ms)
        prev_adj = _num(prev_obj.adjusted_delta_time_ms)
        if curr_adj is None or prev_adj is None:
            return None
        if max(curr_adj, prev_adj) > 1.1 * min(curr_adj, prev_adj):
            break
        curr_nva = _num(curr.normalised_vector_angle_rad)
        prev_nva = _num(prev_obj.normalised_vector_angle_rad)
        if curr_nva is not None and prev_nva is not None:
            angle_difference = abs(curr_nva - prev_nva)
            constant_angle_count += math.cos(8.0 * min(math.radians(11.25), angle_difference))

    try:
        vector_repetition = min(0.5 / constant_angle_count, 1.0) ** 2 if constant_angle_count != 0 else 1.0
    except ZeroDivisionError:
        vector_repetition = 1.0

    curr_lazy = _num(curr.lazy_jump_distance_cs)
    if curr_lazy is None:
        return None
    stack_factor = smootherstep(curr_lazy, 0.0, 100.0)
    angle_difference_adjusted = math.cos(
        2.0 * min(math.radians(45.0), abs(curr.angle_rad - prev.angle_rad) * stack_factor)
    )
    base_nerf = 1.0 - 0.15 * _angle_acuteness(prev.angle_rad) * angle_difference_adjusted
    return (base_nerf + (1.0 - base_nerf) * vector_repetition * 0.5 * stack_factor) ** 2


def _overlap_factor(first: RefObject, second: RefObject) -> Optional[float]:
    radius = _num(first.radius_px)
    if radius is None:
        return None
    if radius <= 0:
        return None
    distance = math.hypot(
        first.position[0] - second.position[0],
        first.position[1] - second.position[1],
    )
    return clamp(1.0 - ((max(distance - radius, 0.0) / radius) ** 2), 0.0, 1.0)


def snap_aim(objects: list[RefObject], i: int, include_sliders: bool) -> Optional[float]:
    """SnapAimEvaluator.EvaluateDifficultyOf (include/exclude variants)."""

    if i < 1:
        return None
    curr = objects[i]
    if curr.row_index <= 1 or curr.is_spinner:
        return 0.0
    prev = objects[i - 1]
    if prev.is_spinner:
        return 0.0

    curr_distance = _num(curr.lazy_jump_distance_cs if include_sliders else curr.jump_distance_cs)
    prev_distance = _num(prev.lazy_jump_distance_cs if include_sliders else prev.jump_distance_cs)
    curr_adj = _num(curr.adjusted_delta_time_ms)
    prev_adj = _num(prev.adjusted_delta_time_ms)
    if curr_distance is None or prev_distance is None or curr_adj is None or prev_adj is None:
        return None

    curr_velocity = curr_distance / curr_adj
    if prev.is_slider and include_sliders:
        prev_travel = _num(prev.lazy_travel_distance_cs)
        if prev_travel is None:
            return None
        slider_distance = prev_travel + curr_distance
        curr_velocity = max(curr_velocity, slider_distance / curr_adj)
    prev_velocity = prev_distance / prev_adj

    snap_difficulty = curr_velocity
    repetition = _vector_angle_repetition(objects, i, curr, prev)
    if repetition is None:
        return None
    snap_difficulty *= repetition

    if curr.angle_rad is not None and prev.angle_rad is not None:
        curr_angle = curr.angle_rad
        last_angle = prev.angle_rad
        velocity_influence = min(curr_velocity, prev_velocity)

        acute_angle_bonus = 0.0
        if max(curr_adj, prev_adj) < 1.25 * min(curr_adj, prev_adj):
            acute_angle_bonus = _angle_acuteness(curr_angle)
            acute_angle_bonus *= 0.08 + 0.92 * (1.0 - min(acute_angle_bonus, _angle_acuteness(last_angle) ** 3))
            acute_angle_bonus *= (
                velocity_influence
                * smootherstep(ms_to_bpm(curr_adj, 2), 300.0, 400.0)
                * smootherstep(curr_distance, 0.0, 200.0)
            )

        wide_angle_bonus = _angle_wideness(curr_angle)
        wide_angle_bonus *= 0.25 + 0.75 * (1.0 - min(wide_angle_bonus, _angle_wideness(last_angle) ** 3))

        wide_angle_curr_velocity = curr_distance / (curr_adj ** 1.45)
        wide_angle_prev_velocity = prev_distance / (prev_adj ** 1.45)
        if prev.is_slider and include_sliders:
            prev_travel = _num(prev.lazy_travel_distance_cs)
            if prev_travel is None:
                return None
            slider_distance = prev_travel + curr_distance
            wide_angle_curr_velocity = max(wide_angle_curr_velocity, slider_distance / (curr_adj ** 1.45))
        wide_angle_bonus *= min(wide_angle_curr_velocity, wide_angle_prev_velocity)

        last2 = _prev(objects, i, 2)
        if last2 is not None:
            back_forth_distance = math.hypot(
                prev.position[0] - last2.position[0],
                prev.position[1] - last2.position[1],
            )
            if back_forth_distance < 1.0:
                wide_angle_bonus *= 1.0 - 0.55 * (1.0 - back_forth_distance)

        snap_difficulty += max(acute_angle_bonus * 2.41, wide_angle_bonus * 9.67)

        wiggle_bonus = (
            velocity_influence
            * smootherstep(curr_distance, 50.0, 100.0)
            * reverse_lerp(curr_distance, 300.0, 100.0) ** 1.8
            * smootherstep(curr_angle, math.radians(110.0), math.radians(60.0))
            * smootherstep(prev_distance, 50.0, 100.0)
            * reverse_lerp(prev_distance, 300.0, 100.0) ** 1.8
            * smootherstep(last_angle, math.radians(110.0), math.radians(60.0))
        )
        snap_difficulty += wiggle_bonus * 1.02

    if max(prev_velocity, curr_velocity) != 0.0:
        if include_sliders:
            curr_velocity = curr_distance / curr_adj
        dist_ratio = smoothstep(
            abs(prev_velocity - curr_velocity) / max(prev_velocity, curr_velocity), 0.0, 1.0
        )
        overlap_velocity_buff = min(
            125.0 / min(curr_adj, prev_adj),
            abs(prev_velocity - curr_velocity),
        )
        velocity_change_bonus = overlap_velocity_buff * dist_ratio
        velocity_change_bonus *= (min(curr_adj, prev_adj) / max(curr_adj, prev_adj)) ** 2
        snap_difficulty += velocity_change_bonus * 0.9

    if curr.is_slider and include_sliders:
        travel_distance = _num(curr.travel_distance_cs)
        travel_time = _num(curr.travel_time_ms)
        if travel_distance is None or travel_time is None or travel_time <= 0:
            return None
        slider_bonus = travel_distance / travel_time
        snap_difficulty += (slider_bonus if slider_bonus < 1.0 else slider_bonus ** 0.75) * 1.5

    small_circle = _num(curr.small_circle_bonus)
    if small_circle is None:
        return None
    snap_difficulty *= small_circle
    snap_difficulty *= _high_bpm_snap(curr_adj)
    return snap_difficulty


def agility(objects: list[RefObject], i: int) -> Optional[float]:
    """AgilityEvaluator.EvaluateDifficultyOf."""

    if i < 1:
        return None
    curr = objects[i]
    if curr.is_spinner:
        return 0.0
    curr_lazy = _num(curr.lazy_jump_distance_cs)
    curr_adj = _num(curr.adjusted_delta_time_ms)
    if curr_lazy is None or curr_adj is None:
        return None
    prev = _prev(objects, i, 0) if curr.row_index > 0 else None
    travel_distance = 0.0 if prev is None else _num(prev.lazy_travel_distance_cs)
    if travel_distance is None:
        return None
    distance = travel_distance + curr_lazy
    distance_scaled = min(distance, 120.0) / 120.0
    small_circle = _num(curr.small_circle_bonus)
    if small_circle is None:
        return None
    return (
        distance_scaled
        * 1000.0
        / curr_adj
        * small_circle ** 1.5
        * _high_bpm_agility(curr_adj)
    )


def flow_aim(objects: list[RefObject], i: int, include_sliders: bool) -> Optional[float]:
    """FlowAimEvaluator.EvaluateDifficultyOf (include/exclude variants)."""

    if i < 1:
        return None
    curr = objects[i]
    if curr.row_index <= 1 or curr.is_spinner:
        return 0.0
    prev = objects[i - 1]
    if prev.is_spinner:
        return 0.0

    curr_distance = _num(curr.lazy_jump_distance_cs if include_sliders else curr.jump_distance_cs)
    prev_distance = _num(prev.lazy_jump_distance_cs if include_sliders else prev.jump_distance_cs)
    curr_adj = _num(curr.adjusted_delta_time_ms)
    prev_adj = _num(prev.adjusted_delta_time_ms)
    small_circle = _num(curr.small_circle_bonus)
    if (
        curr_distance is None
        or prev_distance is None
        or curr_adj is None
        or prev_adj is None
        or small_circle is None
    ):
        return None

    curr_velocity = curr_distance / curr_adj
    if prev.is_slider and include_sliders:
        prev_travel = _num(prev.lazy_travel_distance_cs)
        if prev_travel is None:
            return None
        slider_distance = prev_travel + curr_distance
        curr_velocity = max(curr_velocity, slider_distance / curr_adj)
    prev_velocity = prev_distance / prev_adj

    flow_difficulty = curr_velocity * math.sqrt(small_circle)
    flow_difficulty *= 1.0 + min(
        0.25,
        ((max(curr_adj, prev_adj) - min(curr_adj, prev_adj)) / 50.0) ** 4,
    )

    if curr.angle_rad is not None and prev.angle_rad is not None:
        angle_difference = abs(curr.angle_rad - prev.angle_rad)
        angle_difference_adjusted = math.sin(angle_difference / 2.0) * 180.0
        angular_velocity = angle_difference_adjusted / (curr_adj * 0.1)
        flow_difficulty *= 0.8 + math.sqrt(angular_velocity / 270.0)

    overlapped_notes_weight = 1.0
    if curr.row_index > 2:
        last_last = _prev(objects, i, 1)
        if last_last is None:
            return None
        o1 = _overlap_factor(curr, prev)
        o2 = _overlap_factor(curr, last_last)
        o3 = _overlap_factor(prev, last_last)
        if o1 is None or o2 is None or o3 is None:
            return None
        overlapped_notes_weight = 1.0 - o1 * o2 * o3

    if curr.angle_rad is not None:
        flow_difficulty += curr_velocity * _angle_acuteness(curr.angle_rad) * overlapped_notes_weight

    if max(prev_velocity, curr_velocity) != 0.0:
        if include_sliders:
            curr_velocity = curr_distance / curr_adj
        dist_ratio = smoothstep(
            abs(prev_velocity - curr_velocity) / max(prev_velocity, curr_velocity), 0.0, 1.0
        )
        overlap_velocity_buff = min(
            125.0 / min(curr_adj, prev_adj),
            abs(prev_velocity - curr_velocity),
        )
        flow_difficulty += overlap_velocity_buff * dist_ratio * overlapped_notes_weight * 0.52

    if curr.is_slider and include_sliders:
        travel_distance = _num(curr.travel_distance_cs)
        travel_time = _num(curr.travel_time_ms)
        if travel_distance is None or travel_time is None or travel_time <= 0:
            return None
        flow_difficulty += travel_distance / travel_time

    flow_difficulty = flow_difficulty ** 1.45
    return flow_difficulty * smootherstep(curr_distance, 0.0, 50.0)


def speed(objects: list[RefObject], i: int) -> Optional[float]:
    """SpeedEvaluator.EvaluateDifficultyOf."""

    if i < 1:
        return None
    curr = objects[i]
    if curr.is_spinner:
        return 0.0
    curr_adj = _num(curr.adjusted_delta_time_ms)
    hit_window = _num(curr.hit_window_great_ms)
    feasibility = _num(curr.double_tap_feasibility)
    if curr_adj is None or hit_window is None or feasibility is None:
        return None
    if hit_window <= 0:
        return None
    double_tap_feasibility = 1.0 - feasibility

    strain_time = curr_adj
    strain_time /= clamp((strain_time / hit_window) / 0.93, 0.92, 1.0)

    speed_bonus = 0.0
    if ms_to_bpm(strain_time) > 200.0:
        speed_bonus = 0.75 * ((bpm_to_ms(200.0) - strain_time) / 40.0) ** 2

    speed_difficulty = (1.0 + speed_bonus) * 1000.0 / strain_time
    speed_difficulty *= _high_bpm_speed(curr_adj)
    speed_difficulty *= double_tap_feasibility
    return speed_difficulty


class _Island:
    __slots__ = ("delta", "delta_count", "occurrences")

    def __init__(self, delta: Optional[int] = None) -> None:
        self.delta = None if delta is None else max(int(delta), 25)
        self.delta_count = 1
        self.occurrences = 1

    def add_delta(self, delta: int) -> None:
        if self.delta is None:
            self.delta = max(int(delta), 25)
        self.delta_count += 1

    def is_similar_polarity(self, other: "_Island", epsilon: float) -> bool:
        if self.delta_count <= 1 or other.delta_count <= 1:
            return False
        return (
            abs(self.delta - other.delta) < epsilon
            and self.delta_count % 2 == other.delta_count % 2
        )

    def almost_equals(self, other: "_Island", epsilon: float) -> bool:
        return abs(self.delta - other.delta) < epsilon and self.delta_count == other.delta_count


def _get_effective_difficulty(delta_difference_ratio: float) -> float:
    fraction = delta_difference_ratio - math.trunc(delta_difference_ratio)
    return 1.0 + 26.0 * min(0.5, smoothstep_bell_curve_unit(fraction))


def rhythm(objects: list[RefObject], i: int) -> Optional[float]:
    """RhythmEvaluator.EvaluateDifficultyOf."""

    if i < 1:
        return None
    curr = objects[i]
    if curr.is_spinner:
        return 0.0
    if curr.row_index == 0:
        return 1.0
    hit_window = _num(curr.hit_window_great_ms)
    if hit_window is None:
        return None

    history_time_max = 5000.0
    history_objects_max = 32
    rhythm_overall_multiplier = 0.95
    delta_min_value = 1e-7
    epsilon = hit_window * 0.3

    rhythm_complexity_sum = 0.0
    island = _Island()
    previous_island = _Island()
    islands: list[_Island] = []
    start_difficulty = 0.0
    first_delta_switch = False
    historical_note_count = min(curr.row_index, history_objects_max)

    rhythm_start = 0
    while rhythm_start < historical_note_count - 2:
        prev_obj = _prev(objects, i, rhythm_start)
        if prev_obj is None:
            break
        if curr.start_time_ms - prev_obj.start_time_ms >= history_time_max:
            break
        rhythm_start += 1

    prev_obj = _prev(objects, i, rhythm_start)
    prev_prev_obj = _prev(objects, i, rhythm_start + 1)
    if prev_obj is None:
        return None

    for li in range(rhythm_start, 0, -1):
        curr_obj = _prev(objects, i, li - 1)
        if curr_obj is None:
            break
        if curr_obj.is_spinner:
            continue

        time_decay = (history_time_max - (curr.start_time_ms - curr_obj.start_time_ms)) / history_time_max
        note_decay = float(historical_note_count - li) / historical_note_count
        curr_historical_decay = min(note_decay, time_decay)

        curr_delta_raw = _num(curr_obj.delta_time_ms)
        prev_delta_raw = _num(prev_obj.delta_time_ms)
        if curr_delta_raw is None or prev_delta_raw is None:
            return None
        curr_delta = max(curr_delta_raw, delta_min_value)
        prev_delta = max(prev_delta_raw, delta_min_value)
        delta_difference = abs(prev_delta - curr_delta)

        if island.delta is None:
            island = _Island(int(curr_delta))

        delta_difference_ratio = max(prev_delta, curr_delta) / min(prev_delta, curr_delta)
        difference_multiplier = clamp(2.0 - delta_difference_ratio / 8.0, 0.0, 1.0)
        window_penalty = clamp((delta_difference - epsilon) / epsilon, 0.0, 1.0)
        effective_difficulty = _get_effective_difficulty(delta_difference_ratio) * window_penalty * difference_multiplier

        if prev_obj.is_slider:
            lazy_end_delta = _num(curr_obj.minimum_jump_time_ms)
            real_end_delta = _num(curr_obj.last_object_end_delta_time_ms)
            if lazy_end_delta is None or real_end_delta is None:
                return None
            lazy_ratio = max(lazy_end_delta, curr_delta) / min(lazy_end_delta, curr_delta)
            real_ratio = max(real_end_delta, curr_delta) / min(real_end_delta, curr_delta)
            slider_effective = min(_get_effective_difficulty(lazy_ratio), _get_effective_difficulty(real_ratio))
            effective_difficulty = min(slider_effective, effective_difficulty)

        if delta_difference < epsilon:
            island.add_delta(int(curr_delta))

        if first_delta_switch:
            if delta_difference > epsilon:
                if curr_obj.is_slider:
                    effective_difficulty *= 0.5
                if island.is_similar_polarity(previous_island, epsilon):
                    effective_difficulty *= 0.5

                if prev_prev_obj is None:
                    return None
                prev_prev_delta_raw = _num(prev_prev_obj.delta_time_ms)
                if prev_prev_delta_raw is None:
                    return None
                prev_prev_delta = max(prev_prev_delta_raw, delta_min_value)
                if (
                    prev_prev_delta > prev_delta + epsilon
                    and prev_delta > curr_delta + epsilon
                ):
                    effective_difficulty *= 0.125

                if previous_island.delta_count == island.delta_count:
                    effective_difficulty *= 0.5

                is_speeding_up = prev_delta > curr_delta + epsilon
                if is_speeding_up:
                    effective_difficulty *= 0.65

                found = False
                for existing_island in islands:
                    if existing_island.almost_equals(island, epsilon):
                        if previous_island.almost_equals(island, epsilon):
                            existing_island.occurrences += 1
                        power = logistic(
                            float(island.delta),
                            midpoint_offset=58.33,
                            multiplier=0.24,
                            max_value=2.75,
                        )
                        effective_difficulty *= min(
                            3.0 / existing_island.occurrences,
                            (1.0 / existing_island.occurrences) ** power,
                        )
                        found = True
                        break
                if not found and island.delta_count > 0:
                    islands.append(island)

                prev_feasibility = _num(prev_obj.double_tap_feasibility)
                if prev_feasibility is None:
                    return None
                effective_difficulty *= 1.0 - prev_feasibility * 0.75

                if island.delta_count > 1:
                    rhythm_complexity_sum += math.sqrt(effective_difficulty * start_difficulty) * curr_historical_decay
                else:
                    rhythm_complexity_sum += 0.7 * curr_historical_decay

                start_difficulty = effective_difficulty

                if prev_delta + epsilon < curr_delta:
                    first_delta_switch = False

                previous_island = island
                island = _Island(int(curr_delta))
        elif prev_delta > curr_delta + epsilon:
            first_delta_switch = True
            if curr_obj.is_slider:
                effective_difficulty *= 0.6
            if prev_obj.is_slider:
                effective_difficulty *= 0.6
            start_difficulty = effective_difficulty
            island = _Island(int(curr_delta))

        prev_prev_obj = prev_obj
        prev_obj = curr_obj

    rhythm_complexity_sum *= reverse_lerp(float(island.delta_count), 22.0, 3.0)
    return math.sqrt(4.0 + rhythm_complexity_sum * rhythm_overall_multiplier) / 2.0


def speed_with_rhythm(objects: list[RefObject], i: int) -> Optional[float]:
    """Direct product ``SpeedEvaluator * RhythmEvaluator`` (reference-only)."""

    speed_value = speed(objects, i)
    rhythm_value = rhythm(objects, i)
    if speed_value is None or rhythm_value is None:
        return None
    return speed_value * rhythm_value


def _opacity_at(obj: RefObject, time_ms: float) -> Optional[float]:
    if time_ms > obj.start_time_ms:
        return 0.0
    preempt = _num(obj.preempt_ms)
    fade_in = _num(obj.fade_in_ms)
    if preempt is None or fade_in is None:
        return None
    fade_in_start = obj.start_time_ms - preempt
    if fade_in <= 0:
        return None
    return clamp((time_ms - fade_in_start) / fade_in, 0.0, 1.0)


def _time_nerf_factor(delta_time_ms: float) -> float:
    return clamp(2.0 - delta_time_ms / 1500.0, 0.0, 1.0)


def _past_object_difficulty_influence(objects: list[RefObject], i: int, curr: RefObject) -> Optional[float]:
    if curr.preempt_ms is None:
        return None
    total = 0.0
    skip = 0
    while True:
        loop_obj = _prev(objects, i, skip)
        if loop_obj is None:
            break
        if curr.start_time_ms - loop_obj.start_time_ms > 3000.0:
            break
        if loop_obj.start_time_ms < curr.start_time_ms - curr.preempt_ms:
            break
        opacity = _opacity_at(loop_obj, loop_obj.start_time_ms)
        lazy_jump = _num(loop_obj.lazy_jump_distance_cs)
        if opacity is None or lazy_jump is None:
            return None
        loop_difficulty = opacity * smootherstep(lazy_jump, 15.0, 150.0)
        loop_difficulty *= _time_nerf_factor(curr.start_time_ms - loop_obj.start_time_ms)
        total += loop_difficulty
        skip += 1
    return total


def _current_visible_object_density(objects: list[RefObject], i: int, curr: RefObject) -> Optional[float]:
    total = 0.0
    index = i + 1
    while index < len(objects):
        hit_object = objects[index]
        if hit_object.start_time_ms - curr.start_time_ms > 3000.0:
            break
        if curr.start_time_ms < hit_object.start_time_ms - hit_object.preempt_ms:
            break
        if hit_object.preempt_ms is None:
            return None
        opacity = _opacity_at(hit_object, curr.start_time_ms)
        if opacity is None:
            return None
        total += opacity * _time_nerf_factor(hit_object.start_time_ms - curr.start_time_ms)
        index += 1
    return total


def _constant_angle_nerf_factor(objects: list[RefObject], i: int, curr: RefObject) -> Optional[float]:
    constant_angle_count = 0.0
    index = 0
    current_time_gap = 0.0
    loop_prev0 = curr
    loop_prev1: Optional[RefObject] = None
    loop_prev2: Optional[RefObject] = None

    while current_time_gap < 2000.0:
        loop_obj = _prev(objects, i, index)
        if loop_obj is None:
            break
        loop_adj = _num(loop_obj.adjusted_delta_time_ms)
        if loop_adj is None:
            return None
        long_interval_factor = 1.0 - reverse_lerp(loop_adj, 200.0, 2000.0)

        if loop_obj.angle_rad is not None and curr.angle_rad is not None:
            angle_difference = abs(curr.angle_rad - loop_obj.angle_rad)
            angle_difference_alternating = math.pi

            if (
                loop_prev0.angle_rad is not None
                and loop_prev1 is not None
                and loop_prev1.angle_rad is not None
                and loop_prev2 is not None
                and loop_prev2.angle_rad is not None
            ):
                angle_difference_alternating = abs(loop_prev1.angle_rad - loop_obj.angle_rad)
                angle_difference_alternating += abs(loop_prev2.angle_rad - loop_prev0.angle_rad)
                weight = (
                    reverse_lerp(min(loop_obj.angle_rad, loop_prev0.angle_rad) * 180.0 / math.pi, 20.0, 5.0)
                    * reverse_lerp(max(loop_obj.angle_rad, loop_prev0.angle_rad) * 180.0 / math.pi, 60.0, 120.0)
                )
                angle_difference_alternating = lerp(math.pi, 0.1 * angle_difference_alternating, weight)

            lazy_jump = _num(loop_obj.lazy_jump_distance_cs)
            if lazy_jump is None:
                return None
            stack_factor = smootherstep(lazy_jump, 0.0, 50.0)
            constant_angle_count += (
                math.cos(3.0 * min(math.radians(30.0), min(angle_difference, angle_difference_alternating) * stack_factor))
                * long_interval_factor
            )

        current_time_gap = curr.start_time_ms - loop_obj.start_time_ms
        index += 1
        loop_prev2 = loop_prev1
        loop_prev1 = loop_prev0
        loop_prev0 = loop_obj

    try:
        return clamp(2.0 / constant_angle_count, 0.2, 1.0)
    except ZeroDivisionError:
        return 1.0


def reading(objects: list[RefObject], i: int) -> Optional[float]:
    """ReadingEvaluator.EvaluateDifficultyOf(current, hidden=false)."""

    if i < 1:
        return None
    curr = objects[i]
    if curr.is_spinner or curr.row_index == 0:
        return 0.0
    lazy_jump = _num(curr.lazy_jump_distance_cs)
    curr_adj = _num(curr.adjusted_delta_time_ms)
    if lazy_jump is None or curr_adj is None:
        return None

    velocity = max(1.0, lazy_jump / curr_adj)
    past_influence = _past_object_difficulty_influence(objects, i, curr)
    if past_influence is None:
        return None
    visible_density = _current_visible_object_density(objects, i, curr)
    if visible_density is None:
        return None
    angle_nerf = _constant_angle_nerf_factor(objects, i, curr)
    if angle_nerf is None:
        return None

    future_influence = math.sqrt(visible_density)
    next_obj = _next(objects, i, 0)
    if next_obj is not None:
        next_lazy = _num(next_obj.lazy_jump_distance_cs)
        if next_lazy is None:
            return None
        future_influence *= smootherstep(next_lazy, 15.0, 150.0)

    note_density_difficulty = (
        (past_influence + future_influence) ** 1.7
        * 0.4
        * angle_nerf
        * velocity
    )
    note_density_difficulty = max(0.0, note_density_difficulty - 2.5)
    note_density_difficulty = note_density_difficulty ** 0.45 * 2.4

    preempt = _num(curr.preempt_ms)
    if preempt is None:
        return None
    preempt_difficulty = (
        ((500.0 - preempt + abs(preempt - 500.0)) / 2.0) ** 2.5
        / 140000.0
        * angle_nerf
        * velocity
    )

    return norm(1.5, preempt_difficulty, note_density_difficulty) * _high_bpm_reading(curr_adj)


__all__ = [
    "snap_aim",
    "agility",
    "flow_aim",
    "speed",
    "rhythm",
    "speed_with_rhythm",
    "reading",
]
