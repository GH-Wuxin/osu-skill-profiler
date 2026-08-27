"""Deterministic experimental atomic Map Demand V0.6 computation.

Inputs are already-extracted Local Signal 0.3 object rows and Feature 0.2
map features. This module never reads reference signals into axis inputs.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable, Optional

from . import contract as C
from .archetype_v01 import classify_axes, unavailable_archetype
from .hidden_v01 import apply_hidden_reading_adjustment, hidden_pressure
from .mod_context_v01 import normalize_mods
from .mod_transform_v01 import (
    scale_local_difficulty_windows,
    transform_beatmap,
    transform_context_matches,
)

# Feature fields consumed by map-level axes.
_FEATURE_STAMINA_SUSTAINED = "temporal.longest_dense_section_ms"
_FEATURE_MAP_DURATION = "temporal.map_duration_ms"
_FEATURE_STAMINA_DENSITY = "section.duration_weighted_density_per_s"
_FEATURE_RHYTHM_ENTROPY = "temporal.rhythm_entropy_bits"
_FEATURE_RHYTHM_DIVERSITY = "temporal.interval_diversity"
_FEATURE_RHYTHM_RATIO = "temporal.interval_ratio_mean"
_FEATURE_READING_DENSITY = "section.density_per_s_p95"
_FEATURE_VISUAL_CHANGE = "spatial.direction_change_ratio_ge_90"

_LOCAL_LAZY_JUMP = "ls.lazy_jump_distance_cs_normalised"
_LOCAL_MIN_TIME = "ls.minimum_jump_time_ms"
_LOCAL_ANGLE = "ls.slider_aware_angle_rad"
_LOCAL_ADJ_DT = "ls.adjusted_delta_time_ms"
_LOCAL_HIT_WINDOW = "ls.hit_window_great_ms"
_LOCAL_DOUBLE_TAP = "ls.double_tap_feasibility"
_LOCAL_MIN_DISTANCE = "ls.minimum_jump_distance_cs_normalised"
_LOCAL_PREEMPT = "ls.preempt_ms"


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


def _p90(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return C.percentile_linear(sorted(values), 0.90)


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return C.percentile_linear(sorted(values), 0.50)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def high_ar_pressure_ms(preempt_ms: float) -> float:
    """Official ReadingEvaluator preempt pressure term (CODE_CONFIRMED).

    Quoted upstream term, used here only as a heuristic diagnostic.
    """
    preempt = C.finite_float(preempt_ms, "reading.preempt_ms")
    if preempt >= 500.0:
        return 0.0
    return ((500.0 - preempt) ** 2.5) / 140000.0


def _ar_preempt_ms(ar: Optional[float]) -> Optional[float]:
    """Mirror of production approach_rate_preempt_ms (Local 0.3 formula).

    Kept local to this experimental package so the tools entry point has no
    production import at module import time; tests assert equality with the
    production helper.
    """
    if ar is None:
        return None
    value = 1200.0
    if ar > 5.0:
        value = 1200.0 + (450.0 - 1200.0) * (ar - 5.0) / 5.0
    elif ar < 5.0:
        value = 1200.0 + (1200.0 - 1800.0) * (ar - 5.0) / 5.0
    if not math.isfinite(value):
        return None
    return float(math.floor(value))


def resolve_effective_ar(difficulty: Optional[dict[str, Any]]) -> tuple[Optional[float], Optional[str]]:
    """Legacy effective-AR resolution at the MapDemand layer.

    ppy/osu LegacyBeatmapDecoder semantics: an explicit ApproachRate wins;
    otherwise an OverallDifficulty value is inherited as the effective
    ApproachRate. Missing both -> (None, None) and reading abstains.
    """
    if not isinstance(difficulty, dict):
        return None, None
    ar = _num(difficulty.get("ApproachRate"))
    if ar is not None:
        return ar, "EXPLICIT_AR"
    od = _num(difficulty.get("OverallDifficulty"))
    if od is not None:
        return od, "LEGACY_AR_FALLBACK_TO_OD"
    return None, None


def precision_pressure(distance_cs: float, actual_time_ms: float) -> float:
    """Corrected clean-room precision adaptation.

    HEURISTIC_PROXY_INSPIRED_BY_OSUSKILLS_HUMAN_TIME. Both arguments are
    milliseconds-scale; ``distance_cs`` is already CS-normalised.
    """
    d = max(C.finite_float(distance_cs, "precision.distance_cs"), 0.0)
    t = C.finite_float(actual_time_ms, "precision.actual_time_ms")
    if d <= 0.0:
        return 0.0
    human_time_ms = math.log2(d / 100.0 + 1.0) * 5.0
    gap_ms = t - human_time_ms
    if gap_ms <= 0.0:
        return C.PRECISION_PRESSURE_CAP
    return min(C.PRECISION_PRESSURE_CAP, 1_000_000.0 / max(gap_ms, 1.0) ** 2)


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Optional[dict[str, Any]] = None,
    difficulty: Optional[dict[str, Any]] = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    """Compute finite map-level components from Local 0.3 + Feature 0.2.

    ``difficulty`` is the raw .osu [Difficulty] mapping (parser keys
    ``ApproachRate`` / ``OverallDifficulty``). When supplied, legacy effective
    AR resolution is applied at this experimental layer and recorded in
    ``reading_ar_provenance``. Returns (components, warnings). Missing required
    primitives produce ``None`` component values, never fabricated zeros.
    """
    rows = list(local_rows)
    mods = {str(mod).upper() for mod in effective_mods}
    rate = C.finite_float(clock_rate, "extract_components.clock_rate")
    if rate <= 0.0:
        raise ValueError("extract_components.clock_rate must be positive")
    components: dict[str, Any] = {
        "row_count": len(rows),
        "jump_aim_strain_p90": None,
        "flow_aim_continuity_share": None,
        "flow_aim_chain_length_p90": None,
        "flow_aim_chain_velocity_p90": None,
        "aim_control_angle_change_p90": None,
        "aim_control_velocity_change_p90": None,
        "spatial_precision_pressure_p90": None,
        "raw_speed_strain_p90": None,
        "stamina_sustained_ms": None,
        "stamina_duration_share": None,
        "stamina_density": None,
        "finger_control_interval_entropy": None,
        "finger_control_interval_diversity": None,
        "finger_control_interval_ratio": None,
        "timing_precision_window_pressure": None,
        "reading_local_preempt_median_ms": None,
        "reading_effective_ar": None,
        "reading_ar_provenance": None,
        "reading_preempt_median_ms": None,
        "reading_density": None,
        "reading_visual_change": None,
        "reading_hidden_pressure": None,
    }
    counts: dict[str, int] = {
        "jump_aim_rows": 0,
        "flow_aim_valid_transitions": 0,
        "flow_aim_chain_transitions": 0,
        "aim_control_angle_rows": 0,
        "aim_control_velocity_rows": 0,
        "spatial_precision_rows": 0,
        "raw_speed_rows": 0,
        "timing_precision_rows": 0,
        "reading_preempt_rows": 0,
        "skipped_nonfinite_rows": 0,
    }
    warnings: list[str] = []
    jump_aim: list[float] = []
    flow_chain_lengths: list[float] = []
    flow_chain_velocities: list[float] = []
    aim_control_angle: list[float] = []
    aim_control_velocity: list[float] = []
    spatial_precision: list[float] = []
    raw_speed: list[float] = []
    timing_precision: list[float] = []
    preempts: list[float] = []
    prev_angle: Optional[float] = None
    prev_velocity: Optional[float] = None
    flow_chain_length = 0
    flow_valid_transitions = 0
    flow_chain_transitions = 0

    for row in rows:
        jump = _num(row.get(_LOCAL_LAZY_JUMP))
        min_time = _num(row.get(_LOCAL_MIN_TIME))
        angle = _num(row.get(_LOCAL_ANGLE))
        adj_dt = _num(row.get(_LOCAL_ADJ_DT))

        velocity: Optional[float] = None
        if jump is not None and min_time is not None:
            velocity = max(jump, 0.0) / max(min_time, C.MIN_TIME_MS)
            jump_aim.append(min(max(velocity, 0.0), C.AIM_STRAIN_CAP))
            counts["jump_aim_rows"] += 1

        if angle is not None and prev_angle is not None and adj_dt is not None:
            angle_delta = min(abs(angle - prev_angle), math.pi)
            aim_control_angle.append(angle_delta / max(adj_dt, C.MIN_TIME_MS))
            counts["aim_control_angle_rows"] += 1

            if velocity is not None:
                flow_valid_transitions += 1
                continuous = (
                    adj_dt <= 400.0
                    and angle >= (2.0 * math.pi / 3.0)
                    and angle_delta <= (math.pi / 3.0)
                )
                if continuous:
                    flow_chain_length += 1
                    flow_chain_transitions += 1
                    flow_chain_lengths.append(float(flow_chain_length))
                    chain_bonus = 1.0 + min(flow_chain_length, 8) / 8.0
                    flow_chain_velocities.append(min(velocity, 2.0) * chain_bonus)
                else:
                    flow_chain_length = 0
            else:
                flow_chain_length = 0

        if velocity is not None and prev_velocity is not None and adj_dt is not None:
            change = abs(math.log1p(velocity) - math.log1p(prev_velocity))
            aim_control_velocity.append(change * 1000.0 / max(adj_dt, C.MIN_TIME_MS))
            counts["aim_control_velocity_rows"] += 1

        if angle is None or velocity is None or adj_dt is None:
            flow_chain_length = 0
        if angle is not None:
            prev_angle = angle
        if velocity is not None:
            prev_velocity = velocity

        min_dist = _num(row.get(_LOCAL_MIN_DISTANCE))
        if min_dist is not None and min_time is not None:
            spatial_precision.append(precision_pressure(min_dist, min_time))
            counts["spatial_precision_rows"] += 1

        dt = _num(row.get(_LOCAL_ADJ_DT))
        hit_window = _num(row.get(_LOCAL_HIT_WINDOW))
        if dt is not None and hit_window is not None and hit_window > 0.0:
            strain_time = max(dt, 0.0) / _clamp(
                (max(dt, 0.0) / hit_window) / 0.93, 0.92, 1.0
            )
            feas = _num(row.get(_LOCAL_DOUBLE_TAP))
            penalty = 1.0 if feas is None else _clamp(1.0 - feas, 0.0, 1.0)
            raw_speed.append(1000.0 / max(strain_time, C.MIN_TIME_MS) * penalty)
            counts["raw_speed_rows"] += 1
        if hit_window is not None and hit_window > 0.0:
            timing_precision.append(1000.0 / hit_window)
            counts["timing_precision_rows"] += 1

        preempt = _num(row.get(_LOCAL_PREEMPT))
        if preempt is not None:
            preempts.append(preempt)
            counts["reading_preempt_rows"] += 1

    components["jump_aim_strain_p90"] = _p90(jump_aim)
    if flow_valid_transitions > 0:
        components["flow_aim_continuity_share"] = (
            flow_chain_transitions / flow_valid_transitions
        )
        components["flow_aim_chain_length_p90"] = _p90(flow_chain_lengths) or 0.0
        components["flow_aim_chain_velocity_p90"] = _p90(flow_chain_velocities) or 0.0
    components["aim_control_angle_change_p90"] = _p90(aim_control_angle)
    components["aim_control_velocity_change_p90"] = _p90(aim_control_velocity)
    components["spatial_precision_pressure_p90"] = _p90(spatial_precision)
    components["raw_speed_strain_p90"] = _p90(raw_speed)
    components["timing_precision_window_pressure"] = (
        _median(timing_precision) if len(timing_precision) >= 2 else None
    )
    counts["flow_aim_valid_transitions"] = flow_valid_transitions
    counts["flow_aim_chain_transitions"] = flow_chain_transitions
    components["reading_local_preempt_median_ms"] = _median(preempts)

    # Legacy effective-AR resolution (experimental layer only). Frozen
    # Feature 0.2 / Local 0.3 artifacts are not rewritten: this correction
    # lives in MapDemand input semantics and is recorded as provenance.
    effective_ar, ar_provenance = resolve_effective_ar(difficulty)
    if effective_ar is not None:
        effective_preempt = _ar_preempt_ms(effective_ar)
        if effective_preempt is not None:
            components["reading_effective_ar"] = effective_ar
            components["reading_ar_provenance"] = ar_provenance
            components["reading_preempt_median_ms"] = effective_preempt / rate
    else:
        components["reading_ar_provenance"] = ar_provenance
        components["reading_preempt_median_ms"] = components["reading_local_preempt_median_ms"]

    if features is not None:
        feature_fields = {
            "stamina_sustained_ms": _FEATURE_STAMINA_SUSTAINED,
            "stamina_density": _FEATURE_STAMINA_DENSITY,
            "finger_control_interval_entropy": _FEATURE_RHYTHM_ENTROPY,
            "finger_control_interval_diversity": _FEATURE_RHYTHM_DIVERSITY,
            "finger_control_interval_ratio": _FEATURE_RHYTHM_RATIO,
            "reading_density": _FEATURE_READING_DENSITY,
            "reading_visual_change": _FEATURE_VISUAL_CHANGE,
        }
        for component_name, feature_name in feature_fields.items():
            raw = features.get(feature_name)
            value = _num(raw)
            if raw is not None and value is None:
                warnings.append(f"{feature_name}: non-finite or non-numeric -> unavailable")
            components[component_name] = value

        components["stamina_sustained_ms"] = _num(features.get(_FEATURE_STAMINA_SUSTAINED))
        map_duration = _num(features.get(_FEATURE_MAP_DURATION))
        sustained = components["stamina_sustained_ms"]
        if map_duration is None or map_duration <= 0.0:
            components["stamina_duration_share"] = None
            if map_duration is not None:
                warnings.append("stamina_duration_share: non-positive map_duration_ms")
        elif sustained is not None:
            components["stamina_duration_share"] = _clamp(sustained / map_duration, 0.0, 1.0)

    density = components.get("stamina_density")
    if density is not None and density > C.DENSITY_PATHOLOGICAL_THRESHOLD:
        warnings.append(
            "stamina_density: extreme finite value above "
            f"{C.DENSITY_PATHOLOGICAL_THRESHOLD:g} objects/s, kept and ranked"
        )

    for required in (
        "jump_aim_strain_p90",
        "flow_aim_continuity_share",
        "flow_aim_chain_length_p90",
        "flow_aim_chain_velocity_p90",
        "aim_control_angle_change_p90",
        "aim_control_velocity_change_p90",
        "spatial_precision_pressure_p90",
        "raw_speed_strain_p90",
        "timing_precision_window_pressure",
    ):
        if components[required] is None:
            warnings.append(f"{required}: no eligible local rows")

    components["row_counts"] = counts
    if "HD" in mods:
        components["reading_hidden_pressure"] = hidden_pressure(rows, features)
        if components["reading_hidden_pressure"] is None:
            warnings.append(
                "HD reading pressure unavailable: no eligible non-spinner rows with preempt"
            )

    return components, warnings


def derive_summaries(axes: dict[str, Any]) -> dict[str, Any]:
    """Compute display-only summaries from emitted atomic axes.

    These values are deliberately outside ``axes`` and are never inputs to
    calibration, archetype classification, or human labels.
    """
    groups = {
        "aim_summary": ("jump_aim", "flow_aim", "aim_control", "spatial_precision"),
        "tapping_summary": ("raw_speed", "stamina", "finger_control"),
        "overall_demand": C.AXIS_ORDER,
    }
    summaries: dict[str, Any] = {}
    for name in C.SUMMARY_ORDER:
        source_axes = groups[name]
        values: list[float] = []
        missing: list[str] = []
        for axis in source_axes:
            axis_obj = axes.get(axis)
            score = _num(axis_obj.get("score")) if isinstance(axis_obj, dict) else None
            if not isinstance(axis_obj, dict) or axis_obj.get("status") != "EMITTED" or score is None:
                missing.append(axis)
            else:
                values.append(score)
        if missing:
            summaries[name] = {
                "score": None,
                "status": "INSUFFICIENT_EVIDENCE",
                "source_axes": list(source_axes),
                "missing_axes": missing,
                "policy": "DERIVED_DISPLAY_ONLY_ARITHMETIC_MEAN_V01",
            }
        else:
            summaries[name] = {
                "score": C.finite_float(_mean(values), f"summary.{name}.score"),
                "status": "EMITTED",
                "source_axes": list(source_axes),
                "missing_axes": [],
                "policy": "DERIVED_DISPLAY_ONLY_ARITHMETIC_MEAN_V01",
            }
    return summaries


def score_components(
    components: dict[str, Any],
    calibration: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Rank components against the versioned calibration distributions.

    Returns (axes, warnings, abstentions). Axis output never consumes
    reference signals; the gate is enforced before any ranking.
    """
    distributions = calibration.get("distributions") or {}
    axes: dict[str, Any] = {}
    warnings: list[str] = []
    abstentions: list[str] = []

    for axis in C.AXIS_ORDER:
        meta = C.AXIS_META[axis]
        missing: list[str] = []
        finite_checked: dict[str, Any] = {}

        for name in meta["signals"]:
            if name == "reading_high_ar_pressure":
                preempt = components.get("reading_preempt_median_ms")
                value = None if preempt is None else high_ar_pressure_ms(preempt)
            else:
                value = components.get(name)
            if value is None:
                missing.append(name)
                continue
            finite_checked[name] = C.finite_float(value, f"axis.{axis}.{name}")

        C.assert_no_reference_signals(finite_checked, f"axis.{axis}")

        def abstain(reasons: list[str]) -> None:
            abstentions.append(
                {
                    "axis": axis,
                    "status": "INSUFFICIENT_EVIDENCE",
                    "reasons": reasons,
                }
            )
            axes[axis] = {
                "score": None,
                "status": "INSUFFICIENT_EVIDENCE",
                "confidence": meta["confidence"],
                "method": meta["method"],
                "combination_policy": meta["combination_policy"],
                "signals": {name: None for name in meta["signals"]},
                "warnings": reasons,
                "evidence": [],
            }

        if missing:
            abstain([f"missing_signal:{name}" for name in missing])
            continue

        missing_dists = [name for name in meta["signals"] if not distributions.get(name)]
        if missing_dists:
            abstain([f"missing_calibration_distribution:{name}" for name in missing_dists])
            continue

        ranks: dict[str, float] = {}
        evidence: list[dict[str, Any]] = []
        for name, signal_meta in meta["signals"].items():
            weight = float(signal_meta["weight"])
            value = finite_checked[name]
            rank = C.quantile_rank(distributions[name], value)
            ranks[name] = rank
            evidence.append(
                {
                    "signal": name,
                    "value": value,
                    "rank": rank,
                    "weight": weight,
                    "source": signal_meta["source"],
                    "evidence_tag": signal_meta["evidence_tag"],
                }
            )

        if axis == "flow_aim":
            # Continuity/chain length describe morphology, not difficulty.
            # They gate the velocity demand instead of independently adding
            # enough mass for a slow regular chain to become top-percentile.
            shape = (
                0.55 * ranks["flow_aim_continuity_share"]
                + 0.45 * ranks["flow_aim_chain_length_p90"]
            )
            total = ranks["flow_aim_chain_velocity_p90"] * (0.25 + 0.75 * shape)
        elif axis == "reading":
            # Density alone is not Reading.  Visual change is the primary
            # proxy; density only amplifies that visual burden. Independently
            # strict high-AR pressure remains additive.
            density = ranks["reading_density"]
            visual = ranks["reading_visual_change"]
            total = (
                0.30 * ranks["reading_high_ar_pressure"]
                + 0.50 * visual
                + 0.20 * density * visual
            )
        else:
            total = sum(
                float(meta["signals"][name]["weight"]) * rank
                for name, rank in ranks.items()
            )

        scale = calibration.get("demand_scale")
        nm_stars = scale.get("nm_stars") if isinstance(scale, dict) else None
        if isinstance(nm_stars, list) and nm_stars:
            tail = scale.get("extreme_tail") if isinstance(scale, dict) else None
            if isinstance(tail, dict) and tail.get("method") == "LOG_SURVIVAL_LINEAR_V01":
                lower_q = C.finite_float(
                    tail.get("lower_quantile"), "demand_scale.extreme_tail.lower_quantile"
                )
                upper_q = C.finite_float(
                    tail.get("upper_quantile"), "demand_scale.extreme_tail.upper_quantile"
                )
                min_count = C.finite_float(
                    tail.get("minimum_survival_count", 0.5),
                    "demand_scale.extreme_tail.minimum_survival_count",
                )
                if not (0.0 < lower_q < upper_q < 1.0) or min_count <= 0.0:
                    raise ValueError("invalid demand_scale.extreme_tail parameters")
                if total <= lower_q:
                    star_equivalent = C.percentile_linear(nm_stars, total)
                else:
                    lower_star = C.percentile_linear(nm_stars, lower_q)
                    upper_star = C.percentile_linear(nm_stars, upper_q)
                    survival_floor = min_count / float(len(nm_stars))
                    survival = max(1.0 - total, survival_floor)
                    anchor_decades = math.log10(
                        (1.0 - lower_q) / (1.0 - upper_q)
                    )
                    target_decades = math.log10((1.0 - lower_q) / survival)
                    slope = max(0.0, upper_star - lower_star) / anchor_decades
                    star_equivalent = lower_star + slope * target_decades
            else:
                star_equivalent = C.percentile_linear(nm_stars, total)
            star_equivalent = max(0.0, star_equivalent)
            # V0.5 artifacts explicitly declared a 10-star hard cap. Preserve
            # that historical contract when they are loaded, while V0.6+
            # artifacts omit cap_stars and therefore retain the empirical
            # tail above 10 stars.
            legacy_cap = scale.get("cap_stars")
            if legacy_cap is not None:
                cap = C.finite_float(legacy_cap, "demand_scale.cap_stars")
                if cap <= 0.0:
                    raise ValueError("demand_scale.cap_stars must be positive")
                star_equivalent = min(cap, star_equivalent)
            normalizer = C.finite_float(
                scale.get("score_normalizer_stars", 10.0),
                "demand_scale.score_normalizer_stars",
            )
            if normalizer <= 0.0:
                raise ValueError("demand_scale.score_normalizer_stars must be positive")
            score = star_equivalent / normalizer
            scale_method = str(scale.get("method") or "EMPIRICAL_NM_STAR_EQUIVALENT")
        else:
            # Old/test calibrations remain readable, but outputs declare that
            # they are still percentile-scaled instead of pretending to be
            # absolute difficulty.
            star_equivalent = total * 10.0
            score = total
            scale_method = "LEGACY_PERCENTILE_FALLBACK"

        axes[axis] = {
            "score": C.finite_float(score, f"axis.{axis}.score"),
            "demand_star_equivalent": C.finite_float(
                star_equivalent, f"axis.{axis}.demand_star_equivalent"
            ),
            "percentile_rank": C.finite_float(total, f"axis.{axis}.percentile_rank"),
            "scale_method": scale_method,
            "status": "EMITTED",
            "confidence": meta["confidence"],
            "method": meta["method"],
            "combination_policy": meta["combination_policy"],
            "signals": finite_checked,
            "warnings": [],
            "evidence": evidence,
        }
    return axes, warnings, abstentions


