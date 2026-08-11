"""Stable machine-readable contract for Local Signal Layer v0.2.

Every signal is an *observable* (Layer A) measurement of gameplay geometry or
reaction context.  Nothing here is an official difficulty final and nothing is
a learned skill.  The v0.1 feature contract is frozen; v0.2 uses an
independent ``ls.*`` namespace and its own version.
"""

from __future__ import annotations

from .. import SCHEMA_VERSION

UPSTREAM_REPOSITORY = "ppy/osu"
UPSTREAM_COMMIT = "b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e"
UPSTREAM_DIFFICULTY_VERSION = 20260706

SIGNAL_VERSION = "0.2.0"

# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------


def _entry(
    *,
    unit: str,
    description: str,
    layer: str = "observable",
    upstream_inspiration: str | None = None,
    missing_semantics: str = "None with provenance flag",
    pathological_semantics: str = "None with provenance flag; never silently clipped",
    model_input_safe: bool = True,
    context_only: bool = False,
    weak_label_candidate: bool = False,
) -> dict:
    return {
        "unit": unit,
        "description": description,
        "layer": layer,
        "upstream_inspiration": upstream_inspiration,
        "missing_semantics": missing_semantics,
        "pathological_semantics": pathological_semantics,
        "model_input_safe": model_input_safe,
        "context_only": context_only,
        "weak_label_candidate": weak_label_candidate,
    }


