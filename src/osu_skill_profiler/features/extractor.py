"""Deterministic feature extractor.

Features are observable measurements, not skill judgements. Every feature has
a stable name, a documented unit, a schema entry and deterministic output.
No ML is involved anywhere in this module.
"""

from __future__ import annotations

import math

from ..parser.normalized import NormalizedBeatmap, NormalizedObject
from .stats import describe, percentile, shannon_entropy_bits

BURST_250_MS = 250.0
BURST_125_MS = 125.0
RATE_WINDOW_MS = 1000.0
SECTION_WINDOW_MS = 5000.0
SHARP_ANGLE_DEG = 60.0
DIRECTION_CHANGE_DEG = 90.0

_DIFFICULTY_FIELDS = (
    ("AR", "ApproachRate"),
    ("OD", "OverallDifficulty"),
    ("CS", "CircleSize"),
    ("HP", "HPDrainRate"),
    ("SliderMultiplier", "SliderMultiplier"),
    ("SliderTickRate", "SliderTickRate"),
)


def _json_safe(value):
    """Map non-finite floats to None so feature output is always JSON-safe."""

    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _deltas(objects: tuple[NormalizedObject, ...]) -> list[float]:
    return [obj.delta_time_ms for obj in objects[1:] if obj.delta_time_ms is not None]


def _burst_metrics(objects: tuple[NormalizedObject, ...], threshold: float) -> dict:
    # Rebuild runs against object indices so durations are exact.
    durations: list[float] = []
    lengths: list[int] = []
    i = 1
    while i < len(objects):
        if objects[i].delta_time_ms is not None and objects[i].delta_time_ms <= threshold:
            start_idx = i - 1
            length = 1
            while i < len(objects) and objects[i].delta_time_ms is not None and objects[i].delta_time_ms <= threshold:
                length += 1
                i += 1
            if length >= 2:
                lengths.append(length)
                durations.append(objects[i - 1].time_ms - objects[start_idx].time_ms)
        else:
            i += 1
    return {
        "count": len(lengths),
        "max_len": max(lengths, default=0),
        "longest_duration_ms": max(durations, default=0.0),
    }


def _max_rate_1s(objects: tuple[NormalizedObject, ...]) -> float:
    times = [obj.time_ms for obj in objects]
    times.sort()
    maximum = 0
    end = 0
    for start_idx, start in enumerate(times):
        if end < start_idx:
            end = start_idx
        while end < len(times) and times[end] < start + RATE_WINDOW_MS:
            end += 1
        maximum = max(maximum, end - start_idx)
    return float(maximum)


def _rhythm_bucket(delta_ms: float) -> int:
    return min(15, int(math.floor(math.log2(max(delta_ms, 1.0) / 25.0))))


