"""Beta.8 spatial axes with a separated Jump demand envelope.

This module deliberately leaves :mod:`spatial_axes_v02` replayable.  Flow and
Control are delegated byte-for-byte to v02.  Jump is rebuilt around explicit
support frontiers, and Precision closes one zero-displacement loophole in the
v02 micro-correction channel.  Jump keeps the paired slider-aware phase
geometry, but separates:

* the strongest physical transition (``physical_peak``),
* whether the required signals were actually available
  (``evidence_confidence``), and
* how strongly the pattern is established, sustained, and repeated.

The public ``value`` is explicitly selected from the establishment and
recurrence frontiers.  A contiguous run or separated reappearance can
therefore establish Jump demand, while duration-only sustain and the atomic
physical peak remain diagnostics.  No value is multiplied by confidence or a
fixed-size max-window penalty.  The physical transform is monotone and
unbounded, so a legitimate extreme remains visible.
"""
from __future__ import annotations

from collections import Counter
import heapq
import math
import statistics
from typing import Any, Iterable

from .axis_support_frontier_v01 import (
    JUMP_SUPPORT_POLICY,
    SupportSample,
    evaluate_support_frontier,
    select_public_frontier,
)
from . import paired_transition_geometry_v01 as geometry
from . import spatial_axes_v02 as previous


SCHEMA_VERSION = "spatial_axes_v0.4.0"
LOCAL_SIGNAL_VERSION = geometry.LOCAL_SIGNAL_VERSION
REFERENCE_RADIUS_PX = geometry.REFERENCE_RADIUS_PX
FULL_COVERAGE = previous.FULL_COVERAGE
DEGRADED_COVERAGE = previous.DEGRADED_COVERAGE

JUMP_SCALE = "LOCAL_JOINT_DISTANCE_TIME_PHYSICAL_POWER_V03"
JUMP_SUPPORT_POLICY_ID = "JUMP_ESTABLISHMENT_FRONTIER_V01"
JUMP_PUBLIC_FRONTIER_POLICY_ID = "JUMP_MAX_ESTABLISHMENT_RECURRENCE_V01"
PRECISION_SCALE = "MINIMUM_PHASE_TARGET_ACQUISITION_PHYSICAL_LOG_V03"

# This is a versioned physical unit conversion, not a ceiling.  Compared with
# beta.7's log curve it deliberately lowers the ordinary/mid-load region while
# retaining a materially wider, unbounded extreme tail.
_PHYSICAL_STAR_COEFFICIENT = 1.55
_PHYSICAL_STAR_EXPONENT = 1.12
# Episode identity is deliberately coarser than the evaluated frontier: it
# separates background movement from a contiguous recognisable Jump run, while
# the shared evaluator still scans every observed absolute difficulty.  This
# prevents two bursts separated by ordinary movement from masquerading as one
# sustained episode.
_JUMP_EPISODE_ONSET_STAR = 3.0
_ALTERNATIVE_EXCLUDED_SHARE = 0.15
_ALTERNATIVE_HIGH_CONCURRENCY = 8
_ALTERNATIVE_HIGH_CONCURRENCY_MIN_SHARE = 0.05
# A minimum-phase endpoint displacement is still expressed in playfield pixels
# after CS normalisation.  Several playfield diagonals leave ample room for
# legitimate off-screen slider art while rejecting timing/path extrapolation
# values tens of thousands (or trillions) of pixels away.  This is an input
# domain guard, not a star ceiling; valid velocities remain unbounded.
_MAX_SINGLE_CURSOR_PHASE_DISTANCE_PX = 4096.0


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def _physical_jump_stars(joint_load: float) -> float:
    """Map joint physical load onto an unbounded beta.8 Jump scale."""
    return _PHYSICAL_STAR_COEFFICIENT * max(0.0, joint_load) ** _PHYSICAL_STAR_EXPONENT