# Every numeric/typed field emitted per object.  Names use the ls.* namespace
# so they can never collide with the frozen v0.1 feature names.
SIGNAL_SCHEMA: dict[str, dict] = {
    "ls.original_index": _entry(
        unit="index",
        description="0-based index in the .osu file order of [HitObjects]",
        missing_semantics="always present",
        model_input_safe=False,
    ),
    "ls.time_sorted_index": _entry(
        unit="index",
        description="0-based rank when objects are sorted by (start_time, original_index)",
        missing_semantics="always present",
        model_input_safe=False,
    ),
    "ls.object_type": _entry(
        unit="enum",
        description="circle | slider | spinner",
        missing_semantics="always present",
        model_input_safe=False,
        context_only=True,
    ),
    "ls.start_time_ms": _entry(
        unit="ms",
        description="hit object start time",
        missing_semantics="always present",
        context_only=True,
    ),
    "ls.end_time_ms": _entry(
        unit="ms",
        description="hit object end time (slider: start+duration; spinner: end)",
        missing_semantics="slider without duration falls back to start time with provenance",
        context_only=True,
    ),
    "ls.delta_time_ms": _entry(
        unit="ms",
        description="raw start-to-start delta vs previous object in file order",
        upstream_inspiration="DifficultyHitObject.DeltaTime",
        missing_semantics="None for the first object (no previous)",
    ),
    "ls.adjusted_delta_time_ms": _entry(
        unit="ms",
        description="max(delta_time_ms, 25) - semantic clamp for simultaneous objects",
        upstream_inspiration="OsuDifficultyHitObject.AdjustedDeltaTime",
        missing_semantics="None for the first object",
        pathological_semantics="25ms floor is the official semantic clamp; no other clipping",
    ),
    "ls.last_object_end_delta_time_ms": _entry(
        unit="ms",
        description="max(start - previous_end, 25); first difficulty row equals adjusted delta",
        upstream_inspiration="OsuDifficultyHitObject.LastObjectEndDeltaTime",
        missing_semantics="None for the first object",
    ),
    "ls.preempt_ms": _entry(
        unit="ms",
        description="AR-derived approach time (floor of two-piece linear 1800/1200/450 range)",
        upstream_inspiration="OsuHitObject.TimePreempt",
        missing_semantics="None when ApproachRate is missing (never silent AR=0)",
    ),
    "ls.fade_in_ms": _entry(
        unit="ms",
        description="400*min(1, preempt/450) fade-in duration",
        upstream_inspiration="OsuHitObject.TimeFadeIn",
        missing_semantics="None when ApproachRate is missing",
    ),
    "ls.hit_window_great_ms": _entry(
        unit="ms",
        description="full GREAT hit window: 2*(floor(DifficultyRange(OD,80,50,20))-0.5)",
        upstream_inspiration="DifficultyHitObject.HitWindowGreat",
        missing_semantics="None when OverallDifficulty is missing",
    ),
    "ls.radius_px": _entry(
        unit="px",
        description="object radius from CS: 64*(1-0.7*(CS-5)/5)/2*1.00041",
        upstream_inspiration="OsuHitObject.Radius / LegacyRulesetExtensions.CalculateScaleFromCircleSize",
        missing_semantics="None when CircleSize is missing",
    ),
    "ls.cs_scale": _entry(
        unit="ratio",
        description="CS normalisation scale = 50 / radius_px",
        upstream_inspiration="OsuDifficultyHitObject.NORMALISED_RADIUS / Radius",
        missing_semantics="None when CircleSize is missing",
    ),
    "ls.jump_distance_raw_px": _entry(
        unit="px",
        description="Euclidean distance between previous and current object start positions",
        upstream_inspiration="OsuDifficultyHitObject.JumpDistance (unscaled)",
        missing_semantics="None for the first object; 0.0 when current or previous is a spinner (upstream default)",
    ),
    "ls.jump_distance_cs_normalised": _entry(
        unit="normalised px",
        description="jump_distance_raw_px * cs_scale",
        upstream_inspiration="OsuDifficultyHitObject.JumpDistance",
        missing_semantics="None for the first object / missing CS; 0.0 for spinner context",
    ),
    "ls.lazy_jump_distance_cs_normalised": _entry(
        unit="normalised px",
        description="distance from previous lazy end (or previous start) to current start, CS-normalised",
        upstream_inspiration="OsuDifficultyHitObject.LazyJumpDistance",
        missing_semantics="None for the first object / missing CS; 0.0 for spinner context",
    ),
    "ls.minimum_jump_distance_cs_normalised": _entry(
        unit="normalised px",
        description="min(lazy jump, tail jump) anti-flow/flow aware distance, CS-normalised",
        upstream_inspiration="OsuDifficultyHitObject.MinimumJumpDistance",
        missing_semantics="None for the first object / missing CS; 0.0 for spinner context",
    ),
    "ls.minimum_jump_time_ms": _entry(
        unit="ms",
        description="adjusted delta reduced by previous slider lazy travel time, floored at 25ms",
        upstream_inspiration="OsuDifficultyHitObject.MinimumJumpTime",
        missing_semantics="None for the first object",
    ),
    "ls.travel_distance_cs_normalised": _entry(
        unit="normalised px",
        description="slider lazy travel distance * max(1, span_count^0.3); 0.0 for non-sliders",
        upstream_inspiration="OsuDifficultyHitObject.TravelDistance",
        missing_semantics="None when slider geometry/duration is unknown; 0.0 for non-sliders",
    ),
    "ls.travel_time_ms": _entry(
        unit="ms",
        description="max(lazy_travel_time, 25) for sliders; 0.0 for non-sliders",
        upstream_inspiration="OsuDifficultyHitObject.TravelTime",
        missing_semantics="None when slider duration is unknown; 0.0 for non-sliders",
    ),
    "ls.lazy_end_position_x_px": _entry(
        unit="px",
        description="x of the lazy end position (follow-circle minimum-movement endpoint)",
        upstream_inspiration="OsuDifficultyHitObject.LazyEndPosition",
        missing_semantics="None for non-sliders or unknown slider geometry",
        context_only=True,
    ),
    "ls.lazy_end_position_y_px": _entry(
        unit="px",
        description="y of the lazy end position",
        upstream_inspiration="OsuDifficultyHitObject.LazyEndPosition",
        missing_semantics="None for non-sliders or unknown slider geometry",
        context_only=True,
    ),
    "ls.lazy_travel_distance_cs_normalised": _entry(
        unit="normalised px",
        description="follow-circle lazy cursor path length, CS-normalised by slider radius",
        upstream_inspiration="OsuDifficultyHitObject.LazyTravelDistance",
        missing_semantics="None when slider geometry is unknown; 0.0 for non-sliders",
        weak_label_candidate=True,
    ),
    "ls.lazy_travel_time_ms": _entry(
        unit="ms",
        description="time from slider start to the lazy tracking end",
        upstream_inspiration="OsuDifficultyHitObject.LazyTravelTime",
        missing_semantics="None when slider duration is unknown; 0.0 for non-sliders",
    ),
    "ls.slider_aware_angle_rad": _entry(
        unit="rad",
        description="min(plain angle, slider-aware angle) in [0, pi]",
        upstream_inspiration="OsuDifficultyHitObject.Angle / calculateSliderAngle",
        missing_semantics="None for first two objects, spinner contexts, or missing geometry",
    ),
    "ls.normalised_vector_angle_rad": _entry(
        unit="rad",
        description="atan2(|dy|, |dx|) of the incoming movement vector, in [0, pi/2]",
        upstream_inspiration="OsuDifficultyHitObject.NormalisedVectorAngle",
        missing_semantics="None for first two objects, spinner contexts, or missing geometry",
    ),
    "ls.double_tap_feasibility": _entry(
        unit="ratio",
        description="0..1 feasibility of double-tapping this object with the next one",
        upstream_inspiration="OsuDifficultyHitObject.CalculateDoubleTapFeasibility",
        missing_semantics="None for the first object or when OD is missing; 0.0 for the last object (no next)",
        weak_label_candidate=True,
    ),
    "ls.slider_duration_ms": _entry(
        unit="ms",
        description="path-based slider duration (expected/calculated distance / velocity)",
        upstream_inspiration="Slider.EndTime - Slider.StartTime",
        missing_semantics="None for non-sliders or unknown duration",
    ),
    "ls.slider_velocity_px_per_ms": _entry(
        unit="px/ms",
        description="slider ball velocity from SliderMultiplier, SV and red beat length",
        upstream_inspiration="Slider.Velocity / LegacyRulesetExtensions.GetPrecisionAdjustedBeatLength",
        missing_semantics="None for non-sliders or unknown timing",
    ),
    "ls.slider_path_distance_px": _entry(
        unit="px",
        description="path distance used for duration (expected pixel length when present, else calculated)",
        upstream_inspiration="SliderPath.Distance",
        missing_semantics="None for non-sliders",
    ),
    "ls.slider_span_count": _entry(
        unit="count",
        description="max(1, slider_slides) number of spans",
        upstream_inspiration="Slider.RepeatCount / SpanCount()",
        missing_semantics="None for non-sliders",
    ),
    "ls.slider_tick_count": _entry(
        unit="count",
        description="number of SliderTick nested objects generated",
        upstream_inspiration="SliderEventGenerator.Generate",
        missing_semantics="None for non-sliders or unknown duration",
    ),
    "ls.slider_nested_object_count": _entry(
        unit="count",
        description="head + ticks + repeats + tail nested object count",
        upstream_inspiration="Slider.NestedHitObjects",
        missing_semantics="None for non-sliders or unknown duration",
    ),
    "ls.spinner_context": _entry(
        unit="bool",
        description="True when current or previous object is a spinner (upstream skips distances/angles)",
        missing_semantics="always present",
        context_only=True,
    ),
    "ls.provenance": _entry(
        unit="list",
        description="provenance flags for missing/pathological/legacy semantics",
        missing_semantics="always present",
        model_input_safe=False,
        context_only=True,
    ),
}


