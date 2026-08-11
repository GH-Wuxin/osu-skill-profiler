"""Normalized, object-level beatmap representation.

The .osu text itself is never used as model tokens. Instead each hit object is
converted into a stable numeric view that downstream feature extractors and
segmenters consume. All coordinates are normalized to the 512x384 osu!standard
playfield; times stay in milliseconds.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Optional

from .model import Beatmap, HitObject
from .osu_parser import OsuParseError, effective_timing

PLAYFIELD_WIDTH = 512.0
PLAYFIELD_HEIGHT = 384.0
DENSITY_WINDOW_MS = 1000.0


@dataclass(frozen=True)
class NormalizedObject:
    """One hit object in normalized form, with derived local context."""

    raw: HitObject
    time_ms: float
    x_norm: float
    y_norm: float
    delta_time_ms: Optional[float]
    distance_from_previous: Optional[float]
    movement_velocity_norm_per_s: Optional[float]
    angle_deg: Optional[float]
    local_bpm: float
    local_sv: float
    local_density_per_s: float
    slider_duration_ms: Optional[float] = None
    slider_velocity_px_per_s: Optional[float] = None

    def end_time_ms(self) -> float:
        if self.raw.object_type == "slider" and self.slider_duration_ms is not None:
            return self.time_ms + self.slider_duration_ms
        return self.raw.end_time_ms()


@dataclass(frozen=True)
class NormalizedBeatmap:
    beatmap: Beatmap
    objects: tuple[NormalizedObject, ...]

    def slice(self, start_idx: int, end_idx: int) -> "NormalizedBeatmap":
        """Return a view over objects [start_idx, end_idx) with shared timing context."""

        return NormalizedBeatmap(beatmap=self.beatmap, objects=self.objects[start_idx:end_idx])


def _slider_duration(obj: HitObject, beat_length_ms: float, sv: float, slider_multiplier: float) -> Optional[float]:
    if obj.slider_pixel_length is None or slider_multiplier <= 0 or sv <= 0:
        return None
    try:
        value = obj.slider_pixel_length / (slider_multiplier * 100.0 * sv) * beat_length_ms
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def _angle_deg(prev: NormalizedObject, current: NormalizedObject, nxt: NormalizedObject) -> Optional[float]:
    ax, ay = current.x_norm - prev.x_norm, current.y_norm - prev.y_norm
    bx, by = nxt.x_norm - current.x_norm, nxt.y_norm - current.y_norm
    try:
        norm_a = math.hypot(ax, ay)
        norm_b = math.hypot(bx, by)
    except OverflowError:
        return None
    if norm_a == 0 or norm_b == 0 or not (math.isfinite(norm_a) and math.isfinite(norm_b)):
        return None
    try:
        cosine = (ax * bx + ay * by) / (norm_a * norm_b)
    except OverflowError:
        return None
    if not math.isfinite(cosine):
        return None
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def normalize(beatmap: Beatmap) -> NormalizedBeatmap:
    """Convert a parsed Beatmap into the normalized representation."""

    if beatmap.mode != 0:
        raise OsuParseError(f"only osu!standard (mode 0) is supported, got mode {beatmap.mode}")
    slider_multiplier = float(beatmap.difficulty.get("SliderMultiplier", 1.4))
    if slider_multiplier <= 0:
        raise OsuParseError("SliderMultiplier must be positive")

    raw_objects = beatmap.hit_objects
    times = [obj.time_ms for obj in raw_objects]
    sorted_times = sorted(times)

    def local_density(idx: int) -> float:
        center = times[idx]
        lo = bisect.bisect_left(sorted_times, center - DENSITY_WINDOW_MS / 2.0)
        hi = bisect.bisect_right(sorted_times, center + DENSITY_WINDOW_MS / 2.0)
        count = hi - lo
        return count / (DENSITY_WINDOW_MS / 1000.0)

    normalized: list[NormalizedObject] = []
    for idx, obj in enumerate(raw_objects):
        bpm, sv, beat_length_ms = effective_timing(beatmap.timing_points, obj.time_ms)
        x_norm = obj.x / PLAYFIELD_WIDTH
        y_norm = obj.y / PLAYFIELD_HEIGHT
        delta = times[idx] - times[idx - 1] if idx > 0 else None
        distance = None
        velocity = None
        if idx > 0:
            prev = normalized[idx - 1]
            distance = math.hypot(x_norm - prev.x_norm, y_norm - prev.y_norm)
            if delta is not None and delta > 0:
                try:
                    velocity = distance / (delta / 1000.0)
                except OverflowError:
                    velocity = None
                if velocity is not None and not math.isfinite(velocity):
                    velocity = None
        slider_duration = None
        slider_velocity = None
        if obj.object_type == "slider":
            slider_duration = _slider_duration(obj, beat_length_ms, sv, slider_multiplier)
            if slider_duration and slider_duration > 0 and obj.slider_pixel_length is not None:
                try:
                    slider_velocity = obj.slider_pixel_length / (slider_duration / 1000.0)
                except OverflowError:
                    slider_velocity = None
                if slider_velocity is not None and not math.isfinite(slider_velocity):
                    slider_velocity = None
        normalized.append(
            NormalizedObject(
                raw=obj,
                time_ms=obj.time_ms,
                x_norm=x_norm,
                y_norm=y_norm,
                delta_time_ms=delta,
                distance_from_previous=distance,
                movement_velocity_norm_per_s=velocity,
                angle_deg=None,
                local_bpm=bpm,
                local_sv=sv,
                local_density_per_s=local_density(idx),
                slider_duration_ms=slider_duration,
                slider_velocity_px_per_s=slider_velocity,
            )
        )

    for idx in range(len(normalized)):
        if idx > 0 and idx < len(normalized) - 1:
            normalized[idx] = NormalizedObject(
                raw=normalized[idx].raw,
                time_ms=normalized[idx].time_ms,
                x_norm=normalized[idx].x_norm,
                y_norm=normalized[idx].y_norm,
                delta_time_ms=normalized[idx].delta_time_ms,
                distance_from_previous=normalized[idx].distance_from_previous,
                movement_velocity_norm_per_s=normalized[idx].movement_velocity_norm_per_s,
                angle_deg=_angle_deg(normalized[idx - 1], normalized[idx], normalized[idx + 1]),
                local_bpm=normalized[idx].local_bpm,
                local_sv=normalized[idx].local_sv,
                local_density_per_s=normalized[idx].local_density_per_s,
                slider_duration_ms=normalized[idx].slider_duration_ms,
                slider_velocity_px_per_s=normalized[idx].slider_velocity_px_per_s,
            )
    return NormalizedBeatmap(beatmap=beatmap, objects=tuple(normalized))
