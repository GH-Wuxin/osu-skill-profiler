"""Machine-readable contract for Official Reference Signal Layer v0.1.

Every ``ref.ppy.*`` value is an OFFICIAL_REFERENCE measurement: it contains
ppy/osu difficulty tuning policy from the pinned upstream revision.  It is
never ground truth, never a label and never an observable primitive.

Supported scope: osu!standard, unmodded, local/reference analysis only.
Mod-transformed semantics (HR/DT/HD/EZ/rate-adjusted/lazer mod parity) are
not implemented and must not be inferred from these values.
"""

from __future__ import annotations

UPSTREAM_REPOSITORY = "ppy/osu"
UPSTREAM_COMMIT = "b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e"
UPSTREAM_DIFFICULTY_VERSION = 20260706

REFERENCE_VERSION = "0.1.0"

# Evaluator source mapping used by every contract entry.
_UPSTREAM_FILES = {
    "snap": "SnapAimEvaluator.cs",
    "agility": "AgilityEvaluator.cs",
    "flow": "FlowAimEvaluator.cs",
    "speed": "SpeedEvaluator.cs",
    "rhythm": "RhythmEvaluator.cs",
    "reading": "ReadingEvaluator.cs",
}


def _entry(
    *,
    unit: str,
    description: str,
    upstream_file: str,
    upstream_function: str,
    slider_involvement: str,
    timing_involvement: str,
    missing_semantics: str,
    pathological_semantics: str = "None with provenance; no silent clipping (upstream semantic clamps are preserved)",
    model_input_safe: bool = False,
) -> dict:
    return {
        "classification": "OFFICIAL_REFERENCE",
        "unit": unit,
        "description": description,
        "upstream_file": upstream_file,
        "upstream_function": upstream_function,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_difficulty_version": UPSTREAM_DIFFICULTY_VERSION,
        "slider_involvement": slider_involvement,
        "timing_involvement": timing_involvement,
        "missing_semantics": missing_semantics,
        "pathological_semantics": pathological_semantics,
        "reference_only": True,
        "never_ground_truth": True,
        "model_input_safe": model_input_safe,
        "exploratory_safe": True,
        "final_difficulty": False,
    }


