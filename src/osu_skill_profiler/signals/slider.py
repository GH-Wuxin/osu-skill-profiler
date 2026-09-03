"""Slider nested-object generation and lazy cursor simulation.

Independent reimplementation of the audited ppy/osu preprocessing semantics
(pinned upstream ``b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e``): slider
velocity/duration, tick/repeat/tail events, the follow-circle lazy end
position and lazy travel distance/time.  Everything is deterministic and
pure; pathological inputs produce ``None`` values plus provenance flags
instead of silent clipping.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..parser.model import Beatmap, HitObject
from ..parser.osu_parser import effective_timing
from ..slider_semantics import canonical_slider_counts, canonical_slider_timing
from . import LEGACY_SIGNAL_VERSION, PREVIOUS_SIGNAL_VERSION, SIGNAL_VERSION
from .path import SliderPath, build_slider_path

MIN_DELTA_TIME = 25.0
NORMALISED_RADIUS = 50.0
MAXIMUM_SLIDER_RADIUS = NORMALISED_RADIUS * 2.4  # 120
ASSUMED_SLIDER_RADIUS = NORMALISED_RADIUS * 1.8  # 90
TAIL_LENIENCY = -36.0
MAX_SLIDER_LENGTH = 100000.0
OBJECT_RADIUS = 64.0
BROKEN_GAMEFIELD_ROUNDING_ALLOWANCE = 1.00041
DEFAULT_SLIDER_MULTIPLIER = 1.4
DEFAULT_SLIDER_TICK_RATE = 1.0
MAX_SLIDER_SPANS = 10_000
MAX_SLIDER_TICKS = 100_000


@dataclass(frozen=True)
class NestedObject:
    kind: str  # head | tick | repeat | tail
    time_ms: float
    position: tuple[float, float]
    path_progress: float


@dataclass(frozen=True)
class SliderGeometry:
    """Computed slider geometry and lazy cursor state."""

    path: Optional[SliderPath] = None
    velocity_px_per_ms: Optional[float] = None
    duration_ms: Optional[float] = None
    span_duration_ms: Optional[float] = None
    single_span_duration_ms: Optional[float] = None
    total_duration_ms: Optional[float] = None
    repeat_count: int = 0
    span_count: int = 1
    tick_distance: Optional[float] = None
    nested: tuple[NestedObject, ...] = ()
    lazy_travel_time_ms: Optional[float] = None
    lazy_travel_distance_cs: Optional[float] = None
    lazy_end_position: Optional[tuple[float, float]] = None
    tail_position: Optional[tuple[float, float]] = None
    head_position: Optional[tuple[float, float]] = None
    tracking_end_time_ms: Optional[float] = None
    last_real_tick_reordered: bool = False
    provenance: tuple[str, ...] = ()


def circle_size_scale_radius(cs: Optional[float]) -> Optional[float]:
    """Return ``(scale, radius)`` from CircleSize; ``None`` when CS is missing.

    Matches pinned ppy/osu: ``scale = (1 - 0.7*(CS-5)/5)/2 * 1.00041`` and
    ``radius = 64 * scale``.
    """

    if cs is None:
        return None
    try:
        scale = (1.0 - 0.7 * ((cs - 5.0) / 5.0)) / 2.0 * BROKEN_GAMEFIELD_ROUNDING_ALLOWANCE
        radius = OBJECT_RADIUS * scale
    except OverflowError:
        return None
    if not math.isfinite(scale) or not math.isfinite(radius):
        return None
    return (scale, radius)


def approach_rate_preempt_ms(ar: Optional[float]) -> Optional[int]:
    """AR -> preempt (floor of the two-piece 1800/1200/450 linear range)."""

    if ar is None:
        return None
    if ar > 5.0:
        value = 1200.0 + (450.0 - 1200.0) * (ar - 5.0) / 5.0
    elif ar < 5.0:
        value = 1200.0 + (1200.0 - 1800.0) * (ar - 5.0) / 5.0
    else:
        value = 1200.0
    if not math.isfinite(value):
        return None
    return int(math.floor(value))


def overall_difficulty_great_window_ms(od: Optional[float]) -> Optional[float]:
    """OD -> full GREAT window: 2*(floor(DifficultyRange(OD,80,50,20)) - 0.5)."""

    if od is None:
        return None
    if od > 5.0:
        value = 50.0 + (20.0 - 50.0) * (od - 5.0) / 5.0
    elif od < 5.0:
        value = 50.0 + (50.0 - 80.0) * (od - 5.0) / 5.0
    else:
        value = 50.0
    if not math.isfinite(value):
        return None
    return 2.0 * (math.floor(value) - 0.5)


def _effective_velocity(beatmap: Beatmap, time_ms: float) -> tuple[Optional[float], float, Optional[float], tuple[str, ...]]:
    """Slider ball velocity (px/ms) and red beat length at ``time_ms``.

    Replicates ``LegacyRulesetExtensions.GetPrecisionAdjustedBeatLength`` with
    the SV clamp used by the pinned upstream build.
    """

    provenance: list[str] = []
    slider_multiplier = beatmap.difficulty.get("SliderMultiplier")
    if slider_multiplier is None:
        slider_multiplier = DEFAULT_SLIDER_MULTIPLIER
        provenance.append("slider_multiplier_defaulted")
    if not math.isfinite(float(slider_multiplier)) or float(slider_multiplier) <= 0:
        provenance.append("slider_multiplier_nonpositive")
        return None, 0.0, None, tuple(provenance)
    slider_multiplier = float(slider_multiplier)

    bpm, sv, beat_length_ms = effective_timing(beatmap.timing_points, time_ms)
    if not math.isfinite(beat_length_ms) or beat_length_ms <= 0:
        provenance.append("beat_length_nonpositive")
        return None, 0.0, None, tuple(provenance)
    if sv == 0.0:
        slider_velocity_as_beat_length = -math.inf
    elif math.isinf(sv):
        slider_velocity_as_beat_length = -0.0
    else:
        try:
            slider_velocity_as_beat_length = -100.0 / sv
        except OverflowError:
            slider_velocity_as_beat_length = -math.inf
    if slider_velocity_as_beat_length < 0:
        bpm_multiplier = max(10.0, min(1000.0, -slider_velocity_as_beat_length)) / 100.0
    else:
        bpm_multiplier = 1.0
    precision_adjusted_beat_length = beat_length_ms * bpm_multiplier
    if not math.isfinite(precision_adjusted_beat_length) or precision_adjusted_beat_length <= 0:
        provenance.append("precision_adjusted_beat_length_nonpositive")
        return None, 0.0, None, tuple(provenance)
    velocity = 100.0 * slider_multiplier / precision_adjusted_beat_length
    if not math.isfinite(velocity) or velocity <= 0:
        provenance.append("slider_velocity_nonpositive")
        return None, 0.0, None, tuple(provenance)
    return velocity, beat_length_ms, slider_multiplier, tuple(provenance)


def _build_geometry(
    beatmap: Beatmap,
    obj: HitObject,
    start: tuple[float, float],
    cs_radius: Optional[float],
    signal_version: str = SIGNAL_VERSION,
) -> SliderGeometry:
    if signal_version not in (
        LEGACY_SIGNAL_VERSION,
        PREVIOUS_SIGNAL_VERSION,
        SIGNAL_VERSION,
    ):
        raise ValueError(f"unsupported signal version: {signal_version}")
    provenance: list[str] = []
    counts = canonical_slider_counts(obj.slider_slides)
    repeat_count = counts.repeat_count
    span_count = counts.span_count
    provenance.extend(counts.provenance)
    if span_count > MAX_SLIDER_SPANS:
        provenance.append(f"slider_spans_exceeded:{span_count}")
        return SliderGeometry(repeat_count=repeat_count, span_count=span_count, provenance=tuple(provenance))

    expected_distance = obj.slider_pixel_length
    if expected_distance is None:
        provenance.append("pixel_length_missing")
    if expected_distance is not None and not math.isfinite(expected_distance):
        provenance.append("pixel_length_nonfinite")
        expected_distance = None

    velocity, beat_length_ms, _slider_multiplier, velocity_provenance = _effective_velocity(beatmap, obj.time_ms)
    provenance.extend(velocity_provenance)
    if velocity is None:
        return SliderGeometry(repeat_count=repeat_count, span_count=span_count, provenance=tuple(provenance))

    # The .osu slider start position is the hit object position; upstream
    # prepends it to the control point list, so the path always starts at
    # (0, 0) in path-relative coordinates.
    relative_points = [(0.0, 0.0)] + [(float(px) - obj.x, float(py) - obj.y) for px, py in obj.slider_points]
    path = build_slider_path(
        obj.slider_curve_type,
        relative_points,
        expected_distance,
        split_bezier_segments=signal_version == SIGNAL_VERSION,
    )
    _ = path.distance  # force lazy flattening; blocked_reason is set inside
    if path.blocked_reason is not None:
        # Pathological high-degree geometry is refused rather than flattened
        # with unbounded O(n^2) work; the slider keeps unknown-geometry missing
        # semantics plus a provenance flag (never a fabricated path).
        provenance.append(f"path_blocked:{path.blocked_reason}")
        return SliderGeometry(repeat_count=repeat_count, span_count=span_count, provenance=tuple(provenance))
    if path.non_finite_input:
        provenance.append("path_nonfinite_input")
    path_distance = path.distance
    if not math.isfinite(path_distance) or path_distance < 0:
        provenance.append("path_distance_invalid")
        return SliderGeometry(path=path, velocity_px_per_ms=velocity, repeat_count=repeat_count, span_count=span_count, provenance=tuple(provenance))
    if path_distance == 0:
        provenance.append("path_distance_zero")
        return SliderGeometry(
            path=path,
            velocity_px_per_ms=velocity,
            duration_ms=0.0,
            span_duration_ms=0.0,
            single_span_duration_ms=0.0,
            total_duration_ms=0.0,
            repeat_count=repeat_count,
            span_count=span_count,
            tick_distance=0.0,
            nested=(NestedObject("head", obj.time_ms, start, 0.0),),
            lazy_travel_time_ms=0.0,
            lazy_travel_distance_cs=0.0,
            lazy_end_position=start,
            tail_position=start,
            head_position=start,
            tracking_end_time_ms=obj.time_ms,
            provenance=tuple(provenance),
        )

    timing = canonical_slider_timing(path_distance, velocity, span_count)
    if timing is None:
        provenance.append("slider_duration_invalid")
        return SliderGeometry(
            path=path,
            velocity_px_per_ms=velocity,
            repeat_count=repeat_count,
            span_count=span_count,
            provenance=tuple(provenance),
        )
    single_span_duration_ms = timing.single_span_duration_ms
    total_duration_ms = timing.total_slider_duration_ms
    if signal_version == LEGACY_SIGNAL_VERSION:
        # Historical Local v0.2 failure mode retained only for explicit replay.
        duration_ms = single_span_duration_ms
        span_duration_ms = single_span_duration_ms / span_count
    else:
        duration_ms = total_duration_ms
        span_duration_ms = single_span_duration_ms

    tick_rate = beatmap.difficulty.get("SliderTickRate")
    if tick_rate is None:
        tick_rate = DEFAULT_SLIDER_TICK_RATE
        provenance.append("slider_tick_rate_defaulted")
    try:
        tick_rate = float(tick_rate)
        scoring_distance = velocity * beat_length_ms
        tick_distance = scoring_distance / tick_rate
    except (OverflowError, ZeroDivisionError):
        tick_distance = math.inf
    if not math.isfinite(tick_distance) or tick_distance < 0:
        tick_distance = math.inf
        provenance.append("tick_distance_invalid")
    if tick_rate <= 0:
        provenance.append("slider_tick_rate_nonpositive")
    length = min(MAX_SLIDER_LENGTH, path_distance)
    tick_distance = max(0.0, min(length, tick_distance))
    if tick_distance > 0 and length / tick_distance > MAX_SLIDER_TICKS:
        provenance.append("slider_tick_count_exceeded")
        return SliderGeometry(
            path=path,
            velocity_px_per_ms=velocity,
            repeat_count=repeat_count,
            span_count=span_count,
            provenance=tuple(provenance),
        )
    min_distance_from_end = velocity * 10.0

    events: list[NestedObject] = [NestedObject("head", obj.time_ms, start, 0.0)]
    tick_count = 0
    for span in range(span_count):
        span_start_time = obj.time_ms + span * span_duration_ms
        reversed_span = span % 2 == 1
        span_ticks: list[NestedObject] = []
        d = tick_distance
        while d <= length:
            if d >= length - min_distance_from_end:
                break
            path_progress = d / length
            time_progress = 1.0 - path_progress if reversed_span else path_progress
            event_time = span_start_time + time_progress * span_duration_ms
            position = _path_position(path, start, path_progress)
            span_ticks.append(NestedObject("tick", event_time, position, path_progress))
            tick_count += 1
            d += tick_distance
            if tick_distance <= 0:
                break
        if reversed_span:
            span_ticks.reverse()
        events.extend(span_ticks)
        if span < span_count - 1:
            repeat_progress = (span + 1) % 2
            events.append(
                NestedObject(
                    "repeat",
                    span_start_time + span_duration_ms,
                    _path_position(path, start, repeat_progress),
                    repeat_progress,
                )
            )
    tail_progress = span_count % 2
    tail_position = _path_position(path, start, tail_progress)
    events.append(NestedObject("tail", obj.time_ms + duration_ms, tail_position, tail_progress))

    nested = tuple(events)
    last_real_tick: Optional[NestedObject] = None
    for event in events:
        if event.kind == "tick":
            last_real_tick = event
    tracking_end_time_ms = max(obj.time_ms + duration_ms + TAIL_LENIENCY, obj.time_ms + duration_ms / 2.0)
    late_real_tick = last_real_tick is not None and last_real_tick.time_ms > tracking_end_time_ms
    if late_real_tick and signal_version != LEGACY_SIGNAL_VERSION:
        # Pinned OsuDifficultyHitObject updates tracking end before computing
        # lazy end progress.
        tracking_end_time_ms = last_real_tick.time_ms
    lazy_travel_time_ms = tracking_end_time_ms - obj.time_ms
    end_time_min = lazy_travel_time_ms / span_duration_ms
    if end_time_min % 2 >= 1:
        end_time_min = 1 - end_time_min % 1
    else:
        end_time_min %= 1
    lazy_end_initial = _path_position(path, start, end_time_min)

    reordered = False
    lazy_nested = events
    if late_real_tick:
        lazy_nested = [event for event in events if event is not last_real_tick]
        lazy_nested.append(last_real_tick)
        reordered = True

    cursor = start
    lazy_travel_distance = 0.0
    lazy_end = lazy_end_initial
    if cs_radius is not None and cs_radius > 0:
        scaling_factor = NORMALISED_RADIUS / cs_radius
        for i in range(1, len(lazy_nested)):
            movement_object = lazy_nested[i]
            movement = (
                movement_object.position[0] - cursor[0],
                movement_object.position[1] - cursor[1],
            )
            movement_length = _safe_length(movement)
            if movement_length is None:
                provenance.append("lazy_cursor_nonfinite_geometry")
                return SliderGeometry(
                    path=path,
                    velocity_px_per_ms=velocity,
                    duration_ms=duration_ms,
                    span_duration_ms=span_duration_ms,
                    single_span_duration_ms=single_span_duration_ms,
                    total_duration_ms=total_duration_ms,
                    repeat_count=repeat_count,
                    span_count=span_count,
                    tick_distance=tick_distance,
                    nested=nested,
                    tail_position=tail_position,
                    head_position=start,
                    tracking_end_time_ms=tracking_end_time_ms,
                    lazy_travel_distance_cs=None,
                    provenance=tuple(provenance),
                )
            scaled_length = scaling_factor * movement_length
            required_movement = ASSUMED_SLIDER_RADIUS
            if i == len(lazy_nested) - 1:
                lazy_movement = (lazy_end_initial[0] - cursor[0], lazy_end_initial[1] - cursor[1])
                lazy_movement_length = _safe_length(lazy_movement)
                if lazy_movement_length is None:
                    provenance.append("lazy_end_nonfinite_geometry")
                    break
                if lazy_movement_length < movement_length:
                    movement = lazy_movement
                    scaled_length = scaling_factor * lazy_movement_length
            elif movement_object.kind == "repeat":
                required_movement = NORMALISED_RADIUS
            if scaled_length > required_movement:
                factor = (scaled_length - required_movement) / scaled_length
                cursor = (
                    cursor[0] + movement[0] * factor,
                    cursor[1] + movement[1] * factor,
                )
                scaled_length *= factor
                lazy_travel_distance += scaled_length
            if i == len(lazy_nested) - 1:
                lazy_end = cursor
    else:
        provenance.append("cs_missing_for_lazy_scale")
        lazy_travel_distance = None

    return SliderGeometry(
        path=path,
        velocity_px_per_ms=velocity,
        duration_ms=duration_ms,
        span_duration_ms=span_duration_ms,
        single_span_duration_ms=single_span_duration_ms,
        total_duration_ms=total_duration_ms,
        repeat_count=repeat_count,
        span_count=span_count,
        tick_distance=tick_distance,
        nested=nested,
        lazy_travel_time_ms=lazy_travel_time_ms,
        lazy_travel_distance_cs=lazy_travel_distance,
        lazy_end_position=lazy_end,
        tail_position=tail_position,
        head_position=start,
        tracking_end_time_ms=tracking_end_time_ms,
        last_real_tick_reordered=reordered,
        provenance=tuple(provenance),
    )


def _path_position(path: SliderPath, start: tuple[float, float], progress: float) -> tuple[float, float]:
    offset = path.position_at(progress)
    return (start[0] + offset[0], start[1] + offset[1])


def _safe_length(v: tuple[float, float]) -> Optional[float]:
    try:
        length = math.hypot(v[0], v[1])
    except OverflowError:
        return None
    if not math.isfinite(length):
        return None
    return length


__all__ = [
    "MIN_DELTA_TIME",
    "NORMALISED_RADIUS",
    "MAXIMUM_SLIDER_RADIUS",
    "ASSUMED_SLIDER_RADIUS",
    "TAIL_LENIENCY",
    "SliderGeometry",
    "NestedObject",
    "circle_size_scale_radius",
    "approach_rate_preempt_ms",
    "overall_difficulty_great_window_ms",
    "_build_geometry",
]