def _frontier(
    samples: list[SupportSample], evidence_confidence: float
) -> dict[str, Any]:
    """Bind Jump to the single versioned, axis-agnostic frontier engine."""
    return evaluate_support_frontier(
        samples,
        policy=JUMP_SUPPORT_POLICY,
        evidence_confidence=evidence_confidence,
    )


def _coverage_status(coverage: float, eligible_count: int) -> tuple[str, float]:
    if eligible_count <= 0 or coverage < DEGRADED_COVERAGE:
        return "INSUFFICIENT", 0.0
    if coverage < FULL_COVERAGE:
        return "DEGRADED", coverage
    return "FULL", coverage


def _concurrent_slider_context(bundle: dict[str, Any]) -> dict[str, Any]:
    """Identify heads that begin while an earlier slider is still active.

    Such transitions are valid osu! data, but they require a 2B/concurrent
    active-slider mechanism rather than the single-cursor Jump construct.  A
    strict start-time batch prevents equal-time heads from inventing an order;
    those are handled separately by the geometry bundle.
    """

    objects = sorted(
        bundle.get("objects", ()),
        key=lambda item: (float(item.get("time", 0.0)), int(item["object_index"])),
    )
    active_slider_ends: list[float] = []
    active_prior_by_object: dict[int, int] = {}
    overlap_object_count = 0
    max_concurrent_active_sliders = 0
    index = 0
    while index < len(objects):
        time_ms = float(objects[index].get("time", 0.0))
        while active_slider_ends and active_slider_ends[0] <= time_ms:
            heapq.heappop(active_slider_ends)
        end = index
        while end < len(objects) and float(objects[end].get("time", 0.0)) == time_ms:
            end += 1
        batch = objects[index:end]
        active_prior = len(active_slider_ends)
        for obj in batch:
            object_index = int(obj["object_index"])
            active_prior_by_object[object_index] = active_prior
            if active_prior > 0:
                overlap_object_count += 1
        for obj in batch:
            if obj.get("kind") != "slider":
                continue
            slider_end = float(obj.get("end", time_ms))
            if slider_end > time_ms:
                heapq.heappush(active_slider_ends, slider_end)
        max_concurrent_active_sliders = max(
            max_concurrent_active_sliders,
            len(active_slider_ends),
        )
        index = end
    return {
        "active_prior_slider_count_by_object": active_prior_by_object,
        "overlap_object_count": overlap_object_count,
        "max_concurrent_active_sliders": max_concurrent_active_sliders,
    }


def _alternative_mechanism_abstention(
    *,
    excluded_transition_count: int,
    candidate_transition_count: int,
    max_concurrent_active_sliders: int,
) -> tuple[bool, float]:
    """Decide whether single-cursor Jump is inapplicable map-wide.

    A stray overlap is excluded locally.  A material share of concurrent
    active-slider transitions, or a smaller but highly concurrent cluster,
    identifies a different execution mechanism and makes a single-cursor
    public Jump value misleading even when enough ordinary transitions remain.
    """

    excluded_share = (
        excluded_transition_count / candidate_transition_count
        if candidate_transition_count > 0
        else 0.0
    )
    high_concurrency_cluster = (
        max_concurrent_active_sliders >= _ALTERNATIVE_HIGH_CONCURRENCY
        and excluded_share >= _ALTERNATIVE_HIGH_CONCURRENCY_MIN_SHARE
    )
    return (
        excluded_share >= _ALTERNATIVE_EXCLUDED_SHARE
        or high_concurrency_cluster,
        excluded_share,
    )


