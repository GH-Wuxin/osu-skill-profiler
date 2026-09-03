"""Beta.9 Micro Precision recovery over beta.8 slider-aware geometry.

Beta.8 correctly removed same-coordinate repeats from the micro-correction
channel, but its displacement-presence band also suppressed legitimate small
corrections and its CS4 target-size term was identically zero.  Beta.9 keeps
the exact-repeat fix while restoring a bounded ordinary-target tolerance
channel.  High-CS target tightness is measured in two-dimensional landing
area, not only one-dimensional radius, so explicit small-circle evidence can
still reach the upper scale without turning ordinary fast jumps into Micro.
"""

from __future__ import annotations

from collections import Counter
import math
import statistics
from typing import Any, Iterable

from . import paired_transition_geometry_v01 as geometry
from . import spatial_axes_v03 as previous


SCHEMA_VERSION = "spatial_axes_v0.5.0"
LOCAL_SIGNAL_VERSION = geometry.LOCAL_SIGNAL_VERSION
REFERENCE_RADIUS_PX = geometry.REFERENCE_RADIUS_PX
FULL_COVERAGE = previous.FULL_COVERAGE
DEGRADED_COVERAGE = previous.DEGRADED_COVERAGE

JUMP_SCALE = previous.JUMP_SCALE
JUMP_SUPPORT_POLICY_ID = previous.JUMP_SUPPORT_POLICY_ID
JUMP_PUBLIC_FRONTIER_POLICY_ID = previous.JUMP_PUBLIC_FRONTIER_POLICY_ID
PRECISION_SCALE = "MINIMUM_PHASE_TARGET_TOLERANCE_PHYSICAL_LOG_V04"