NUMERIC_SIGNALS = tuple(
    name
    for name, entry in SIGNAL_SCHEMA.items()
    if entry["unit"] not in ("enum", "list", "bool") and name not in (
        "ls.original_index",
        "ls.time_sorted_index",
        "ls.lazy_end_position_x_px",
        "ls.lazy_end_position_y_px",
    )
)

SEGMENT_SUMMARY_FIELDS = ("mean", "p90", "max")


# ---------------------------------------------------------------------------
# v0.1 -> v0.2 migration table
# ---------------------------------------------------------------------------

# Exact-duplicate pairs identified in the v0.1 contract review.  v0.1 keeps
# emitting both names with identical meaning; v0.2 canonicalises and marks the
# deprecated side as an alias.  No historical value is changed.
DUPLICATE_ALIASES: tuple[tuple[str, str, str], ...] = (
    (
        "temporal.burst_count_250ms",
        "temporal.dense_section_count",
        "both count runs of >=2 gaps <= 250ms; dense_section_count is canonical",
    ),
    (
        "temporal.burst_longest_duration_ms_250ms",
        "temporal.longest_dense_section_ms",
        "both measure the longest dense 250ms run; longest_dense_section_ms is canonical",
    ),
    (
        "section.duration_weighted_density_per_s",
        "temporal.density_objects_per_s",
        "map-level values coincide by construction; density_objects_per_s is canonical",
    ),
)


def migration_table() -> dict:
    """Return the machine-readable v0.1 -> v0.2 migration table."""

    return {
        "from_feature_version": "0.1.0",
        "to_feature_version": SIGNAL_VERSION,
        "policy": (
            "v0.1 frozen contract remains loadable and byte-deterministic. "
            "v0.2 signals live in the ls.* namespace and never rewrite v0.1 "
            "names. Deprecated duplicates are preserved in v0.1 and marked "
            "as aliases in v0.2; no historical meaning is changed."
        ),
        "duplicate_aliases": [
            {"deprecated": deprecated, "canonical": canonical, "reason": reason}
            for deprecated, canonical, reason in DUPLICATE_ALIASES
        ],
        "schema_version": SCHEMA_VERSION,
    }


__all__ = [
    "SIGNAL_SCHEMA",
    "NUMERIC_SIGNALS",
    "SEGMENT_SUMMARY_FIELDS",
    "DUPLICATE_ALIASES",
    "migration_table",
    "UPSTREAM_REPOSITORY",
    "UPSTREAM_COMMIT",
    "UPSTREAM_DIFFICULTY_VERSION",
    "SIGNAL_VERSION",
]