def derive_context(components: dict[str, Any]) -> dict[str, Any]:
    """Expose objective settings without treating them as human skill axes."""
    pressure = _num(components.get("timing_precision_window_pressure"))
    if pressure is None or pressure <= 0.0:
        return {
            "accuracy_window": {
                "status": "INSUFFICIENT_EVIDENCE",
                "great_window_ms": None,
                "source": "median ls.hit_window_great_ms",
                "excluded_from_skill_axes": True,
            }
        }
    return {
        "accuracy_window": {
            "status": "EMITTED",
            "great_window_ms": C.finite_float(
                1000.0 / pressure, "context.accuracy_window.great_window_ms"
            ),
            "source": "median ls.hit_window_great_ms",
            "excluded_from_skill_axes": True,
            "reason": "OD/hit-window strictness is objective context, not a map archetype",
        }
    }


def analyze_components(
    *,
    checksum: str,
    requested_mods: Iterable[str] = (),
    components: dict[str, Any],
    calibration: dict[str, Any],
    reference_diagnostics: Optional[dict[str, Any]] = None,
    applied_mod_context: Optional[dict[str, Any]] = None,
    algorithm_id: str = C.ALGORITHM_ID,
) -> dict[str, Any]:
    """Wrap components into the full MapDemand output contract."""
    mod_context = normalize_mods(requested_mods)
    calibration_id = str(calibration.get("calibration_id", ""))
    C.assert_no_reference_signals(components, "analyze_components.components")
    identity = C.make_identity(
        beatmap_checksum=checksum,
        effective_mods=mod_context["effective_mods"],
        clock_rate=mod_context["clock_rate"],
        calibration_id=calibration_id,
        algorithm_id=algorithm_id,
    )
    output: dict[str, Any] = {
        "schema_version": C.SCHEMA_VERSION,
        "status": "OK",
        "identity": identity,
        "axes": {},
        "context": derive_context(components),
        "summaries": {},
        "archetype": unavailable_archetype("ANALYSIS_NOT_COMPLETED"),
        "diagnostics": {
            "components": components,
            "mod_context": mod_context,
            "mod_transform_context": applied_mod_context,
            "reference_diagnostics": None,
        },
        "abstentions": [],
        "warnings": [],
    }
    if mod_context["status"] == "INVALID":
        output["status"] = "INVALID_MOD_STATE"
        output["warnings"].extend(mod_context["errors"])
        for axis in C.AXIS_ORDER:
            output["axes"][axis] = {
                "score": None,
                "status": "INVALID_MOD_STATE",
                "confidence": C.AXIS_META[axis]["confidence"],
                "method": C.AXIS_META[axis]["method"],
                "combination_policy": C.AXIS_META[axis]["combination_policy"],
                "signals": {},
                "warnings": ["invalid mod state"],
                "evidence": [],
            }
        output["summaries"] = derive_summaries(output["axes"])
        return output

    hidden_value = _num(components.get("reading_hidden_pressure"))
    required_mod_signals_ready = "HD" not in mod_context["effective_mods"] or (
        hidden_value is not None and 0.0 <= hidden_value <= 1.0
    )
    transform_ready = not mod_context["effective_mods"] or (
        transform_context_matches(applied_mod_context, mod_context)
        and required_mod_signals_ready
    )
    if not transform_ready:
        output["status"] = "UNSUPPORTED_MOD_STATE"
        output["warnings"].append(
            {
                "code": "UNSUPPORTED_MOD_STATE",
                "message": "required Map Demand transforms/signals are blocked, absent, or do not match this mod context",
                "requested_mods": mod_context["requested_mods"],
                "effective_mods": mod_context["effective_mods"],
                "pending_transforms": mod_context["pending_transforms"],
                "required_signals": mod_context["required_signals"],
                "pending_signals": mod_context["pending_signals"],
                "deferred_mods": mod_context["deferred_mods"],
                "unsupported_mechanics": mod_context["unsupported_mechanics"],
            }
        )
        for axis in C.AXIS_ORDER:
            output["axes"][axis] = {
                "score": None,
                "status": "UNSUPPORTED_MOD_STATE",
                "confidence": C.AXIS_META[axis]["confidence"],
                "method": C.AXIS_META[axis]["method"],
                "combination_policy": C.AXIS_META[axis]["combination_policy"],
                "signals": {},
                "warnings": ["unsupported mod state"],
                "evidence": [],
            }
        output["summaries"] = derive_summaries(output["axes"])
        return output

    axes, component_warnings, abstentions = score_components(components, calibration)
    if "HD" in mod_context["effective_mods"]:
        axes["reading"] = apply_hidden_reading_adjustment(
            axes["reading"], components.get("reading_hidden_pressure")
        )
    output["axes"] = axes
    output["summaries"] = derive_summaries(axes)
    output["archetype"] = classify_axes(axes)
    output["warnings"] = [{"code": "COMPONENT_WARNING", "message": w} for w in component_warnings]
    output["abstentions"] = abstentions
    if reference_diagnostics is not None:
        output["diagnostics"]["reference_diagnostics"] = reference_diagnostics
        output["diagnostics"]["reference_signal_version"] = C.REFERENCE_SIGNAL_VERSION
    output["diagnostics"]["component_warnings"] = component_warnings
    C.scan_finite(output, "analyze_components.output")
    return output