class FeatureExtractor:
    """Extracts a flat, deterministic feature dict from a NormalizedBeatmap."""

    feature_version = "0.1.0"

    def extract(self, nmap: NormalizedBeatmap) -> dict:
        objects = nmap.objects
        features: dict = {}

        # ---- temporal -----------------------------------------------------
        deltas = _deltas(objects)
        deltas_desc = describe(deltas)
        features["temporal.object_count"] = float(len(objects))
        map_start = objects[0].time_ms
        map_end = max((obj.end_time_ms() for obj in objects), default=map_start)
        features["temporal.map_duration_ms"] = map_end - map_start
        duration_s = max((map_end - map_start) / 1000.0, 1e-9)
        features["temporal.density_objects_per_s"] = len(objects) / duration_s
        bpm_values = [obj.local_bpm for obj in objects]
        for key, value in describe(bpm_values).items():
            features[f"temporal.bpm_{key}"] = value
        for key, value in deltas_desc.items():
            features[f"temporal.delta_time_ms_{key}"] = value
        ratios = []
        for prev, current in zip(deltas, deltas[1:]):
            if prev > 0:
                ratios.append(current / prev)
        features["temporal.interval_ratio_mean"] = describe(ratios)["mean"]
        buckets = [_rhythm_bucket(delta) for delta in deltas]
        bucket_counts: dict[int, int] = {}
        for bucket in buckets:
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        features["temporal.rhythm_entropy_bits"] = shannon_entropy_bits(bucket_counts.values())
        features["temporal.interval_diversity"] = (
            len(bucket_counts) / len(buckets) if buckets else None
        )
        for label, threshold in (("250ms", BURST_250_MS), ("125ms", BURST_125_MS)):
            metrics = _burst_metrics(objects, threshold)
            features[f"temporal.burst_count_{label}"] = float(metrics["count"])
            features[f"temporal.burst_max_len_{label}"] = float(metrics["max_len"])
            features[f"temporal.burst_longest_duration_ms_{label}"] = metrics["longest_duration_ms"]
        dense = _burst_metrics(objects, BURST_250_MS)
        features["temporal.dense_section_count"] = float(dense["count"])
        features["temporal.longest_dense_section_ms"] = dense["longest_duration_ms"]
        features["temporal.object_rate_max_1s"] = _max_rate_1s(objects)

        # ---- spatial ------------------------------------------------------
        distances = [obj.distance_from_previous for obj in objects[1:]]
        velocities = [obj.movement_velocity_norm_per_s for obj in objects[1:]]
        for key, value in describe(distances).items():
            features[f"spatial.distance_norm_{key}"] = value
        for key, value in describe(velocities).items():
            features[f"spatial.velocity_norm_per_s_{key}"] = value
        accelerations: list[float] = []
        for idx in range(2, len(objects)):
            delta = objects[idx].delta_time_ms
            if (
                delta
                and objects[idx].movement_velocity_norm_per_s is not None
                and objects[idx - 1].movement_velocity_norm_per_s is not None
            ):
                try:
                    accelerations.append(
                        (objects[idx].movement_velocity_norm_per_s - objects[idx - 1].movement_velocity_norm_per_s)
                        / (delta / 1000.0)
                    )
                except OverflowError:
                    pass
        features["spatial.acceleration_norm_per_s2_mean"] = describe(accelerations)["mean"]
        features["spatial.acceleration_norm_per_s2_max"] = describe(accelerations)["max"]
        angles = [obj.angle_deg for obj in objects if obj.angle_deg is not None]
        for key, value in describe(angles).items():
            features[f"spatial.angle_deg_{key}"] = value
        features["spatial.sharp_angle_ratio_lt_60"] = (
            sum(1 for angle in angles if angle < SHARP_ANGLE_DEG) / len(angles) if angles else None
        )
        features["spatial.direction_change_ratio_ge_90"] = (
            sum(1 for angle in angles if angle >= DIRECTION_CHANGE_DEG) / len(angles) if angles else None
        )
        path_length = sum(d for d in distances if d is not None)
        if path_length > 0 and len(objects) >= 2:
            net = math.hypot(
                objects[-1].x_norm - objects[0].x_norm,
                objects[-1].y_norm - objects[0].y_norm,
            )
            features["spatial.net_displacement_ratio"] = net / path_length
        else:
            features["spatial.net_displacement_ratio"] = None
        features["spatial.x_range_norm"] = (
            max(obj.x_norm for obj in objects) - min(obj.x_norm for obj in objects)
            if objects
            else None
        )
        features["spatial.y_range_norm"] = (
            max(obj.y_norm for obj in objects) - min(obj.y_norm for obj in objects)
            if objects
            else None
        )

        # ---- slider -------------------------------------------------------
        sliders = [obj for obj in objects if obj.raw.object_type == "slider"]
        features["slider.slider_ratio"] = len(sliders) / len(objects) if objects else None
        slider_durations = [obj.slider_duration_ms for obj in sliders]
        for key, value in describe(slider_durations).items():
            features[f"slider.duration_ms_{key}"] = value
        slider_velocities = [obj.slider_velocity_px_per_s for obj in sliders]
        for key, value in describe(slider_velocities).items():
            features[f"slider.velocity_px_per_s_{key}"] = value
        slider_lengths = [obj.raw.slider_pixel_length for obj in sliders if obj.raw.slider_pixel_length is not None]
        for key, value in describe(slider_lengths).items():
            features[f"slider.length_px_{key}"] = value
        slider_repeats = [float(obj.raw.slider_slides or 0) for obj in sliders]
        features["slider.repeats_total"] = sum(slider_repeats)
        features["slider.repeats_max"] = max(slider_repeats, default=0.0)
        transitions = sum(
            1
            for idx in range(1, len(objects))
            if objects[idx].raw.object_type == "circle" and objects[idx - 1].raw.object_type == "slider"
        )
        features["slider.to_circle_transition_count"] = float(transitions)

        # ---- section (fixed-window aggregate) ------------------------------
        features.update(self._section_features(objects))

        # ---- difficulty context -------------------------------------------
        difficulty = nmap.beatmap.difficulty
        for feature_key, source_key in _DIFFICULTY_FIELDS:
            features[f"difficulty.{feature_key}"] = difficulty.get(source_key)

        return {key: _json_safe(value) for key, value in features.items()}

    def _section_features(self, objects: tuple[NormalizedObject, ...]) -> dict:
        if not objects:
            return {
                "section.window_count": 0,
                "section.density_per_s_mean": None,
                "section.density_per_s_p95": None,
                "section.density_per_s_max": None,
                "section.duration_weighted_density_per_s": None,
                "section.velocity_norm_per_s_p90": None,
                "section.angle_deg_p90": None,
                "section.peak_density_window_start_ms": None,
            }
        start = objects[0].time_ms
        end = max(obj.end_time_ms() for obj in objects)
        # Bucket objects by fixed-window index computed from the first object's
        # time. This bounds the number of windows by object count and stays
        # correct even when a map contains absurdly large timestamps.
        buckets: dict[int, list] = {}
        for obj in objects:
            bucket = int((obj.time_ms - start) // SECTION_WINDOW_MS)
            buckets.setdefault(bucket, []).append(obj)
        windows: list[dict] = []
        for bucket in sorted(buckets):
            window_start = start + bucket * SECTION_WINDOW_MS
            window_end = min(window_start + SECTION_WINDOW_MS, end)
            members = buckets[bucket]
            duration_s = max((window_end - window_start) / 1000.0, 1e-9)
            densities = [obj.local_density_per_s for obj in members]
            velocities = [obj.movement_velocity_norm_per_s for obj in members if obj.movement_velocity_norm_per_s is not None]
            angles = [obj.angle_deg for obj in members if obj.angle_deg is not None]
            windows.append(
                {
                    "start_ms": window_start,
                    "duration_s": duration_s,
                    "density_per_s": len(members) / duration_s,
                    "velocity_p90": percentile(sorted(velocities), 0.90) if velocities else None,
                    "angle_p90": percentile(sorted(angles), 0.90) if angles else None,
                }
            )
        if not windows:
            return {
                "section.window_count": 0,
                "section.density_per_s_mean": None,
                "section.density_per_s_p95": None,
                "section.density_per_s_max": None,
                "section.duration_weighted_density_per_s": None,
                "section.velocity_norm_per_s_p90": None,
                "section.angle_deg_p90": None,
                "section.peak_density_window_start_ms": None,
            }
        densities = sorted(w["density_per_s"] for w in windows)
        total_duration = sum(w["duration_s"] for w in windows)
        peak = max(windows, key=lambda w: (w["density_per_s"], -w["start_ms"]))
        return {
            "section.window_count": len(windows),
            "section.density_per_s_mean": sum(densities) / len(densities),
            "section.density_per_s_p95": percentile(densities, 0.95),
            "section.density_per_s_max": densities[-1],
            "section.duration_weighted_density_per_s": (
                sum(w["density_per_s"] * w["duration_s"] for w in windows) / total_duration
            ),
            "section.velocity_norm_per_s_p90": percentile(
                sorted(v for v in (w["velocity_p90"] for w in windows) if v is not None), 0.90
            ),
            "section.angle_deg_p90": percentile(
                sorted(a for a in (w["angle_p90"] for w in windows) if a is not None), 0.90
            ),
            "section.peak_density_window_start_ms": peak["start_ms"],
        }