NEUTRAL_TARGET_TOLERANCE = 0.24
NEUTRAL_TARGET_EFFORT_CAP = 0.45
MICRO_DISPLACEMENT_PRESENCE_RADIUS_RATIO = 0.12
TARGET_TIGHTNESS_DIMENSIONS = 2.0


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def _precision_axis(bundle: dict[str, Any], mods: tuple[str, ...]) -> dict[str, Any]:
    transitions = bundle["transitions"]
    denominator = bundle["candidate_transition_count"]
    records: list[dict[str, Any]] = []
    last_block: Any = None
    run = 0
    previous_distance: float | None = None
    missing_reasons: Counter[str] = Counter()
    same_position_repeat_count = 0

    for transition in transitions:
        block = transition["block"]
        if block != last_block:
            run = 0
            previous_distance = None
            last_block = block
        channel = transition["channels"][geometry.MINIMUM_MINIMUM]
        radius = previous.previous._positive(  # noqa: SLF001
            transition.get("radius_px")
        )
        if not channel["available"] or radius is None:
            if not channel["available"]:
                missing_reasons.update(channel["missing_reasons"])
            if radius is None:
                missing_reasons["MISSING_RADIUS"] += 1
            run += 1
            previous_distance = None
            continue

        distance = float(channel["distance_px"])
        time = float(channel["time_ms"])
        if distance <= 1e-12:
            same_position_repeat_count += 1
        acquisition = -math.expm1(
            -((distance / (0.90 * REFERENCE_RADIUS_PX)) ** 1.40)
        )
        temporal = math.log2(1.0 + (1000.0 / time) / 4.0)

        # Ordinary circles still have finite landing tolerance.  Give that
        # physical requirement a bounded floor instead of declaring CS4
        # exactly zero, while letting larger circles reduce it smoothly.
        neutral_tolerance = NEUTRAL_TARGET_TOLERANCE * min(
            1.0, REFERENCE_RADIUS_PX / radius
        )
        neutral_target_effort = min(
            NEUTRAL_TARGET_EFFORT_CAP,
            acquisition * temporal * neutral_tolerance,
        )
        radius_tightness_octaves = max(
            0.0,
            math.log2(REFERENCE_RADIUS_PX / radius),
        )
        # Hit tolerance is an area in the playfield.  Shrinking the target
        # radius by one octave removes two octaves of admissible landing area.
        # This only strengthens explicit small-circle evidence: CS4 remains at
        # zero here and continues to use the bounded ordinary-target channel.
        target_area_tightness_octaves = (
            TARGET_TIGHTNESS_DIMENSIONS * radius_tightness_octaves
        )
        tight_target_effort = (
            acquisition * temporal * target_area_tightness_octaves
        )
        target_effort = neutral_target_effort + tight_target_effort

        micro_correction = 0.0
        micro_displacement_presence = 0.0
        if previous_distance is not None:
            large_setup = -math.expm1(
                -((previous_distance / (4.0 * REFERENCE_RADIUS_PX)) ** 3.0)
            )
            # The exclusion band is intentionally narrow: exact repeats must
            # be zero, but a real several-pixel correction should rapidly
            # recover the close-landing demand beta.8 erased.
            micro_displacement_presence = -math.expm1(
                -(
                    distance
                    / (
                        MICRO_DISPLACEMENT_PRESENCE_RADIUS_RATIO
                        * REFERENCE_RADIUS_PX
                    )
                )
                ** 2.0
            )
            micro_landing = micro_displacement_presence * math.exp(
                -((distance / (1.60 * REFERENCE_RADIUS_PX)) ** 2.0)
            )
            timing_weight = 1.0 / (1.0 + (time / 220.0) ** 3.0)
            micro_correction = large_setup * micro_landing * timing_weight
        effort = target_effort + 1.50 * micro_correction
        records.append(
            {
                "time": transition["end_time_ms"],
                "segment": transition["segment"],
                "block": block,
                "section": (int(block), run),
                "effort": effort,
                "acquisition": acquisition,
                "temporal": temporal,
                "neutral_tolerance": neutral_tolerance,
                "neutral_target_effort": neutral_target_effort,
                "radius_tightness_octaves": radius_tightness_octaves,
                "target_area_tightness_octaves": (
                    target_area_tightness_octaves
                ),
                "tight_target_effort": tight_target_effort,
                "target_effort": target_effort,
                "micro_correction": micro_correction,
                "micro_displacement_presence": micro_displacement_presence,
                "distance_px": distance,
                "time_ms": time,
                "radius_px": radius,
            }
        )
        previous_distance = distance

    def score(window: list[dict[str, Any]]) -> dict[str, float]:
        strongest = sorted(
            window,
            key=lambda item: item["effort"],
            reverse=True,
        )[:6]
        effort = statistics.fmean(item["effort"] for item in strongest)
        effective_events = sum(-math.expm1(-item["effort"]) for item in window)
        evidence = 0.35 + 0.65 * (1.0 - math.exp(-effective_events / 3.0))
        return {
            "value": 5.0 * math.log2(1.0 + 1.20 * effort) * evidence,
            "support": _clamp((-math.expm1(-effort)) * evidence),
            "effective_events": effective_events,
            "precision_effort": effort,
            "mean_acquisition": statistics.fmean(
                item["acquisition"] for item in strongest
            ),
            "mean_time_ms": statistics.fmean(
                item["time_ms"] for item in strongest
            ),
            "mean_radius_px": statistics.fmean(
                item["radius_px"] for item in strongest
            ),
            "mean_neutral_tolerance": statistics.fmean(
                item["neutral_tolerance"] for item in strongest
            ),
            "mean_neutral_target_effort": statistics.fmean(
                item["neutral_target_effort"] for item in strongest
            ),
            "mean_radius_tightness_octaves": statistics.fmean(
                item["radius_tightness_octaves"] for item in strongest
            ),
            "mean_target_area_tightness_octaves": statistics.fmean(
                item["target_area_tightness_octaves"] for item in strongest
            ),
            "mean_tight_target_effort": statistics.fmean(
                item["tight_target_effort"] for item in strongest
            ),
            "mean_target_effort": statistics.fmean(
                item["target_effort"] for item in strongest
            ),
            "mean_micro_correction": statistics.fmean(
                item["micro_correction"] for item in strongest
            ),
            "mean_micro_displacement_presence": statistics.fmean(
                item["micro_displacement_presence"] for item in strongest
            ),
        }

    winning = previous.previous._section_best(  # noqa: SLF001
        records,
        max_events=8,
        max_span_ms=None,
        scorer=score,
    )
    return previous.previous._base_measure(  # noqa: SLF001
        axis="spatial_precision",
        denominator=denominator,
        eligible_count=len(records),
        winning=winning,
        scale=PRECISION_SCALE,
        signals={
            "pairing": geometry.MINIMUM_MINIMUM,
            "missing_reasons": dict(sorted(missing_reasons.items())),
            "head_full_minimum_time_mixing": False,
            "radius_direction": "smaller radius increases demand",
            "ordinary_target_tolerance": "BOUNDED_NONZERO_CS4_FLOOR",
            "neutral_target_tolerance": NEUTRAL_TARGET_TOLERANCE,
            "neutral_target_effort_cap": NEUTRAL_TARGET_EFFORT_CAP,
            "target_tightness_dimensions": TARGET_TIGHTNESS_DIMENSIONS,
            "small_target_tightness": "LOG2_REFERENCE_AREA_OVER_TARGET_AREA",
            "micro_correction": (
                "same minimum/minimum phase: large setup -> "
                "nonzero close landing"
            ),
            "micro_displacement_presence_radius_ratio": (
                MICRO_DISPLACEMENT_PRESENCE_RADIUS_RATIO
            ),
            "same_position_repeat_count": same_position_repeat_count,
            "same_position_repeat_is_micro_correction": False,
            "window_events": 8,
            "window_ms": None,
            "effective_mods": list(mods),
        },
    )


def extract_spatial_measures(
    rows: Iterable[dict[str, Any]],
    resolved_preempt_ms: float | None = None,
    effective_mods: Iterable[str] = (),
) -> dict[str, Any]:
    """Return beta.9 Precision plus the frozen beta.8 spatial axes."""

    source = list(rows)
    delegated = previous.extract_spatial_measures(
        source,
        resolved_preempt_ms=resolved_preempt_ms,
        effective_mods=effective_mods,
    )
    bundle = geometry.build_transition_bundle(source, resolved_preempt_ms)
    mods = tuple(str(mod) for mod in delegated["effective_mods"])
    result = dict(delegated)
    result.update(
        schema_version=SCHEMA_VERSION,
        spatial_precision=_precision_axis(bundle, mods),
    )
    return result


__all__ = [
    "SCHEMA_VERSION",
    "LOCAL_SIGNAL_VERSION",
    "REFERENCE_RADIUS_PX",
    "FULL_COVERAGE",
    "DEGRADED_COVERAGE",
    "JUMP_SCALE",
    "JUMP_SUPPORT_POLICY_ID",
    "JUMP_PUBLIC_FRONTIER_POLICY_ID",
    "PRECISION_SCALE",
    "NEUTRAL_TARGET_TOLERANCE",
    "NEUTRAL_TARGET_EFFORT_CAP",
    "MICRO_DISPLACEMENT_PRESENCE_RADIUS_RATIO",
    "TARGET_TIGHTNESS_DIMENSIONS",
    "extract_spatial_measures",
]
