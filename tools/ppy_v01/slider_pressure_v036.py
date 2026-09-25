"""Experimental v0.36 Slider pressure discovery for the real-world corpus.

This module is deliberately an evidence extractor.  It does not create a
Slider pressure star value and it does not change any of the nine formal map
axes.  For every parsed Slider it reports the ppy-style geometry, a minimum
cursor trajectory under the follow-circle allowance, and the physical
quantities used to select real-world review candidates.

The trajectory is the same conservative question used by the preceding
mandatory-follow work, with one numerical refinement:

    keep the cursor still while it remains inside the follow allowance;
    once it would leave the allowance, move only the minimum distance needed
    to put it back on the allowance boundary.

v0.36 integrates the portion of each sampled ball segment that is outside the
allowance boundary instead of assigning the whole interval to the active
episode.  This reduces sample-step bias in active-follow fraction and episode
duration while leaving endpoint correction, required velocity, support gates,
and the no-scalar admission contract unchanged.

All pressure fields remain a vector.  Selection is done with support gates
that have a geometric meaning, never with a weighted pressure scalar.
"""

from __future__ import annotations

import math
import zipfile
import sys
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

# Keep the source package runnable directly from a clean checkout, matching
# the other ppy_v01 command-line tools in this distribution.
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(_PACKAGE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT / "src"))

from osu_skill_profiler.parser.model import Beatmap, HitObject
from osu_skill_profiler.parser.osu_parser import parse_osu, parse_osu_file
from osu_skill_profiler.signals import SIGNAL_VERSION
from osu_skill_profiler.signals.slider import (
    NORMALISED_RADIUS,
    _build_geometry,
    circle_size_scale_radius,
)
from osu_skill_profiler.slider_semantics import canonical_slider_counts


RUNTIME_VERSION = "v036_continuous_boundary_pressure_discovery"
DISCOVERY_VERSION = "0.36.0"

# These are support gates, not weights.  A candidate must have both a real
# amount of forced cursor movement and a sustained forced-follow episode.
MANDATORY_TRAVEL_GATE_NORM = 50.0
LONGEST_ACTIVE_BALL_PATH_GATE_NORM = 100.0

# ppy's ordinary follow allowance is 90 normalised px in the existing signal
# layer.  Repeat endpoint acquisition uses the 50 px radius from the same
# layer; endpoint counts remain evidence for the existing Precision lane.
FOLLOW_ALLOWANCE_NORM = 90.0
REPEAT_ALLOWANCE_NORM = NORMALISED_RADIUS

# v0.33 used a dense sampler with a 512 interval guard.  Keep that behaviour,
# while making the requested resolution explicit for corpus reproducibility.
DEFAULT_SAMPLE_STEP_NORM = 2.0
MAX_SAMPLE_INTERVALS = 512

# A lazy-motion negative must be visibly fast while demanding little cursor
# motion.  The thresholds are only a label gate; no scalar is admitted.
LAZY_BALL_VELOCITY_GATE_NORM = 2.0
LAZY_REQUIRED_VELOCITY_CEILING_NORM = 0.19
LAZY_MANDATORY_TRAVEL_FRACTION_CEILING = 0.25
LAZY_ACTIVE_FOLLOW_FRACTION_FLOOR = 0.019


