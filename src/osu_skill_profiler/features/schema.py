"""Versioned machine-readable schemas for deterministic Feature layers."""

from __future__ import annotations


def _describe_entry(unit: str, description: str, level: str = "map_and_segment") -> dict:
    return {
        "unit": unit,
        "level": level,
        "description": description,
    }


def _expand(name: str, unit: str, description: str, level: str = "map_and_segment") -> dict:
    return {
        f"{name}_mean": _describe_entry(unit, f"{description} (mean)", level),
        f"{name}_std": _describe_entry(unit, f"{description} (standard deviation)", level),
        f"{name}_p50": _describe_entry(unit, f"{description} (p50)", level),
        f"{name}_p75": _describe_entry(unit, f"{description} (p75)", level),
        f"{name}_p90": _describe_entry(unit, f"{description} (p90)", level),
        f"{name}_p95": _describe_entry(unit, f"{description} (p95)", level),
        f"{name}_max": _describe_entry(unit, f"{description} (max)", level),
        f"{name}_min": _describe_entry(unit, f"{description} (min)", level),
    }


LEGACY_FEATURE_VERSION = "0.1.0"
FEATURE_VERSION = "0.2.0"


FEATURE_SCHEMA_V01: dict = {
    **_expand("temporal.delta_time_ms", "ms", "gap between consecutive hit object start times"),
    **_expand("temporal.bpm", "beats/min", "local BPM at each hit object"),
    "temporal.object_count": _describe_entry("count", "number of hit objects"),
    "temporal.map_duration_ms": _describe_entry("ms", "first object start to last object end"),
    "temporal.density_objects_per_s": _describe_entry("objects/s", "object count divided by map duration"),
    "temporal.interval_ratio_mean": _describe_entry("ratio", "mean ratio of consecutive delta times"),
    "temporal.rhythm_entropy_bits": _describe_entry("bits", "Shannon entropy of quantized delta-time buckets"),
    "temporal.interval_diversity": _describe_entry("ratio", "unique quantized intervals divided by interval count"),
    "temporal.burst_count_250ms": _describe_entry("count", "runs of >=2 gaps <= 250ms"),
    "temporal.burst_max_len_250ms": _describe_entry("count", "longest run of gaps <= 250ms"),
    "temporal.burst_longest_duration_ms_250ms": _describe_entry("ms", "longest burst duration (250ms threshold)"),
    "temporal.burst_count_125ms": _describe_entry("count", "runs of >=2 gaps <= 125ms"),
    "temporal.burst_max_len_125ms": _describe_entry("count", "longest run of gaps <= 125ms"),
    "temporal.burst_longest_duration_ms_125ms": _describe_entry("ms", "longest burst duration (125ms threshold)"),
    "temporal.dense_section_count": _describe_entry("count", "dense sections (gaps <= 250ms)"),
    "temporal.longest_dense_section_ms": _describe_entry("ms", "longest continuous dense section"),
    "temporal.object_rate_max_1s": _describe_entry("objects/s", "maximum objects in any 1s window"),
    **_expand("spatial.distance_norm", "normalized units", "Euclidean distance to previous object on 512x384 field"),
    **_expand("spatial.velocity_norm_per_s", "normalized units/s", "distance divided by delta time"),
    "spatial.acceleration_norm_per_s2_mean": _describe_entry("normalized units/s^2", "mean velocity change rate"),
    "spatial.acceleration_norm_per_s2_max": _describe_entry("normalized units/s^2", "maximum velocity change rate"),
    **_expand("spatial.angle_deg", "degrees", "turn angle at object between incoming and outgoing vectors"),
    "spatial.sharp_angle_ratio_lt_60": _describe_entry("ratio", "fraction of angles below 60 degrees"),
    "spatial.direction_change_ratio_ge_90": _describe_entry("ratio", "fraction of angles at or above 90 degrees"),
    "spatial.net_displacement_ratio": _describe_entry("ratio", "start-to-end distance divided by path length"),
    "spatial.x_range_norm": _describe_entry("normalized units", "horizontal bounding-box extent"),
    "spatial.y_range_norm": _describe_entry("normalized units", "vertical bounding-box extent"),
    "slider.slider_ratio": _describe_entry("ratio", "sliders divided by all objects"),
    **_expand("slider.duration_ms", "ms", "estimated slider duration from pixel length, SV and BPM"),
    **_expand("slider.velocity_px_per_s", "px/s", "slider pixel length divided by duration"),
    **_expand("slider.length_px", "px", "slider pixel length"),
    "slider.repeats_total": _describe_entry("count", "sum of slider repeat counts"),
    "slider.repeats_max": _describe_entry("count", "maximum slider repeat count"),
    "slider.to_circle_transition_count": _describe_entry("count", "circles immediately following a slider"),
    "section.window_count": _describe_entry("count", "non-empty fixed windows used"),
    "section.density_per_s_mean": _describe_entry("objects/s", "mean window density"),
    "section.density_per_s_p95": _describe_entry("objects/s", "p95 window density"),
    "section.density_per_s_max": _describe_entry("objects/s", "peak window density"),
    "section.duration_weighted_density_per_s": _describe_entry("objects/s", "window density weighted by window duration"),
    "section.velocity_norm_per_s_p90": _describe_entry("normalized units/s", "p90 of window p90 velocities"),
    "section.angle_deg_p90": _describe_entry("degrees", "p90 of window p90 angles"),
    "section.peak_density_window_start_ms": _describe_entry("ms", "start time of the densest window"),
    "difficulty.AR": _describe_entry("osu AR", "approach rate", "difficulty_context"),
    "difficulty.OD": _describe_entry("osu OD", "overall difficulty", "difficulty_context"),
    "difficulty.CS": _describe_entry("osu CS", "circle size", "difficulty_context"),
    "difficulty.HP": _describe_entry("osu HP", "hp drain rate", "difficulty_context"),
    "difficulty.SliderMultiplier": _describe_entry("multiplier", "slider velocity multiplier", "difficulty_context"),
    "difficulty.SliderTickRate": _describe_entry("ticks/beat", "slider tick rate", "difficulty_context"),
}


