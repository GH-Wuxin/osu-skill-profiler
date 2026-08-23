"""Per-object Local Signal extraction (Layer A, v0.3 current; v0.2 replayable).

The extractor processes hit objects in .osu file order (matching the audited
ppy/osu difficulty preprocessing order) while also emitting a
``time_sorted_index`` so downstream consumers can never confuse file order
with chronological order.

Only observable signals are produced.  No official difficulty final, no
harmonic aggregation and no skill score is computed or emitted.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from ..parser.model import Beatmap, HitObject
from .contract import (
    LEGACY_SIGNAL_VERSION,
    SEGMENT_SUMMARY_FIELDS,
    SIGNAL_VERSION,
    UPSTREAM_COMMIT,
    UPSTREAM_DIFFICULTY_VERSION,
    numeric_signals,
    signal_schema,
)
from .slider import (
    ASSUMED_SLIDER_RADIUS,
    MAXIMUM_SLIDER_RADIUS,
    MIN_DELTA_TIME,
    NORMALISED_RADIUS,
    SliderGeometry,
    _build_geometry,
    approach_rate_preempt_ms,
    circle_size_scale_radius,
    overall_difficulty_great_window_ms,
)

SEGMENT_WINDOW_MS = 5000.0


def _safe_hypot(a: float, b: float) -> Optional[float]:
    try:
        value = math.hypot(a, b)
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def _calculate_angle(current: tuple[float, float], last: tuple[float, float], last_last: tuple[float, float]) -> Optional[float]:
    v1 = (last_last[0] - last[0], last_last[1] - last[1])
    v2 = (current[0] - last[0], current[1] - last[1])
    try:
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        det = v1[0] * v2[1] - v1[1] * v2[0]
    except OverflowError:
        return None
    if not math.isfinite(dot) or not math.isfinite(det):
        return None
    return abs(math.atan2(det, dot))


def _double_tap_feasibility(
    curr_delta_ms: float,
    next_delta_ms: float,
    lazy_jump_cs: float,
    hit_window_great_ms: float,
) -> float:
    curr_delta_time = max(1.0, curr_delta_ms)
    next_delta_time = max(1.0, next_delta_ms)
    delta_difference = abs(next_delta_time - curr_delta_time)
    speed_ratio = curr_delta_time / max(curr_delta_time, delta_difference)
    window_ratio = min(1.0, curr_delta_time / hit_window_great_ms) ** 5
    distance_factor = max(0.0, min(1.0, (lazy_jump_cs - NORMALISED_RADIUS * 2) / (NORMALISED_RADIUS - NORMALISED_RADIUS * 2))) ** 2
    return 1.0 - speed_ratio ** (distance_factor * (1.0 - window_ratio))


def _scaled_mean(values: list[float]) -> float:
    scale = max(abs(v) for v in values)
    if scale == 0:
        return 0.0
    return scale * (sum(v / scale for v in values) / len(values))


def _travel_distance_cs(
    geometry: Optional[SliderGeometry],
    signal_version: str,
) -> Optional[float]:
    if geometry is None:
        return 0.0
    if geometry.lazy_travel_distance_cs is None:
        return None
    bonus_count = (
        geometry.span_count
        if signal_version == LEGACY_SIGNAL_VERSION
        else geometry.repeat_count
    )
    return geometry.lazy_travel_distance_cs * max(1.0, bonus_count ** 0.3)


def _percentile(sorted_values: list[float], q: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


class LocalSignalExtractor:
    """Extract a version-selected local signal table and segment summaries."""

    signal_version = SIGNAL_VERSION

    def __init__(self, signal_version: str = SIGNAL_VERSION) -> None:
        # Resolve both contracts eagerly so unsupported versions fail before
        # any beatmap work or partial output is produced.
        signal_schema(signal_version)
        numeric_signals(signal_version)
        self.signal_version = signal_version

    def extract(self, beatmap: Beatmap) -> dict:
        rows = self._extract_rows(beatmap)
        segments = segment_local_signals(
            rows,
            window_ms=SEGMENT_WINDOW_MS,
            signal_version=self.signal_version,
        )
        schema = signal_schema(self.signal_version)
        missing_counts: dict[str, int] = {}
        nonfinite_counts: dict[str, int] = {}
        for row in rows:
            for key in schema:
                if key in ("ls.provenance",):
                    continue
                value = row.get(key)
                if value is None:
                    missing_counts[key] = missing_counts.get(key, 0) + 1
                elif isinstance(value, float) and not math.isfinite(value):
                    nonfinite_counts[key] = nonfinite_counts.get(key, 0) + 1
        return {
            "signal_version": self.signal_version,
            "upstream_repository": "ppy/osu",
            "upstream_commit": UPSTREAM_COMMIT,
            "upstream_difficulty_version": UPSTREAM_DIFFICULTY_VERSION,
            "object_count": len(rows),
            "objects": rows,
            "segments": segments,
            "summary": {
                "segment_count": len(segments),
                "missing_counts": missing_counts,
                "nonfinite_counts": nonfinite_counts,
            },
        }

    def _extract_rows(
        self,
        beatmap: Beatmap,
        _geometries_out: Optional[list[Optional[SliderGeometry]]] = None,
    ) -> list[dict]:
        """Extract per-object rows in .osu file order.

        ``_geometries_out`` is a private reference-layer hook: when supplied,
        the already-computed per-object slider geometries are appended to it
        (file order) so Layer B never needs to re-run the expensive slider
        path machinery.  It does not change any row semantics.
        """

        raw_objects = beatmap.hit_objects
        n = len(raw_objects)
        if n == 0:
            return []

        cs = beatmap.difficulty.get("CircleSize")
        cs_radius = None
        cs_scale = None
        if cs is not None:
            cs_result = circle_size_scale_radius(cs)
            if cs_result is not None:
                _scale, cs_radius = cs_result
                cs_scale = NORMALISED_RADIUS / cs_radius

        ar = beatmap.difficulty.get("ApproachRate")
        od = beatmap.difficulty.get("OverallDifficulty")
        preempt = approach_rate_preempt_ms(ar)
        fade_in = 400.0 * min(1.0, preempt / 450.0) if preempt is not None else None
        hit_window_great = overall_difficulty_great_window_ms(od)

        starts = [(float(obj.x), float(obj.y)) for obj in raw_objects]
        times = [float(obj.time_ms) for obj in raw_objects]

        geometries: list[Optional[SliderGeometry]] = []
        for obj in raw_objects:
            if obj.object_type == "slider":
                geometries.append(
                    _build_geometry(
                        beatmap,
                        obj,
                        (float(obj.x), float(obj.y)),
                        cs_radius,
                        signal_version=self.signal_version,
                    )
                )
            else:
                geometries.append(None)
        if _geometries_out is not None:
            _geometries_out.extend(geometries)

        end_times: list[float] = []
        for idx, obj in enumerate(raw_objects):
            geometry = geometries[idx]
            if obj.object_type == "slider":
                end_times.append(times[idx] + geometry.duration_ms if geometry is not None and geometry.duration_ms is not None else times[idx])
            elif obj.object_type == "spinner":
                end_times.append(float(obj.spinner_end_ms) if obj.spinner_end_ms is not None else times[idx])
            else:
                end_times.append(times[idx])

        time_sorted_indices = sorted(range(n), key=lambda idx: (times[idx], idx))
        time_sorted_rank = [0] * n
        for rank, idx in enumerate(time_sorted_indices):
            time_sorted_rank[idx] = rank

        rows: list[dict] = []
        for i in range(n):
            obj = raw_objects[i]
            start = starts[i]
            geometry = geometries[i]
            provenance: list[str] = []

            if i == 0:
                provenance.append("no_previous")

            row: dict[str, Any] = {
                "ls.original_index": i,
                "ls.time_sorted_index": time_sorted_rank[i],
                "ls.object_type": obj.object_type,
                "ls.start_time_ms": times[i],
                "ls.end_time_ms": end_times[i],
                "ls.preempt_ms": preempt,
                "ls.fade_in_ms": fade_in,
                "ls.hit_window_great_ms": hit_window_great,
                "ls.radius_px": cs_radius,
                "ls.cs_scale": cs_scale,
            }
            if ar is None:
                provenance.append("ar_missing")
            if od is None:
                provenance.append("od_missing")
            if cs is None:
                provenance.append("cs_missing")

            # ---- timing ---------------------------------------------------
            if i == 0:
                row["ls.delta_time_ms"] = None
                row["ls.adjusted_delta_time_ms"] = None
                row["ls.last_object_end_delta_time_ms"] = None
            else:
                delta = times[i] - times[i - 1]
                row["ls.delta_time_ms"] = delta
                adjusted = max(delta, MIN_DELTA_TIME)
                row["ls.adjusted_delta_time_ms"] = adjusted
                if i == 1:
                    row["ls.last_object_end_delta_time_ms"] = adjusted
                else:
                    row["ls.last_object_end_delta_time_ms"] = max(times[i] - end_times[i - 1], MIN_DELTA_TIME)

            # ---- slider-specific raw geometry -----------------------------
            if geometry is not None:
                row["ls.slider_duration_ms"] = geometry.duration_ms
                if self.signal_version != LEGACY_SIGNAL_VERSION:
                    row["ls.slider_repeat_count"] = geometry.repeat_count
                    row["ls.slider_single_span_duration_ms"] = geometry.single_span_duration_ms
                    row["ls.slider_total_duration_ms"] = geometry.total_duration_ms
                row["ls.slider_velocity_px_per_ms"] = geometry.velocity_px_per_ms
                row["ls.slider_path_distance_px"] = (
                    geometry.path.distance if geometry.path is not None else None
                )
                row["ls.slider_span_count"] = geometry.span_count
                row["ls.slider_tick_count"] = sum(1 for e in geometry.nested if e.kind == "tick") if geometry.nested else None
                row["ls.slider_nested_object_count"] = len(geometry.nested) if geometry.nested else None
                row["ls.travel_distance_cs_normalised"] = _travel_distance_cs(
                    geometry,
                    self.signal_version,
                )
                row["ls.travel_time_ms"] = (
                    max(geometry.lazy_travel_time_ms, MIN_DELTA_TIME)
                    if geometry.lazy_travel_time_ms is not None
                    else None
                )
                row["ls.lazy_travel_time_ms"] = geometry.lazy_travel_time_ms
                row["ls.lazy_travel_distance_cs_normalised"] = geometry.lazy_travel_distance_cs
                row["ls.lazy_end_position_x_px"] = (
                    geometry.lazy_end_position[0] if geometry.lazy_end_position is not None else None
                )
                row["ls.lazy_end_position_y_px"] = (
                    geometry.lazy_end_position[1] if geometry.lazy_end_position is not None else None
                )
                if geometry.last_real_tick_reordered:
                    provenance.append("last_real_tick_reordered")
                if geometry.provenance:
                    provenance.extend(geometry.provenance)
            else:
                row["ls.slider_duration_ms"] = None
                if self.signal_version != LEGACY_SIGNAL_VERSION:
                    row["ls.slider_repeat_count"] = None
                    row["ls.slider_single_span_duration_ms"] = None
                    row["ls.slider_total_duration_ms"] = None
                row["ls.slider_velocity_px_per_ms"] = None
                row["ls.slider_path_distance_px"] = None
                row["ls.slider_span_count"] = None
                row["ls.slider_tick_count"] = None
                row["ls.slider_nested_object_count"] = None
                row["ls.travel_distance_cs_normalised"] = 0.0
                row["ls.travel_time_ms"] = 0.0
                row["ls.lazy_travel_time_ms"] = 0.0
                row["ls.lazy_travel_distance_cs_normalised"] = 0.0
                row["ls.lazy_end_position_x_px"] = None
                row["ls.lazy_end_position_y_px"] = None

            # ---- distances / angles / double-tap --------------------------
            spinner_context = obj.object_type == "spinner" or (i > 0 and raw_objects[i - 1].object_type == "spinner")
            row["ls.spinner_context"] = spinner_context
            row["ls.jump_distance_raw_px"] = None
            row["ls.jump_distance_cs_normalised"] = None
            row["ls.lazy_jump_distance_cs_normalised"] = None
            row["ls.minimum_jump_distance_cs_normalised"] = None
            row["ls.minimum_jump_time_ms"] = None
            row["ls.slider_aware_angle_rad"] = None
            row["ls.normalised_vector_angle_rad"] = None
            row["ls.double_tap_feasibility"] = None

            if i > 0:
                adjusted = row["ls.adjusted_delta_time_ms"]
                row["ls.minimum_jump_time_ms"] = adjusted
                if spinner_context:
                    row["ls.jump_distance_raw_px"] = 0.0
                    row["ls.jump_distance_cs_normalised"] = 0.0
                    row["ls.lazy_jump_distance_cs_normalised"] = 0.0
                    row["ls.minimum_jump_distance_cs_normalised"] = 0.0
                    if obj.object_type == "spinner":
                        provenance.append("current_is_spinner")
                    if raw_objects[i - 1].object_type == "spinner":
                        provenance.append("previous_is_spinner")
                else:
                    previous = starts[i - 1]
                    jump_raw = _safe_hypot(start[0] - previous[0], start[1] - previous[1])
                    if jump_raw is None:
                        provenance.append("jump_distance_nonfinite")
                    row["ls.jump_distance_raw_px"] = jump_raw
                    last_geometry = geometries[i - 1]
                    last_cursor = previous
                    if last_geometry is not None and last_geometry.lazy_end_position is not None:
                        last_cursor = last_geometry.lazy_end_position
                    lazy_jump_raw = _safe_hypot(start[0] - last_cursor[0], start[1] - last_cursor[1])
                    if lazy_jump_raw is None:
                        provenance.append("lazy_jump_distance_nonfinite")
                    jump_cs = jump_raw * cs_scale if (jump_raw is not None and cs_scale is not None) else None
                    lazy_jump_cs = lazy_jump_raw * cs_scale if (lazy_jump_raw is not None and cs_scale is not None) else None
                    row["ls.jump_distance_cs_normalised"] = jump_cs
                    row["ls.lazy_jump_distance_cs_normalised"] = lazy_jump_cs
                    row["ls.minimum_jump_distance_cs_normalised"] = lazy_jump_cs
                    if cs_scale is None:
                        provenance.append("cs_missing_for_distance_scale")

                    if last_geometry is not None and last_geometry.tail_position is not None:
                        last_travel_time = (
                            max(last_geometry.lazy_travel_time_ms, MIN_DELTA_TIME)
                            if last_geometry.lazy_travel_time_ms is not None
                            else None
                        )
                        if last_travel_time is None:
                            provenance.append("minimum_jump_time_previous_slider_unknown")
                        else:
                            row["ls.minimum_jump_time_ms"] = max(adjusted - last_travel_time, MIN_DELTA_TIME)
                        tail_jump_raw = _safe_hypot(start[0] - last_geometry.tail_position[0], start[1] - last_geometry.tail_position[1])
                        tail_jump_cs = tail_jump_raw * cs_scale if (tail_jump_raw is not None and cs_scale is not None) else None
                        if lazy_jump_cs is not None and tail_jump_cs is not None:
                            row["ls.minimum_jump_distance_cs_normalised"] = max(
                                0.0,
                                min(
                                    lazy_jump_cs - (MAXIMUM_SLIDER_RADIUS - ASSUMED_SLIDER_RADIUS),
                                    tail_jump_cs - MAXIMUM_SLIDER_RADIUS,
                                ),
                            )
                        elif tail_jump_cs is None and lazy_jump_cs is not None:
                            row["ls.minimum_jump_distance_cs_normalised"] = None
                            provenance.append("minimum_jump_distance_tail_unknown")

                    # angle block
                    if i >= 2 and raw_objects[i - 2].object_type != "spinner":
                        last_last_geometry = geometries[i - 2]
                        angle_last_cursor = last_cursor
                        previous_travel = _travel_distance_cs(
                            last_geometry,
                            self.signal_version,
                        )
                        if previous_travel is not None and previous_travel > 0:
                            angle_last_cursor = previous
                        last_last_cursor = (
                            last_last_geometry.lazy_end_position
                            if last_last_geometry is not None and last_last_geometry.lazy_end_position is not None
                            else starts[i - 2]
                        )
                        angle = _calculate_angle(start, angle_last_cursor, last_last_cursor)
                        slider_angle: Optional[float] = None
                        slider_angle_last = (
                            last_geometry.lazy_end_position
                            if last_geometry is not None and last_geometry.lazy_end_position is not None
                            else previous
                        )
                        slider_angle_last_last = last_last_cursor
                        if previous_travel is not None and previous_travel > 0:
                            if len(last_geometry.nested) >= 2:
                                second_last = last_geometry.nested[-2]
                                slider_angle_last_last = second_last.position
                            else:
                                provenance.append("slider_second_last_nested_missing")
                        slider_angle = _calculate_angle(start, slider_angle_last, slider_angle_last_last)
                        if angle is not None and slider_angle is not None:
                            row["ls.slider_aware_angle_rad"] = min(angle, slider_angle)
                        elif angle is None:
                            provenance.append("plain_angle_nonfinite")
                        elif slider_angle is None:
                            provenance.append("slider_angle_nonfinite")
                        v = (start[0] - angle_last_cursor[0], start[1] - angle_last_cursor[1])
                        if math.isfinite(v[0]) and math.isfinite(v[1]):
                            row["ls.normalised_vector_angle_rad"] = math.atan2(abs(v[1]), abs(v[0]))
                        else:
                            provenance.append("normalised_vector_angle_nonfinite")

                    # double-tap feasibility
                    if hit_window_great is None:
                        provenance.append("od_missing_for_double_tap")
                    elif i + 1 < n:
                        lazy_jump_for_dt = row["ls.lazy_jump_distance_cs_normalised"]
                        if lazy_jump_for_dt is None:
                            provenance.append("double_tap_lazy_jump_unknown")
                        else:
                            row["ls.double_tap_feasibility"] = _double_tap_feasibility(
                                delta,
                                times[i + 1] - times[i],
                                lazy_jump_for_dt,
                                hit_window_great,
                            )
                    else:
                        row["ls.double_tap_feasibility"] = 0.0

            row["ls.provenance"] = tuple(dict.fromkeys(provenance))
            rows.append(row)

        return rows


def segment_local_signals(
    rows: list[dict],
    window_ms: float = SEGMENT_WINDOW_MS,
    signal_version: str = SIGNAL_VERSION,
) -> list[dict]:
    """Fixed-time-window segment summaries (mean/p90/max per numeric signal)."""

    if not rows:
        return []
    ordered = sorted(rows, key=lambda r: (r["ls.start_time_ms"], r["ls.original_index"]))
    start = ordered[0]["ls.start_time_ms"]
    end = max(r["ls.end_time_ms"] for r in ordered)
    buckets: dict[int, list[int]] = {}
    for pos, row in enumerate(ordered):
        bucket = int((row["ls.start_time_ms"] - start) // window_ms)
        buckets.setdefault(bucket, []).append(pos)
    segments: list[dict] = []
    for bucket in sorted(buckets):
        indices = buckets[bucket]
        window_start = start + bucket * window_ms
        window_end = min(window_start + window_ms, end)
        members = [ordered[idx] for idx in indices]
        aggregates: dict[str, dict[str, float]] = {}
        for name in numeric_signals(signal_version):
            values = [
                float(m[name])
                for m in members
                if isinstance(m.get(name), (int, float)) and math.isfinite(float(m[name]))
            ]
            if not values:
                continue
            sorted_values = sorted(values)
            aggregates[name] = {
                "mean": _scaled_mean(values),
                "p90": _percentile(sorted_values, 0.90),
                "max": sorted_values[-1],
            }
        segments.append(
            {
                "start_ms": window_start,
                "end_ms": window_end,
                "start_idx": indices[0],
                "end_idx": indices[-1] + 1,
                "object_count": len(members),
                "aggregates": aggregates,
            }
        )
    return segments


__all__ = ["LocalSignalExtractor", "segment_local_signals", "SEGMENT_WINDOW_MS"]