def _jump_axis(bundle: dict[str, Any], mods: tuple[str, ...]) -> dict[str, Any]:
    denominator = int(bundle["candidate_transition_count"])
    concurrent_context = _concurrent_slider_context(bundle)
    active_prior_by_object = concurrent_context[
        "active_prior_slider_count_by_object"
    ]
    alternative_transition_count = 0
    invalid_geometry_transition_count = 0
    max_invalid_geometry_distance_px = 0.0
    channel_counts: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    samples: list[SupportSample] = []
    last_block: int | None = None
    last_hard_state: bool | None = None
    episode_id = -1
    unavailable_since_last = True

    for transition in bundle["transitions"]:
        if active_prior_by_object.get(
            int(transition["to_object_index"]), 0
        ) > 0:
            alternative_transition_count += 1
            unavailable_since_last = True
            last_block = int(transition["block"])
            last_hard_state = None
            continue
        channels = transition["channels"]
        channel_name: str | None = None
        channel: dict[str, Any] | None = None
        if channels[geometry.MINIMUM_MINIMUM]["available"]:
            channel_name = geometry.MINIMUM_MINIMUM
            channel = channels[channel_name]
        elif channels[geometry.HEAD_FULL]["available"]:
            channel_name = geometry.HEAD_FULL
            channel = channels[channel_name]

        block = int(transition["block"])
        if channel is None or channel_name is None:
            unavailable_since_last = True
            last_block = block
            last_hard_state = None
            continue

        channel_counts[channel_name] += 1
        distance = float(channel["distance_px"])
        duration = float(channel["time_ms"])
        velocity = float(channel["velocity_px_per_ms"])
        if distance > _MAX_SINGLE_CURSOR_PHASE_DISTANCE_PX:
            invalid_geometry_transition_count += 1
            max_invalid_geometry_distance_px = max(
                max_invalid_geometry_distance_px,
                distance,
            )
            unavailable_since_last = True
            last_block = block
            last_hard_state = None
            continue
        distance_load = distance / (4.0 * REFERENCE_RADIUS_PX)
        velocity_load = velocity / 1.15
        joint_load = math.sqrt(max(0.0, distance_load)) * velocity_load
        physical_stars = _physical_jump_stars(joint_load)
        mechanism_weight = -math.expm1(-(joint_load ** 1.35))
        hard_state = physical_stars >= _JUMP_EPISODE_ONSET_STAR
        if (
            unavailable_since_last
            or block != last_block
            or hard_state != last_hard_state
        ):
            episode_id += 1
        unavailable_since_last = False
        last_block = block
        last_hard_state = hard_state
        record = {
            "time_ms": float(transition["end_time_ms"]),
            "start_ms": float(transition["start_time_ms"]),
            "segment": int(transition["segment"]),
            "block": block,
            "episode_id": episode_id,
            "joint_load": joint_load,
            "physical_stars": physical_stars,
            "distance_px": distance,
            "duration_ms": duration,
            "velocity_px_per_ms": velocity,
            "channel": channel_name,
            "from_kind": transition["from_kind"],
            "to_kind": transition["to_kind"],
        }
        records.append(record)
        samples.append(
            SupportSample(
                difficulty=physical_stars,
                time_ms=record["time_ms"],
                duration_ms=duration,
                episode_id=episode_id,
                section_id=block,
                weight=mechanism_weight,
            )
        )

    coverage = len(records) / denominator if denominator > 0 else 0.0
    map_level_alternative, excluded_share = _alternative_mechanism_abstention(
        excluded_transition_count=alternative_transition_count,
        candidate_transition_count=denominator,
        max_concurrent_active_sliders=int(
            concurrent_context["max_concurrent_active_sliders"]
        ),
    )
    status, activation = _coverage_status(coverage, len(records))
    if map_level_alternative:
        status = "INSUFFICIENT"
        activation = 0.0
    envelope = _frontier(samples, coverage)
    public_frontier = select_public_frontier(
        envelope,
        components=("establishment", "recurrence"),
        policy_id=JUMP_PUBLIC_FRONTIER_POLICY_ID,
    )
    physical_peak = envelope["physical_peak"]
    winning: dict[str, Any] | None = None
    physical_peak_details: dict[str, Any]
    if records:
        strongest = max(
            records,
            key=lambda item: (item["physical_stars"], -item["time_ms"]),
        )
        winning = {
            "segment": strongest["segment"],
            "block": strongest["block"],
            "episode_id": strongest["episode_id"],
            "start_ms": strongest["start_ms"],
            "end_ms": strongest["time_ms"],
            "event_count": 1,
            "joint_load": strongest["joint_load"],
            "distance_px": strongest["distance_px"],
            "time_ms": strongest["duration_ms"],
            "velocity_px_per_ms": strongest["velocity_px_per_ms"],
            "channel": strongest["channel"],
            "from_kind": strongest["from_kind"],
            "to_kind": strongest["to_kind"],
        }
        physical_peak_details = {
            "star": physical_peak,
            "raw_load": strongest["joint_load"],
            "unit": "star_equivalent",
            "scale_method": JUMP_SCALE,
            "atomic_window": dict(winning),
        }
    else:
        physical_peak_details = {
            "star": physical_peak,
            "raw_load": None,
            "unit": "star_equivalent",
            "scale_method": JUMP_SCALE,
            "atomic_window": None,
        }

    evidence_confidence = float(envelope["evidence_confidence"])
    evidence_confidence_details = {
        "value": evidence_confidence,
        "status": status,
        "structural_coverage": bundle["structural_coverage"],
        "required_channel_coverage": coverage,
        "eligible_count": len(records),
        "candidate_count": denominator,
        "policy": "REQUIRED_PAIRED_GEOMETRY_COVERAGE_V01",
        "semantics": "MEASUREMENT_RELIABILITY_NOT_DIFFICULTY_ATTENUATION",
    }
    establishment = dict(envelope["establishment"])
    sustain = dict(envelope["sustain"])
    recurrence = dict(envelope["recurrence"])
    frontier_value = public_frontier.get("frontier_star")
    value = 0.0 if frontier_value is None else float(frontier_value)
    selected_component = public_frontier.get("selected_component")
    selected_payload = (
        envelope.get(selected_component)
        if isinstance(selected_component, str)
        else None
    )
    support = _clamp(
        float(
            selected_payload.get("support", 0.0)
            if isinstance(selected_payload, dict)
            else 0.0
        )
    )
    reason = (
        "CONCURRENT_ACTIVE_SLIDER_ALTERNATIVE_MECHANISM"
        if map_level_alternative
        else "COMPLETE_EVIDENCE"
        if status == "FULL"
        else "PARTIAL_EVIDENCE"
        if status == "DEGRADED"
        else "CONCURRENT_ACTIVE_SLIDER_ALTERNATIVE_MECHANISM"
        if alternative_transition_count > 0
        else "NO_VALID_SPATIAL_EVIDENCE"
        if len(records) <= 0
        else "INSUFFICIENT_EVIDENCE_COVERAGE"
    )
    return {
        "status": status,
        "reason": reason,
        "value": value if status != "INSUFFICIENT" else None,
        "support": support,
        "counterevidence": _clamp((1.0 - support) * coverage),
        "eligible_count": len(records),
        "coverage": coverage,
        "activation": activation,
        "winning_section": winning,
        "total_sr_used": False,
        "scale": JUMP_SCALE,
        "physical_peak": physical_peak,
        "physical_peak_details": physical_peak_details,
        "evidence_confidence": evidence_confidence,
        "evidence_confidence_details": evidence_confidence_details,
        "establishment": establishment,
        "sustain": sustain,
        "recurrence": recurrence,
        "public_frontier": public_frontier,
        "combined_frontier_star": envelope.get("combined_frontier_star"),
        "support_frontier_schema_version": envelope.get("schema_version"),
        "signals": {
            "axis": "jump_aim",
            "pairing_priority": [
                geometry.MINIMUM_MINIMUM,
                geometry.HEAD_FULL,
            ],
            "channel_counts": dict(sorted(channel_counts.items())),
            "candidate_count": denominator,
            "fixed_max_window_events": None,
            "fixed_max_window_ms": None,
            "peak_confidence_multiplication": False,
            "public_value_semantics": "SELECTED_SUPPORT_FRONTIER_STAR",
            "support_policy": JUMP_SUPPORT_POLICY_ID,
            "public_frontier_policy": JUMP_PUBLIC_FRONTIER_POLICY_ID,
            "episode_onset_star": _JUMP_EPISODE_ONSET_STAR,
            "alternative_mechanism": {
                "kind": "CONCURRENT_ACTIVE_SLIDER_2B",
                "excluded_transition_count": alternative_transition_count,
                "candidate_transition_count": denominator,
                "excluded_transition_share": excluded_share,
                "overlap_object_count": concurrent_context[
                    "overlap_object_count"
                ],
                "max_concurrent_active_sliders": concurrent_context[
                    "max_concurrent_active_sliders"
                ],
                "routing": "EXCLUDED_FROM_SINGLE_CURSOR_JUMP",
                "map_level_abstention": map_level_alternative,
                "map_level_policy": (
                    "ABSTAIN_AT_15_PERCENT_EXCLUDED_OR_"
                    "8_CONCURRENT_WITH_5_PERCENT_EXCLUDED"
                ),
                "invalid_single_cursor_geometry_count": (
                    invalid_geometry_transition_count
                ),
                "max_invalid_geometry_distance_px": (
                    max_invalid_geometry_distance_px
                    if invalid_geometry_transition_count > 0
                    else None
                ),
                "single_cursor_geometry_distance_limit_px": (
                    _MAX_SINGLE_CURSOR_PHASE_DISTANCE_PX
                ),
                "invalid_geometry_routing": (
                    "EXCLUDED_FROM_SINGLE_CURSOR_JUMP"
                ),
            },
            "distance_only_floor": False,
            "effective_mods": list(mods),
        },
    }