def sha256_file_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def extract_from_path(
    path: str,
    requested_mods: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Parse a .osu file and run Local 0.3 + Feature 0.2 extractors.

    Returns (local_rows, features, metadata). Metadata includes the raw
    parsed ``difficulty`` mapping for legacy effective-AR resolution.
    """
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src = os.path.join(root, "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    from osu_skill_profiler.features.extractor import FeatureExtractor
    from osu_skill_profiler.parser.normalized import normalize
    from osu_skill_profiler.parser.osu_parser import parse_osu_file
    from osu_skill_profiler.signals.extractor import LocalSignalExtractor

    source_beatmap = parse_osu_file(path)
    mod_context = normalize_mods(requested_mods)
    beatmap, transform_context = transform_beatmap(source_beatmap, mod_context)
    local_rows = LocalSignalExtractor(C.LOCAL_SIGNAL_VERSION).extract(beatmap)["objects"]
    local_rows = scale_local_difficulty_windows(
        local_rows, transform_context.get("clock_rate", 1.0)
    )
    features = FeatureExtractor(C.FEATURE_VERSION).extract(normalize(beatmap))
    metadata = {
        "path": path,
        "object_count": len(local_rows),
        "feature_count": len(features),
        "difficulty": dict(beatmap.difficulty),
        "effective_difficulty": dict(
            transform_context.get("effective_difficulty", beatmap.difficulty)
        ),
        "source_difficulty": dict(source_beatmap.difficulty),
        "mod_context": mod_context,
        "mod_transform_context": transform_context,
    }
    return local_rows, features, metadata