def _finite(value: Any) -> Optional[float]:
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _safe_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    try:
        value = math.hypot(a[0] - b[0], a[1] - b[1])
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _angle_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Return the unsigned turn angle between two non-zero vectors."""

    a_len = math.hypot(a[0], a[1])
    b_len = math.hypot(b[0], b[1])
    if a_len <= 0.0 or b_len <= 0.0:
        return 0.0
    cosine = (a[0] * b[0] + a[1] * b[1]) / (a_len * b_len)
    cosine = max(-1.0, min(1.0, cosine))
    return math.acos(cosine)


def _quantile(values: list[float], probability: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = max(0.0, min(1.0, probability)) * (len(values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


@dataclass(frozen=True)
class _Sample:
    time_ms: float
    position_norm: tuple[float, float]
    ball_path_norm: float
    repeat_boundary: bool = False


@dataclass(frozen=True)
class _Trajectory:
    mandatory_travel_norm: float
    mandatory_travel_fraction: float
    active_follow_fraction: float
    active_follow_duration_ms: float
    longest_active_episode_ball_path_norm: float
    longest_active_episode_duration_ms: float
    mean_slack_fraction: float
    required_cursor_velocity_norm_px_per_ms: float
    residual_steering_25px_rad: float
    residual_steering_50px_rad: float
    active_ball_path_norm: float
    active_episode_count: int
    correction_vectors: tuple[tuple[float, float] | None, ...]


def _sample_count(path_distance_norm: float, sample_step_norm: float) -> int:
    if not math.isfinite(path_distance_norm) or path_distance_norm <= 0:
        return 1
    step = max(0.25, float(sample_step_norm))
    requested = int(math.ceil(path_distance_norm / step))
    # Keep the v0.33 guard: long paths are uniformly downsampled instead of
    # appending a large, artificial final interval.
    return max(1, min(MAX_SAMPLE_INTERVALS, requested))


def _slider_samples(
    geometry: Any,
    obj: HitObject,
    normalisation: float,
    *,
    sample_step_norm: float,
) -> tuple[list[_Sample], float]:
    """Build uniformly timed samples over every slider span."""

    path = geometry.path
    path_distance = _finite(getattr(path, "distance", None))
    span_duration = _finite(getattr(geometry, "single_span_duration_ms", None))
    span_count = int(getattr(geometry, "span_count", 1) or 1)
    if path is None or path_distance is None or path_distance <= 0 or span_duration is None or span_duration <= 0:
        return [], 0.0
    path_distance_norm = path_distance * normalisation
    count = _sample_count(path_distance_norm, sample_step_norm)
    samples: list[_Sample] = []
    start = (float(obj.x), float(obj.y))
    for span in range(span_count):
        reverse = span % 2 == 1
        for index in range(count + 1):
            # The first point of a later span is also the previous span's end.
            # Keep the zero-duration duplicate so the repeat boundary is
            # explicit; the trajectory pass skips that interval and does not
            # turn endpoint acquisition into body pressure.
            fraction = index / count
            progress = 1.0 - fraction if reverse else fraction
            relative = path.position_at(progress)
            absolute = (start[0] + relative[0], start[1] + relative[1])
            position_norm = (absolute[0] * normalisation, absolute[1] * normalisation)
            time_ms = float(obj.time_ms) + span * span_duration + fraction * span_duration
            samples.append(
                _Sample(
                    time_ms=time_ms,
                    position_norm=position_norm,
                    ball_path_norm=path_distance_norm * (span + fraction),
                    repeat_boundary=span > 0 and index == 0,
                )
            )
    return samples, path_distance_norm * span_count


def _residual_turn_for_threshold(
    vectors: list[tuple[float, float] | None],
    threshold: float,
) -> float:
    """Measure the maximum turn inside a correction-distance window.

    v0.34 used ``threshold`` only as a yes/no gate and then summed turns over
    the whole Slider.  That made the 25 px and 50 px fields identical for most
    long corrections.  v0.35 scans every contiguous correction window and
    returns the largest turn accumulated after at least ``threshold`` pixels
    of mandatory correction.  If the full correction path does not reach the
    threshold, the signature stays zero.  The result remains descriptive
    evidence, not an axis value.
    """

    if not vectors or not math.isfinite(threshold) or threshold <= 0.0:
        return 0.0

    # Repeat boundaries separate body spans.  The cursor can reverse along the
    # same path there, but that reversal belongs to endpoint acquisition, not
    # to a continuous body-steering window.
    segments: list[list[tuple[float, float]]] = []
    segment: list[tuple[float, float]] = []
    for vector in vectors:
        if vector is None:
            if segment:
                segments.append(segment)
                segment = []
            continue
        length = math.hypot(vector[0], vector[1])
        if length <= 0.0:
            continue
        segment.append(vector)
    if segment:
        segments.append(segment)

    maximum_turn = 0.0
    for vectors_in_segment in segments:
        lengths = [math.hypot(vector[0], vector[1]) for vector in vectors_in_segment]
        if not lengths or sum(lengths) < threshold:
            continue
        turns_at_index = [0.0]
        for index in range(1, len(vectors_in_segment)):
            turns_at_index.append(
                turns_at_index[-1]
                + _angle_between(vectors_in_segment[index - 1], vectors_in_segment[index])
            )
        cumulative_distance = [0.0]
        for length in lengths:
            cumulative_distance.append(cumulative_distance[-1] + length)
        for start in range(len(lengths)):
            end = bisect_left(cumulative_distance, cumulative_distance[start] + threshold, start + 1)
            if end >= len(cumulative_distance):
                continue
            # ``turns_at_index[k]`` includes the angle entering vector k.  The
            # subtraction excludes the angle before the selected window.
            window_turn = turns_at_index[end - 1] - turns_at_index[start]
            maximum_turn = max(maximum_turn, window_turn)
    return maximum_turn


def _outside_allowance_fraction(
    start: tuple[float, float],
    end: tuple[float, float],
    cursor: tuple[float, float],
    allowance: float,
) -> float:
    """Return the fraction of a linear ball segment outside the allowance.

    The v0.35 endpoint sampler marked an entire interval active whenever the
    endpoint exceeded the follow circle.  With long capped intervals that
    over-counted active path and active duration.  Solve the first boundary
    crossing of ``|start + u*(end-start) - cursor| = allowance`` instead.
    The cursor remains the previous projected position for this interval; the
    endpoint projection itself is deliberately unchanged.
    """

    if not math.isfinite(allowance) or allowance <= 0.0:
        return 1.0
    d0 = _safe_distance(start, cursor)
    d1 = _safe_distance(end, cursor)
    if d1 <= allowance:
        return 0.0
    if d0 > allowance:
        return 1.0
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    qx = start[0] - cursor[0]
    qy = start[1] - cursor[1]
    a = dx * dx + dy * dy
    if not math.isfinite(a) or a <= 1e-18:
        return 1.0 if d1 > allowance else 0.0
    b = 2.0 * (qx * dx + qy * dy)
    c = qx * qx + qy * qy - allowance * allowance
    discriminant = b * b - 4.0 * a * c
    if not math.isfinite(discriminant) or discriminant < 0.0:
        # The endpoint is outside and the segment has no recoverable crossing
        # due to roundoff or a pathological input; fail closed to full active.
        return 1.0
    root = math.sqrt(max(0.0, discriminant))
    candidates = [(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)]
    crossings = [u for u in candidates if math.isfinite(u) and 0.0 <= u <= 1.0]
    if not crossings:
        return 1.0
    crossing = min(crossings)
    return max(0.0, min(1.0, 1.0 - crossing))


def _mandatory_trajectory(
    samples: list[_Sample],
    *,
    total_ball_path_norm: float,
) -> Optional[_Trajectory]:
    if len(samples) < 2 or total_ball_path_norm <= 0:
        return None
    cursor = samples[0].position_norm
    previous_ball = cursor
    previous_time = samples[0].time_ms
    mandatory_travel = 0.0
    active_ball_path = 0.0
    active_duration = 0.0
    slack_time = 0.0
    duration_total = 0.0
    active_episode_count = 0
    current_episode_ball = 0.0
    current_episode_duration = 0.0
    longest_episode_ball = 0.0
    longest_episode_duration = 0.0
    corrections: list[tuple[float, float] | None] = []
    active = False

    for sample in samples[1:]:
        dt = sample.time_ms - previous_time
        ball_step = _safe_distance(sample.position_norm, previous_ball)
        # A repeat boundary is emitted twice by the per-span sampler.  It is
        # a zero-distance endpoint event, not Slider-body travel; skip it even
        # when floating-point span arithmetic leaves a tiny positive dt.
        if sample.repeat_boundary:
            corrections.append(None)
            previous_ball = sample.position_norm
            previous_time = sample.time_ms
            continue
        if not math.isfinite(dt) or dt <= 0:
            previous_ball = sample.position_norm
            previous_time = sample.time_ms
            continue
        allowance = REPEAT_ALLOWANCE_NORM if sample.repeat_boundary else FOLLOW_ALLOWANCE_NORM
        before = _safe_distance(sample.position_norm, cursor)
        correction = max(0.0, before - allowance)
        active_fraction = _outside_allowance_fraction(
            previous_ball,
            sample.position_norm,
            cursor,
            allowance,
        )
        vector = (0.0, 0.0)
        if correction > 0.0 and before > 0.0:
            scale = correction / before
            vector = (
                (sample.position_norm[0] - cursor[0]) * scale,
                (sample.position_norm[1] - cursor[1]) * scale,
            )
            cursor = (cursor[0] + vector[0], cursor[1] + vector[1])
            corrections.append(vector)
        residual = _safe_distance(sample.position_norm, cursor)
        slack_time += max(0.0, allowance - residual) / max(allowance, 1e-9) * dt
        duration_total += dt
        mandatory_travel += correction
        is_active = active_fraction > 1e-9
        if is_active:
            active_ball_step = ball_step * active_fraction
            active_duration_step = dt * active_fraction
            active_ball_path += active_ball_step
            active_duration += active_duration_step
            current_episode_ball += active_ball_step
            current_episode_duration += active_duration_step
            if not active:
                active_episode_count += 1
            active = True
        elif active:
            longest_episode_ball = max(longest_episode_ball, current_episode_ball)
            longest_episode_duration = max(longest_episode_duration, current_episode_duration)
            current_episode_ball = 0.0
            current_episode_duration = 0.0
            active = False
        previous_ball = sample.position_norm
        previous_time = sample.time_ms
    if active:
        longest_episode_ball = max(longest_episode_ball, current_episode_ball)
        longest_episode_duration = max(longest_episode_duration, current_episode_duration)

    if duration_total <= 0:
        return None
    required_velocity = mandatory_travel / duration_total
    return _Trajectory(
        mandatory_travel_norm=mandatory_travel,
        mandatory_travel_fraction=mandatory_travel / max(total_ball_path_norm, 1e-9),
        active_follow_fraction=active_ball_path / max(total_ball_path_norm, 1e-9),
        active_follow_duration_ms=active_duration,
        longest_active_episode_ball_path_norm=longest_episode_ball,
        longest_active_episode_duration_ms=longest_episode_duration,
        mean_slack_fraction=slack_time / duration_total,
        required_cursor_velocity_norm_px_per_ms=required_velocity,
        residual_steering_25px_rad=_residual_turn_for_threshold(corrections, 25.0),
        residual_steering_50px_rad=_residual_turn_for_threshold(corrections, 50.0),
        active_ball_path_norm=active_ball_path,
        active_episode_count=active_episode_count,
        correction_vectors=tuple(corrections),
    )


def _source_identity(beatmap: Beatmap, source_name: str) -> dict[str, Any]:
    return {
        "source": source_name,
        "title": beatmap.metadata.get("Title"),
        "artist": beatmap.metadata.get("Artist"),
        "creator": beatmap.metadata.get("Creator"),
        "version": beatmap.metadata.get("Version"),
        "beatmap_id": beatmap.metadata.get("BeatmapID"),
        "beatmap_set_id": beatmap.metadata.get("BeatmapSetID"),
        "mode": beatmap.mode,
        "difficulty": {
            key: beatmap.difficulty.get(key)
            for key in (
                "ApproachRate",
                "OverallDifficulty",
                "CircleSize",
                "SliderMultiplier",
                "SliderTickRate",
            )
        },
    }


def _metric_row(
    beatmap: Beatmap,
    obj: HitObject,
    slider_index: int,
    source_name: str,
    *,
    sample_step_norm: float,
) -> dict[str, Any]:
    cs = _finite(beatmap.difficulty.get("CircleSize"))
    scale_radius = circle_size_scale_radius(cs)
    if scale_radius is None or scale_radius[1] <= 0:
        return {
            "slider_index": slider_index,
            "start_time_ms": obj.time_ms,
            "start_time": _format_time(obj.time_ms),
            "status": "UNVERIFIED",
            "unverified_reason": "circle_size_missing_or_invalid",
        }
    _scale, radius = scale_radius
    normalisation = NORMALISED_RADIUS / radius
    geometry = _build_geometry(
        beatmap,
        obj,
        (float(obj.x), float(obj.y)),
        radius,
        signal_version=SIGNAL_VERSION,
    )
    provenance = list(geometry.provenance)
    samples, total_ball_path_norm = _slider_samples(
        geometry,
        obj,
        normalisation,
        sample_step_norm=sample_step_norm,
    )
    trajectory = _mandatory_trajectory(samples, total_ball_path_norm=total_ball_path_norm)
    path_distance = _finite(getattr(geometry.path, "distance", None))
    duration = _finite(getattr(geometry, "total_duration_ms", None))
    span_count = int(getattr(geometry, "span_count", 1) or 1)
    if trajectory is None or path_distance is None or duration is None or duration <= 0:
        return {
            "slider_index": slider_index,
            "start_time_ms": obj.time_ms,
            "start_time": _format_time(obj.time_ms),
            "span_count": span_count,
            "status": "UNVERIFIED",
            "unverified_reason": "geometry_or_timing_unavailable",
            "provenance": provenance,
        }
    ball_velocity = total_ball_path_norm / duration
    mandatory_supported = trajectory.mandatory_travel_norm >= MANDATORY_TRAVEL_GATE_NORM
    episode_supported = trajectory.longest_active_episode_ball_path_norm >= LONGEST_ACTIVE_BALL_PATH_GATE_NORM
    support_gate = mandatory_supported and episode_supported
    return {
        "slider_index": slider_index,
        "start_time_ms": round(float(obj.time_ms), 6),
        "end_time_ms": round(float(obj.time_ms + duration), 6),
        "start_time": _format_time(obj.time_ms),
        "end_time": _format_time(obj.time_ms + duration),
        "x": obj.x,
        "y": obj.y,
        "curve_type": obj.slider_curve_type,
        "span_count": span_count,
        "repeat_count": canonical_slider_counts(obj.slider_slides).repeat_count,
        "path_distance_raw_px": round(path_distance, 6),
        "duration_ms": round(duration, 6),
        "slider_ball_velocity_norm_px_per_ms": round(ball_velocity, 9),
        "slider_ball_velocity_raw_px_per_ms": round(path_distance * span_count / duration, 9),
        "mandatory_cursor_travel_norm_px": round(trajectory.mandatory_travel_norm, 6),
        "mandatory_travel_fraction": round(trajectory.mandatory_travel_fraction, 9),
        "active_follow_fraction": round(trajectory.active_follow_fraction, 9),
        "active_follow_duration_ms": round(trajectory.active_follow_duration_ms, 6),
        "longest_active_episode_ball_path_norm_px": round(trajectory.longest_active_episode_ball_path_norm, 6),
        "longest_active_episode_duration_ms": round(trajectory.longest_active_episode_duration_ms, 6),
        "mean_tracking_slack_fraction": round(trajectory.mean_slack_fraction, 9),
        "required_cursor_velocity_norm_px_per_ms": round(trajectory.required_cursor_velocity_norm_px_per_ms, 9),
        "residual_steering_25px_rad": round(trajectory.residual_steering_25px_rad, 9),
        "residual_steering_50px_rad": round(trajectory.residual_steering_50px_rad, 9),
        "active_episode_count": trajectory.active_episode_count,
        "support": {
            "mandatory_travel_gate_norm_px": MANDATORY_TRAVEL_GATE_NORM,
            "longest_active_ball_path_gate_norm_px": LONGEST_ACTIVE_BALL_PATH_GATE_NORM,
            "mandatory_travel_pass": mandatory_supported,
            "longest_active_episode_pass": episode_supported,
            "sustained_high_pressure_candidate": support_gate,
        },
        "trajectory_integration": {
            "mode": "continuous_boundary_crossing_v036",
            "active_interval_fraction_is_interpolated": True,
            "endpoint_correction_is_unchanged": True,
        },
        "provenance": provenance,
        "status": "OK",
    }


def _format_time(time_ms: float) -> str:
    total_ms = max(0, int(round(float(time_ms))))
    minutes, remainder = divmod(total_ms, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def _classify_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    known = [row for row in rows if row.get("status") == "OK"]
    sustained = [
        row
        for row in known
        if row.get("support", {}).get("sustained_high_pressure_candidate")
    ]
    tight = [
        row
        for row in sustained
        if row.get("mean_tracking_slack_fraction", 1.0) <= 0.15
    ]
    steering = [
        row
        for row in sustained
        if row.get("residual_steering_25px_rad", 0.0) >= 1.0
    ]
    lazy = [
        row
        for row in known
        if (
            row.get("slider_ball_velocity_norm_px_per_ms", 0.0) >= LAZY_BALL_VELOCITY_GATE_NORM
            and row.get("required_cursor_velocity_norm_px_per_ms", 1.0) <= LAZY_REQUIRED_VELOCITY_CEILING_NORM
            and row.get("mandatory_travel_fraction", 1.0) <= LAZY_MANDATORY_TRAVEL_FRACTION_CEILING
            and row.get("active_follow_fraction", 0.0) >= LAZY_ACTIVE_FOLLOW_FRACTION_FLOOR
        )
    ]
    sustained.sort(
        key=lambda row: (
            row.get("required_cursor_velocity_norm_px_per_ms", -math.inf),
            row.get("mandatory_cursor_travel_norm_px", -math.inf),
            row.get("longest_active_episode_ball_path_norm_px", -math.inf),
        ),
        reverse=True,
    )
    tight.sort(key=lambda row: (row.get("mean_tracking_slack_fraction", math.inf), -row.get("required_cursor_velocity_norm_px_per_ms", 0.0)))
    steering.sort(key=lambda row: row.get("residual_steering_25px_rad", -math.inf), reverse=True)
    lazy.sort(
        key=lambda row: (
            row.get("slider_ball_velocity_norm_px_per_ms", -math.inf),
            -row.get("required_cursor_velocity_norm_px_per_ms", math.inf),
        ),
        reverse=True,
    )
    return {
        "sustained_high_pressure_by_required_cursor_velocity": sustained,
        "supported_tight_tracking_by_low_slack": tight,
        "supported_steering_by_25px_residual_turn": steering,
        "lazy_motion_negative_controls_by_ball_velocity": lazy,
    }


def scan_beatmap(
    beatmap: Beatmap,
    *,
    source_name: str = "<memory>",
    sample_step_norm: float = DEFAULT_SAMPLE_STEP_NORM,
    top_n: Optional[int] = 20,
) -> dict[str, Any]:
    """Scan one parsed map and return serialisable v0.34 evidence."""

    rows: list[dict[str, Any]] = []
    slider_index = 0
    for obj in beatmap.hit_objects:
        if obj.object_type != "slider":
            continue
        slider_index += 1
        rows.append(
            _metric_row(
                beatmap,
                obj,
                slider_index,
                source_name,
                sample_step_norm=sample_step_norm,
            )
        )
    buckets = _classify_rows(rows)
    if top_n is not None:
        top_n = max(0, int(top_n))
        buckets = {key: value[:top_n] for key, value in buckets.items()}
    known = [row for row in rows if row.get("status") == "OK"]
    return {
        "schema_version": "ppy_slider_pressure_corpus_v036",
        "runtime": RUNTIME_VERSION,
        "discovery_version": DISCOVERY_VERSION,
        "formal_axis_admission": {
            "slider_pressure_scalar_admitted": False,
            "nine_axis_values_changed": False,
            "skill_rating_admitted": False,
        },
        "trajectory_integration": {
            "mode": "continuous_boundary_crossing_v036",
            "active_interval_fraction_is_interpolated": True,
            "endpoint_correction_is_unchanged": True,
        },
        "selection_contract": {
            "ppy_priority": True,
            "matched_evidence_required": True,
            "unverified_when_unproven": True,
            "support_gates": {
                "mandatory_cursor_travel_norm_px": MANDATORY_TRAVEL_GATE_NORM,
                "longest_active_follow_ball_path_norm_px": LONGEST_ACTIVE_BALL_PATH_GATE_NORM,
            },
            "lazy_negative_gates": {
                "ball_velocity_norm_px_per_ms_min": LAZY_BALL_VELOCITY_GATE_NORM,
                "required_cursor_velocity_norm_px_per_ms_max": LAZY_REQUIRED_VELOCITY_CEILING_NORM,
                "mandatory_travel_fraction_max": LAZY_MANDATORY_TRAVEL_FRACTION_CEILING,
                "active_follow_fraction_min": LAZY_ACTIVE_FOLLOW_FRACTION_FLOOR,
            },
        },
        "map": _source_identity(beatmap, source_name),
        "scan": {
            "sample_step_norm_px": sample_step_norm,
            "max_sample_intervals_per_span": MAX_SAMPLE_INTERVALS,
            "slider_event_count": len(rows),
            "known_slider_event_count": len(known),
            "unverified_slider_event_count": len(rows) - len(known),
            "sustained_high_pressure_count": len(_classify_rows(rows)["sustained_high_pressure_by_required_cursor_velocity"]),
            "lazy_motion_negative_control_count": len(_classify_rows(rows)["lazy_motion_negative_controls_by_ball_velocity"]),
        },
        "candidates": buckets,
        "all_slider_evidence": rows,
    }


def iter_osu_sources(source: str | Path) -> Iterator[tuple[str, Beatmap]]:
    """Yield ``(source_name, Beatmap)`` for .osu files, dirs, and mapset zips."""

    path = Path(source)
    if path.is_dir():
        for child in sorted(path.rglob("*.osu")):
            yield str(child), parse_osu_file(child)
        return
    if path.suffix.lower() in {".zip", ".osz"}:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.lower().endswith(".osu"):
                    continue
                raw = archive.read(name)
                yield f"{path}!{name}", parse_osu(raw.decode("utf-8-sig", errors="replace"))
        return
    if path.suffix.lower() == ".osu":
        yield str(path), parse_osu_file(path)
        return
    raise ValueError(f"source must be a .osu, .osz/.zip, or directory: {path}")


def scan_source(
    source: str | Path,
    *,
    sample_step_norm: float = DEFAULT_SAMPLE_STEP_NORM,
    top_n: Optional[int] = 20,
) -> dict[str, Any]:
    maps = [
        scan_beatmap(
            beatmap,
            source_name=name,
            sample_step_norm=sample_step_norm,
            top_n=top_n,
        )
        for name, beatmap in iter_osu_sources(source)
    ]
    return {
        "schema_version": "ppy_slider_pressure_corpus_v036_batch",
        "runtime": RUNTIME_VERSION,
        "source": str(source),
        "map_count": len(maps),
        "maps": maps,
    }


__all__ = [
    "DISCOVERY_VERSION",
    "DEFAULT_SAMPLE_STEP_NORM",
    "LONGEST_ACTIVE_BALL_PATH_GATE_NORM",
    "MANDATORY_TRAVEL_GATE_NORM",
    "RUNTIME_VERSION",
    "iter_osu_sources",
    "scan_beatmap",
    "scan_source",
]