def _precision_axis(bundle: dict[str, Any], mods: tuple[str, ...]) -> dict[str, Any]:
    """Measure target precision without treating a zero-distance repeat as aim.

    The v02 close-landing term peaked at distance zero.  That made a large
    movement followed by a same-coordinate repeat look like the strongest
    possible micro correction.  The added displacement-presence band is zero
    at the origin, rises across genuine sub-radius corrections, and retains the
    existing wide-distance falloff.  The target-acquisition channel is
    otherwise unchanged.
    """

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
        radius = previous._positive(transition.get("radius_px"))  # noqa: SLF001
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
        target_tightness = max(
            0.0,
            math.log2(REFERENCE_RADIUS_PX / radius),
        )
        target_effort = acquisition * temporal * target_tightness
        micro_correction = 0.0
        micro_displacement_presence = 0.0
        if previous_distance is not None:
            large_setup = -math.expm1(
                -((previous_distance / (4.0 * REFERENCE_RADIUS_PX)) ** 3.0)
            )
            micro_displacement_presence = -math.expm1(
                -((distance / (0.35 * REFERENCE_RADIUS_PX)) ** 2.0)
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
                "target_tightness": target_tightness,
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
            "mean_target_tightness_octaves": statistics.fmean(
                item["target_tightness"] for item in strongest
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

    winning = previous._section_best(  # noqa: SLF001
        records,
        max_events=8,
        max_span_ms=None,
        scorer=score,
    )
    return previous._base_measure(  # noqa: SLF001
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
            "ordinary_cs4_speed_is_not_precision": True,
            "micro_correction": (
                "same minimum/minimum phase: large setup -> "
                "nonzero close landing"
            ),
            "micro_displacement_presence": (
                "(1-exp(-(distance/(0.35R))^2))*"
                "exp(-(distance/(1.60R))^2)"
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
    """Return beta.8 Jump/Precision plus frozen v02 Flow and Control."""
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
        jump_aim=_jump_axis(bundle, mods),
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
    "_concurrent_slider_context",
    "extract_spatial_measures",
]