# Feature v0.2 keeps every unaffected v0.1 field, corrects total slider
# duration through the extractor, and replaces the two historically misnamed
# repeat fields with unambiguous repeat/span counts.
FEATURE_SCHEMA_V02: dict = {
    key: dict(value)
    for key, value in FEATURE_SCHEMA_V01.items()
    if key not in ("slider.repeats_total", "slider.repeats_max")
}
for _key, _entry in FEATURE_SCHEMA_V02.items():
    if _key.startswith("slider.duration_ms_"):
        _entry["description"] = _entry["description"].replace(
            "estimated slider duration",
            "total slider duration across all spans",
        )
FEATURE_SCHEMA_V02.update(
    {
        "slider.repeat_count_total": _describe_entry(
            "count", "sum of true slider repeat counts (span_count - 1)"
        ),
        "slider.repeat_count_max": _describe_entry(
            "count", "maximum true slider repeat count"
        ),
        "slider.span_count_total": _describe_entry(
            "count", "sum of slider span counts from the .osu slides field"
        ),
        "slider.span_count_max": _describe_entry(
            "count", "maximum slider span count"
        ),
    }
)

# Public alias is the corrected current contract. Historical callers must ask
# for FEATURE_SCHEMA_V01 explicitly.
FEATURE_SCHEMA = FEATURE_SCHEMA_V02


def feature_schema(version: str) -> dict:
    if version == LEGACY_FEATURE_VERSION:
        return FEATURE_SCHEMA_V01
    if version == FEATURE_VERSION:
        return FEATURE_SCHEMA_V02
    raise ValueError(f"unsupported feature version: {version}")


__all__ = [
    "FEATURE_SCHEMA",
    "FEATURE_SCHEMA_V01",
    "FEATURE_SCHEMA_V02",
    "FEATURE_VERSION",
    "LEGACY_FEATURE_VERSION",
    "feature_schema",
]