REFERENCE_SCHEMA: dict[str, dict] = {
    # ---- structural identity (not reference policy) ---------------------
    "ref.original_index": {
        "classification": "IDENTITY",
        "unit": "index",
        "description": "0-based index in the .osu file order of [HitObjects]",
        "upstream_file": None,
        "upstream_function": None,
        "missing_semantics": "always present",
        "model_input_safe": False,
    },
    "ref.time_sorted_index": {
        "classification": "IDENTITY",
        "unit": "index",
        "description": "0-based rank when objects are sorted by (start_time, original_index)",
        "upstream_file": None,
        "upstream_function": None,
        "missing_semantics": "always present",
        "model_input_safe": False,
    },
    "ref.start_time_ms": {
        "classification": "IDENTITY",
        "unit": "ms",
        "description": "hit object start time",
        "upstream_file": None,
        "upstream_function": None,
        "missing_semantics": "always present",
        "model_input_safe": False,
    },
    "ref.object_type": {
        "classification": "IDENTITY",
        "unit": "enum",
        "description": "circle | slider | spinner",
        "upstream_file": None,
        "upstream_function": None,
        "missing_semantics": "always present",
        "model_input_safe": False,
    },
    "ref.provenance": {
        "classification": "IDENTITY",
        "unit": "list",
        "description": "provenance flags for missing/pathological/legacy semantics",
        "upstream_file": None,
        "upstream_function": None,
        "missing_semantics": "always present",
        "model_input_safe": False,
    },
    # ---- official reference evaluator signals --------------------------
    "ref.ppy.snap_include_sliders": _entry(
        unit="normalised px/ms (policy-scaled, dimensionless scale)",
        description=(
            "SnapAimEvaluator.EvaluateDifficultyOf(current, withSliderTravelDistance=true): "
            "snap aim difficulty including lazy slider travel distance through previous sliders "
            "and the current slider travel bonus."
        ),
        upstream_file=_UPSTREAM_FILES["snap"],
        upstream_function="EvaluateDifficultyOf",
        slider_involvement=(
            "Include variant: previous slider lazy travel extends currVelocity; current slider "
            "adds TravelDistance/TravelTime bonus; angle handling uses lazy cursor positions."
        ),
        timing_involvement=(
            "AdjustedDeltaTime (25ms floor), highBpmBonus, rhythm-change penalty for velocity "
            "changes, 300-400 BPM acute-angle gating."
        ),
        missing_semantics=(
            "None for the first raw object (no difficulty row) or when required inputs are "
            "unavailable (blocked slider geometry / missing CS). 0.0 only where the upstream "
            "gate returns 0 (Index<=1, spinner context)."
        ),
    ),
    "ref.ppy.snap_exclude_sliders": _entry(
        unit="normalised px/ms (policy-scaled, dimensionless scale)",
        description=(
            "SnapAimEvaluator.EvaluateDifficultyOf(current, withSliderTravelDistance=false): "
            "snap aim difficulty using start-to-start jump distances only (no slider travel)."
        ),
        upstream_file=_UPSTREAM_FILES["snap"],
        upstream_function="EvaluateDifficultyOf",
        slider_involvement="Exclude variant: slider travel is ignored; slider-to-object transitions use raw jump geometry.",
        timing_involvement="Same timing policy as the include variant.",
        missing_semantics=(
            "None for the first raw object (no difficulty row) or when required inputs are "
            "unavailable. 0.0 only where the upstream gate returns 0."
        ),
    ),
    "ref.ppy.agility": _entry(
        unit="normalised px/ms (policy-scaled, dimensionless scale)",
        description=(
            "AgilityEvaluator.EvaluateDifficultyOf(current): fast-aiming difficulty from "
            "(previous lazy travel + current lazy jump), capped at 120 normalised px, over "
            "AdjustedDeltaTime, with small-circle and high-BPM bonuses."
        ),
        upstream_file=_UPSTREAM_FILES["agility"],
        upstream_function="EvaluateDifficultyOf",
        slider_involvement="Previous slider lazy travel distance is added to the current lazy jump.",
        timing_involvement="AdjustedDeltaTime and highBpmBonus(0.2 base).",
        missing_semantics="None for the first raw object or missing lazy jump; 0.0 for spinner current.",
    ),
    "ref.ppy.flow_include_sliders": _entry(
        unit="normalised px/ms (policy-scaled, dimensionless scale)",
        description=(
            "FlowAimEvaluator.EvaluateDifficultyOf(current, withSliderTravelDistance=true): "
            "flow aim difficulty including slider travel, raised to 1.45 and gated by "
            "Smootherstep(distance,0,50)."
        ),
        upstream_file=_UPSTREAM_FILES["flow"],
        upstream_function="EvaluateDifficultyOf",
        slider_involvement="Include variant: previous slider lazy travel extends currVelocity; current slider adds travel velocity.",
        timing_involvement="AdjustedDeltaTime, rhythm-change factor, angular velocity factor.",
        missing_semantics="None for the first raw object or required missing inputs; 0.0 only where the upstream gate returns 0.",
    ),
    "ref.ppy.flow_exclude_sliders": _entry(
        unit="normalised px/ms (policy-scaled, dimensionless scale)",
        description=(
            "FlowAimEvaluator.EvaluateDifficultyOf(current, withSliderTravelDistance=false): "
            "flow aim difficulty using start-to-start jump distances only."
        ),
        upstream_file=_UPSTREAM_FILES["flow"],
        upstream_function="EvaluateDifficultyOf",
        slider_involvement="Exclude variant: no slider travel extension or current-slider travel bonus.",
        timing_involvement="Same timing policy as the include variant.",
        missing_semantics="None for the first raw object or required missing inputs; 0.0 only where the upstream gate returns 0.",
    ),
    "ref.ppy.speed": _entry(
        unit="1/ms (policy-scaled, dimensionless scale)",
        description=(
            "SpeedEvaluator.EvaluateDifficultyOf(current): tap-speed difficulty from "
            "AdjustedDeltaTime, OD-window-capped strain time, 200+BPM bonus, high-BPM bonus "
            "and double-tap feasibility penalty."
        ),
        upstream_file=_UPSTREAM_FILES["speed"],
        upstream_function="EvaluateDifficultyOf",
        slider_involvement="Spinner current returns 0; sliders otherwise use the same tap-time policy.",
        timing_involvement="AdjustedDeltaTime, hit window (OD), highBpmBonus(0.3 base), double-tap feasibility.",
        missing_semantics="None for the first raw object or when OD is missing; 0.0 for spinner current.",
    ),
    "ref.ppy.rhythm": _entry(
        unit="dimensionless multiplier (>=1)",
        description=(
            "RhythmEvaluator.EvaluateDifficultyOf(current): rhythm-complexity multiplier "
            "derived from island structure over the previous 5s/32-object window, delta "
            "ratios, slider-aware ratios, double-tap nerf and occurrence nerfs."
        ),
        upstream_file=_UPSTREAM_FILES["rhythm"],
        upstream_function="EvaluateDifficultyOf",
        slider_involvement="Slider-aware minimum-jump and last-object-end ratios; bpm-change-into/from-slider nerfs.",
        timing_involvement="Raw DeltaTime comparisons, hit-window epsilon, 5s history window, island deltas.",
        missing_semantics="None for the first raw object or when OD is missing on evaluated rows; 0.0 for spinner current.",
    ),
    "ref.ppy.speed_with_rhythm": _entry(
        unit="policy product (dimensionless scale)",
        description=(
            "SpeedEvaluator value x RhythmEvaluator value for the same object. This is a "
            "private test/reference-only decomposition mirroring the two evaluators that the "
            "Speed skill combines under harmonic strain decay; it is NOT the official strain "
            "value and does NOT include the 1.16 skill multiplier or decay."
        ),
        upstream_file="Speed.cs / SpeedEvaluator.cs / RhythmEvaluator.cs",
        upstream_function="ObjectDifficultyOf (decomposed, no strain decay)",
        slider_involvement="Inherits both evaluators' slider semantics.",
        timing_involvement="Inherits both evaluators' timing semantics.",
        missing_semantics="None whenever either component is unavailable; 0.0 for spinner current.",
    ),
    "ref.ppy.reading": _entry(
        unit="dimensionless policy value",
        description=(
            "ReadingEvaluator.EvaluateDifficultyOf(current, hidden=false): unmodded reading "
            "difficulty from visible-object density (past+future), constant-angle repetition "
            "nerf, preempt difficulty and high-BPM bonus, combined with a 1.5-norm."
        ),
        upstream_file=_UPSTREAM_FILES["reading"],
        upstream_function="EvaluateDifficultyOf",
        slider_involvement="No slider-specific branch; sliders participate via start times, lazy jumps and preempt.",
        timing_involvement="Preempt (AR), 3s reading window, 2s angle window, time nerf, highBpmBonus(0.8 base).",
        missing_semantics="None for the first raw object or when AR/lazy-jump inputs are unavailable; 0.0 only where the upstream gate returns 0.",
    ),
}


REFERENCE_NUMERIC_SIGNALS = tuple(
    name
    for name, entry in REFERENCE_SCHEMA.items()
    if entry.get("classification") == "OFFICIAL_REFERENCE"
)

# Aggregation policy per numeric signal for fixed-time segment summaries.
# count/mean/median/p90/p95/max are descriptive statistics only; they never
# form a final segment difficulty scalar.
SEGMENT_SUMMARY_FIELDS = ("count", "mean", "median", "p90", "p95", "max")

SEGMENT_AGGREGATION_POLICY: dict[str, tuple[str, ...]] = {
    signal: SEGMENT_SUMMARY_FIELDS for signal in REFERENCE_NUMERIC_SIGNALS
}


__all__ = [
    "REFERENCE_SCHEMA",
    "REFERENCE_NUMERIC_SIGNALS",
    "REFERENCE_VERSION",
    "SEGMENT_SUMMARY_FIELDS",
    "SEGMENT_AGGREGATION_POLICY",
    "UPSTREAM_REPOSITORY",
    "UPSTREAM_COMMIT",
    "UPSTREAM_DIFFICULTY_VERSION",
]
