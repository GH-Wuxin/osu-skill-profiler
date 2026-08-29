"""Map Demand V0.96: signed mechanic evidence and contrast-preserving axes.

V0.95.3 remains replayable.  V0.96 deliberately demotes the inherited,
human-calibrated score to a continuity reference.  Every emitted axis now has
both supporting and counter evidence; total SR scales proven mechanics but no
longer gives every mechanic an unconditional floor.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Optional

from . import contract as C
from . import model_v091 as v091
from . import model_v092 as v092
from . import model_v095 as v095

ALGORITHM_ID = "MAP_DEMAND_ATOMIC_V096"
MAP_DEMAND_VERSION = "0.9.6"
SCHEMA_VERSION = "map_demand_v0.9.6"
AXIS_SCHEMA_VERSION = v095.AXIS_SCHEMA_VERSION
AXIS_ORDER = v095.AXIS_ORDER
MECHANISM_SPEC = (
    "MAP_DEMAND_ATOMIC_V096:base=v0953_replay;"
    "scale=signed_support_minus_counterevidence;"
    "inheritance=non_normative_continuity_reference;"
    "total_sr=scales_proven_mechanics_not_axis_floor;"
    "precision=signed_target_size_settling_micro_correction;"
    "prominence=convex_decisive_evidence_uplift;"
    "human_labels=wide_band_ordering_reference_only"
)

extract_from_path = v095.extract_from_path
sha256_file_bytes = v095.sha256_file_bytes


def _finite(value: Any) -> float | None:
    return v095._finite(value)


def _clamp(value: float, low: float, high: float) -> float:
    return v095._clamp(value, low, high)


def _quantile(values: list[float], q: float) -> float | None:
    return v095._quantile(values, q)


def calibration_id(base_calibration_id: str) -> str:
    payload = json.dumps(
        {"base_calibration_id": base_calibration_id, "mechanism_spec": MECHANISM_SPEC},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"mdoverlay_v096:{digest}"


def _signed_precision_components(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return signed target-size evidence around the neutral CS4 radius.

    V0.95 clamped every CS4-or-larger target to zero, so CS0, CS2 and CS4
    became indistinguishable.  V0.96 keeps that negative evidence: large
    targets reduce tolerance demand while small targets increase it.
    """

    signed_targets: list[float] = []
    velocities: list[float] = []
    for row in rows:
        if row.get("ls.object_type") == "spinner":
            continue
        radius = _finite(row.get("ls.radius_px"))
        distance = _finite(row.get("ls.jump_distance_raw_px"))
        dt = _finite(row.get("ls.minimum_jump_time_ms"))
        if radius is None or distance is None or dt is None or radius <= 0.0 or dt <= 0.0:
            continue
        signed_targets.append(_clamp((36.5 - radius) / 18.0, -1.0, 1.0))
        velocities.append(distance / max(dt, C.MIN_TIME_MS))

    signed_target = _quantile(signed_targets, 0.75) or 0.0
    return {
        "v096_precision_signed_target_p75": signed_target,
        "v096_precision_small_target_gate": max(0.0, signed_target) ** 1.35,
        "v096_precision_large_target_relief": max(0.0, -signed_target) ** 1.20,
        "v096_precision_velocity_p90": _quantile(velocities, 0.90),
    }


def extract_components(
    local_rows: Iterable[dict[str, Any]],
    features: Optional[dict[str, Any]] = None,
    difficulty: Optional[dict[str, Any]] = None,
    clock_rate: float = 1.0,
    effective_mods: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    rows = list(local_rows)
    components, warnings = v095.extract_components(
        rows,
        features,
        difficulty=difficulty,
        clock_rate=clock_rate,
        effective_mods=effective_mods,
    )
    components.update(_signed_precision_components(rows))
    return components, warnings


def _axis_stars(axes: dict[str, Any], axis: str) -> float | None:
    return v095._axis_stars(axes, axis)


def _set_signed_axis(
    axes: dict[str, Any],
    axis: str,
    *,
    anchor: float,
    support: float,
    counter: float,
    base_multiplier: float,
    support_gain: float,
    counter_cost: float,
    prominence_gain: float,
    cap: float | None = None,
    reference_weight: float = 0.40,
    signals: Optional[dict[str, Any]] = None,
) -> None:
    item = axes.get(axis)
    incoming = _axis_stars(axes, axis)
    if not isinstance(item, dict) or incoming is None:
        return
    positive = _clamp(float(support), 0.0, 1.0)
    negative = _clamp(float(counter), 0.0, 1.0)
    prominence = _clamp((positive - 0.72) / 0.28, 0.0, 1.0) ** 1.45
    multiplier = max(
        0.06,
        base_multiplier
        + support_gain * positive
        - counter_cost * negative
        + prominence_gain * prominence,
    )
    structural_target = anchor * multiplier
    # Old human-fit values remain useful for continuity and rough ordering, but
    # cannot veto strong counter-evidence or dictate an exact target.
    inherited_weight = _clamp(reference_weight + 0.12 * positive, 0.0, 0.62)
    adjusted = inherited_weight * incoming + (1.0 - inherited_weight) * structural_target
    if cap is not None:
        adjusted = min(float(cap), adjusted)
    adjusted = max(0.0, adjusted)
    item["demand_star_equivalent"] = adjusted
    item["score"] = adjusted / 10.0
    item["percentile_rank"] = None
    item["scale_method"] = "SIGNED_MECHANIC_EVIDENCE_STAR_SCALE_V096"
    item["method"] = "SUPPORT_MINUS_COUNTEREVIDENCE_WITH_PROMINENCE_V096"
    item.setdefault("evidence", []).append(
        {
            "component": "v096_signed_mechanic_axis",
            "incoming_v0953_stars_reference_only": incoming,
            "scale_anchor_stars": anchor,
            "support_gate": positive,
            "counterevidence_gate": negative,
            "signed_evidence": positive - negative,
            "prominence_gate": prominence,
            "structural_target_multiplier": multiplier,
            "structural_target_stars": structural_target,
            "inherited_reference_weight": inherited_weight,
            "adjusted_stars": adjusted,
            "signals": signals or {},
            "human_calibration_policy": "WIDE_BAND_ORDERING_REFERENCE_NOT_EXACT_TARGET",
            "evidence_tag": "MECHANISM_FIRST_V096_REQUIRES_BROAD_VALIDATION",
        }
    )


def _flow_support(components: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    share = _finite(components.get("v091_flow_chain_share")) or 0.0
    length = _finite(components.get("v091_flow_chain_length_p90")) or 0.0
    velocity = _finite(components.get("v091_flow_chain_velocity_p90")) or 0.0
    smoothness = _finite(components.get("v091_flow_chain_smoothness_mean")) or 0.0
    tapping = _finite(components.get("v095_tapping_evidence_gate")) or 0.0
    repeated_ms = _finite(components.get("v092_pressure_repeated_section_effective_ms")) or 0.0
    morphology = (
        0.34 * _clamp(share / 0.48, 0.0, 1.0)
        + 0.28 * _clamp((length - 1.0) / 9.0, 0.0, 1.0)
        + 0.24 * _clamp((velocity - 0.35) / 1.9, 0.0, 1.0)
        + 0.14 * _clamp(smoothness, 0.0, 1.0)
    )
    persistence = repeated_ms / (repeated_ms + 24000.0)
    support = morphology * (0.72 + 0.18 * tapping + 0.10 * persistence)
    counter = _clamp(0.72 * (1.0 - morphology) + 0.28 * (1.0 - persistence), 0.0, 1.0)
    return support, counter, {
        "flow_morphology": morphology,
        "flow_chain_share": share,
        "flow_chain_length_p90": length,
        "flow_chain_velocity_p90": velocity,
        "flow_chain_smoothness": smoothness,
        "compact_tapping_gate": tapping,
        "repeated_pressure_load": persistence,
    }


def _reading_support(
    axes: dict[str, Any], components: dict[str, Any], mods: set[str]
) -> tuple[float, float, dict[str, Any]]:
    physical = sorted(
        (
            value
            for axis in ("jump_aim", "flow_aim", "aim_control", "spatial_precision", "raw_speed")
            if (value := _axis_stars(axes, axis)) is not None
        ),
        reverse=True,
    )
    environment = sum(physical[:3]) / 3.0 if len(physical) >= 3 else 0.0
    preempt = _finite(components.get("reading_preempt_median_ms")) or 600.0
    overlap = _finite(components.get("v091_visible_overlap_load_p90")) or 0.0
    cluster = _finite(components.get("v091_visible_cluster_load_p90")) or 1.0
    overlap_share = _finite(components.get("v091_visible_overlap_pair_share")) or 0.0
    stack_share = _finite(components.get("v091_visible_stack_object_share")) or 0.0
    density = _finite(components.get("reading_density")) or 0.0
    pair_support = _clamp((overlap_share - 0.10) / 0.25, 0.0, 1.0)
    spatial = (
        0.50 * math.sqrt(_clamp(overlap / 2.0, 0.0, 1.0) * pair_support)
        + 0.30 * math.sqrt(_clamp((cluster - 1.0) / 5.0, 0.0, 1.0) * pair_support)
        + 0.20 * _clamp((stack_share - 0.08) / 0.52, 0.0, 1.0)
    )
    required_preempt = _clamp(720.0 - 48.0 * (environment - 5.0), 320.0, 900.0)
    relative_low_ar = _clamp((preempt / required_preempt - 1.0) / 0.65, 0.0, 1.0)
    high_ar_relief = _clamp((required_preempt - preempt) / 260.0, 0.0, 1.0)
    activity = max(
        spatial,
        _clamp((density - 1.0) / 2.0, 0.0, 1.0),
        _clamp((environment - 1.5) / 3.0, 0.0, 1.0),
    )
    low_ar = relative_low_ar * activity
    hd = (0.28 + 0.72 * spatial) * (0.30 + 0.70 * low_ar) * activity if "HD" in mods else 0.0
    support = _clamp(0.48 * spatial + 0.34 * low_ar + 0.18 * hd, 0.0, 1.0)
    counter = _clamp(
        0.55 * high_ar_relief * (1.0 - spatial)
        + 0.45 * (1.0 - activity),
        0.0,
        1.0,
    )
    return support, counter, {
        "physical_environment_stars": environment,
        "actual_preempt_ms": preempt,
        "required_preempt_ms": required_preempt,
        "pair_supported_spatial_load": spatial,
        "relative_low_ar_gate": relative_low_ar,
        "activity_gate": activity,
        "hd_synergy_gate": hd,
        "high_ar_relief_gate": high_ar_relief,
    }


def _sustain_support(components: dict[str, Any], *, endurance: bool) -> tuple[float, float, dict[str, Any]]:
    coverage = _clamp(_finite(components.get("v092_pressure_coverage")) or 0.0, 0.0, 1.0)
    longest_s = max(0.0, _finite(components.get("v092_pressure_longest_continuous_effective_ms")) or 0.0) / 1000.0
    effective_s = max(0.0, _finite(components.get("v092_pressure_effective_duration_ms")) or 0.0) / 1000.0
    repeated_s = max(0.0, _finite(components.get("v092_pressure_repeated_section_effective_ms")) or 0.0) / 1000.0
    recovery = _clamp(_finite(components.get("v092_pressure_recovery_ratio")) or 0.0, 0.0, 1.0)
    if endurance:
        duration = effective_s / (effective_s + 120.0)
        repeated = repeated_s / (repeated_s + 75.0)
        continuous = longest_s / (longest_s + 20.0)
        support = _clamp(0.38 * duration + 0.28 * repeated + 0.20 * math.sqrt(coverage) + 0.14 * continuous, 0.0, 1.0)
        counter = _clamp(0.50 * (1.0 - duration) + 0.30 * recovery + 0.20 * (1.0 - coverage), 0.0, 1.0)
    else:
        continuous = longest_s / (longest_s + 6.0)
        repeated = repeated_s / (repeated_s + 30.0)
        duration = effective_s / (effective_s + 60.0)
        support = _clamp(0.45 * continuous + 0.30 * repeated + 0.15 * math.sqrt(coverage) + 0.10 * duration, 0.0, 1.0)
        counter = _clamp(0.55 * (1.0 - continuous) + 0.25 * (1.0 - repeated) + 0.20 * recovery, 0.0, 1.0)
    return support, counter, {
        "pressure_coverage": coverage,
        "longest_continuous_effective_s": longest_s,
        "effective_pressure_s": effective_s,
        "repeated_pressure_s": repeated_s,
        "recovery_ratio": recovery,
    }


def _signed_gates(
    axes: dict[str, Any], components: dict[str, Any], mods: set[str]
) -> dict[str, tuple[float, float, dict[str, Any]]]:
    jump_tail = _clamp(_finite(components.get("v092_jump_tail_activation")) or 0.0, 0.0, 1.0)
    jump_severity = _clamp(_finite(components.get("v092_jump_severity_gate")) or 0.0, 0.0, 1.0)
    jump_persistence = _clamp(_finite(components.get("v092_jump_persistence_gate")) or 0.0, 0.0, 1.0)
    tapping_large_jump_share = _clamp(
        _finite(components.get("v095_tapping_large_jump_pair_share")) or 0.0,
        0.0,
        1.0,
    )
    movement_large_jump_share = _clamp(
        _finite(components.get("v095_control_large_jump_share")) or 0.0,
        0.0,
        1.0,
    )
    large_jump_share = max(tapping_large_jump_share, movement_large_jump_share)
    distance_speed_support = math.sqrt(
        _clamp(movement_large_jump_share / 0.60, 0.0, 1.0)
        * max(jump_severity, 0.25 * jump_tail)
    )
    jump_support = max(
        distance_speed_support,
        _clamp(
            0.42 * jump_severity
            + 0.30 * jump_persistence
            + 0.28 * jump_tail,
            0.0,
            1.0,
        ),
    )
    jump_counter = _clamp(
        (1.0 - large_jump_share) * (0.65 + 0.35 * (1.0 - jump_support)),
        0.0,
        1.0,
    )

    control_index = _clamp(_finite(components.get("v095_control_index")) or 0.0, 0.0, 1.0)
    control_support = _clamp((control_index - 0.08) / 0.82, 0.0, 1.0)
    stable_jump = large_jump_share * jump_tail * (1.0 - control_support)
    control_counter = _clamp(0.62 * (1.0 - control_support) + 0.38 * stable_jump, 0.0, 1.0)

    small_target = _clamp(_finite(components.get("v096_precision_small_target_gate")) or 0.0, 0.0, 1.0)
    large_target = _clamp(_finite(components.get("v096_precision_large_target_relief")) or 0.0, 0.0, 1.0)
    settling = _clamp(_finite(components.get("v095_precision_settling_p90")) or 0.0, 0.0, 1.0)
    micro = _clamp(_finite(components.get("v095_precision_micro_gate")) or 0.0, 0.0, 1.0)
    precision_support = _clamp(
        0.46 * small_target + 0.14 * settling + 0.40 * micro,
        0.0,
        1.0,
    )
    precision_counter = _clamp(
        0.64 * large_target + 0.36 * (1.0 - max(small_target, micro)),
        0.0,
        1.0,
    )

    tapping = _clamp(_finite(components.get("v095_tapping_evidence_gate")) or 0.0, 0.0, 1.0)
    tapping_chain_count = max(
        0.0,
        _finite(components.get("v095_tapping_longest_fast_chain_count")) or 0.0,
    )
    tapping_chain_ms = max(
        0.0,
        _finite(components.get("v095_tapping_longest_fast_chain_duration_ms")) or 0.0,
    )
    tapping_chain_gate = _clamp((tapping_chain_count - 2.0) / 40.0, 0.0, 1.0)
    tapping_duration_gate = tapping_chain_ms / (tapping_chain_ms + 4000.0)
    # A high local tapping rate is not yet high Raw Speed demand. Sustained or
    # repeatedly extended chains decide how much of that peak rate is exposed.
    raw_support = tapping * (
        0.50 + 0.28 * tapping_chain_gate + 0.22 * tapping_duration_gate
    )
    raw_counter = _clamp(
        0.46 * (1.0 - raw_support)
        + 0.34 * large_jump_share * (1.0 - raw_support)
        + 0.20 * tapping * (1.0 - max(tapping_chain_gate, tapping_duration_gate)),
        0.0,
        1.0,
    )

    pair_count = max(0.0, _finite(components.get("v091_finger_fast_pair_count")) or 0.0)
    change_share = _clamp(_finite(components.get("v091_finger_nontrivial_change_share")) or 0.0, 0.0, 1.0)
    novelty = _clamp((_finite(components.get("v091_finger_novelty_p90")) or 0.0) / 0.28, 0.0, 1.0)
    repeat = _clamp((pair_count - 8.0) / 42.0, 0.0, 1.0)
    finger_support = math.sqrt(repeat * change_share * novelty)
    finger_counter = _clamp(0.45 * (1.0 - repeat) + 0.55 * repeat * (1.0 - change_share * novelty), 0.0, 1.0)

    flow_support, flow_counter, flow_signals = _flow_support(components)
    reading_support, reading_counter, reading_signals = _reading_support(axes, components, mods)
    stamina_support, stamina_counter, stamina_signals = _sustain_support(components, endurance=False)
    endurance_support, endurance_counter, endurance_signals = _sustain_support(components, endurance=True)
    return {
        "jump_aim": (jump_support, jump_counter, {"jump_severity": jump_severity, "jump_persistence": jump_persistence, "jump_tail": jump_tail, "tapping_large_jump_share": tapping_large_jump_share, "movement_large_jump_share": movement_large_jump_share, "distance_speed_support": distance_speed_support}),
        "aim_control": (control_support, control_counter, {"control_index": control_index, "stable_jump_counterevidence": stable_jump}),
        "spatial_precision": (precision_support, precision_counter, {"small_target_gate": small_target, "large_target_relief": large_target, "settling_gate": settling, "micro_correction_gate": micro}),
        "raw_speed": (raw_support, raw_counter, {"compact_tapping_peak_gate": tapping, "longest_fast_chain_count": tapping_chain_count, "longest_fast_chain_duration_ms": tapping_chain_ms, "chain_persistence_gate": tapping_chain_gate, "duration_persistence_gate": tapping_duration_gate, "large_jump_share": large_jump_share}),
        "finger_control": (finger_support, finger_counter, {"fast_pair_count": pair_count, "repeat_gate": repeat, "nontrivial_change_share": change_share, "novelty_gate": novelty}),
        "flow_aim": (flow_support, flow_counter, flow_signals),
        "reading": (reading_support, reading_counter, reading_signals),
        "stamina": (stamina_support, stamina_counter, stamina_signals),
        "endurance": (endurance_support, endurance_counter, endurance_signals),
    }


_AXIS_SCALE = {
    # base, support gain, counter cost, prominence gain, cap, old-reference weight
    "jump_aim": (0.52, 0.50, 0.25, 0.24, None, 0.44),
    "aim_control": (0.42, 0.48, 0.28, 0.18, None, 0.40),
    "spatial_precision": (0.48, 0.48, 0.32, 0.24, None, 0.28),
    "flow_aim": (0.58, 0.50, 0.16, 0.24, None, 0.42),
    "raw_speed": (0.44, 0.52, 0.30, 0.22, None, 0.38),
    "finger_control": (0.55, 0.48, 0.18, 0.24, None, 0.48),
    "reading": (0.50, 0.50, 0.30, 0.25, None, 0.34),
    "stamina": (0.42, 0.50, 0.28, 0.20, 10.0, 0.38),
    "endurance": (0.40, 0.52, 0.28, 0.20, 10.0, 0.38),
}


def analyze_components(
    *,
    checksum: str,
    requested_mods: Iterable[str] = (),
    components: dict[str, Any],
    calibration: dict[str, Any],
    reference_diagnostics: Optional[dict[str, Any]] = None,
    applied_mod_context: Optional[dict[str, Any]] = None,
    algorithm_id: str = ALGORITHM_ID,
) -> dict[str, Any]:
    output = v095.analyze_components(
        checksum=checksum,
        requested_mods=requested_mods,
        components=components,
        calibration=calibration,
        reference_diagnostics=reference_diagnostics,
        applied_mod_context=applied_mod_context,
        algorithm_id=algorithm_id,
    )
    diagnostics = output.setdefault("diagnostics", {})
    mod_context = diagnostics.get("mod_context", {})
    output["schema_version"] = SCHEMA_VERSION
    output["identity"] = C.make_identity(
        beatmap_checksum=checksum,
        effective_mods=mod_context.get("effective_mods", []),
        clock_rate=mod_context.get("clock_rate", 1.0),
        calibration_id=calibration_id(str(calibration.get("calibration_id", ""))),
        algorithm_id=algorithm_id,
        map_demand_version=MAP_DEMAND_VERSION,
    )
    diagnostics["v096_base_map_demand_version"] = v095.MAP_DEMAND_VERSION
    diagnostics["v096_mechanism_spec"] = MECHANISM_SPEC
    if output.get("status") == "OK":
        anchor_data = diagnostics.get("v091_star_anchor", {})
        anchor = _finite(anchor_data.get("stars")) if isinstance(anchor_data, dict) else None
        if anchor is None:
            anchor = v091._estimate_anchor(output["axes"])
        if anchor is not None:
            mods = set(mod_context.get("effective_mods", []))
            gates = _signed_gates(output["axes"], components, mods)
            # Physical mechanics first. Reading and sustain use the revised
            # physical profile rather than the inherited correlated profile.
            order = (
                "jump_aim",
                "aim_control",
                "spatial_precision",
                "flow_aim",
                "raw_speed",
                "finger_control",
                "stamina",
                "endurance",
            )
            for axis in order:
                support, counter, signals = gates[axis]
                base, gain, cost, prominence, cap, reference_weight = _AXIS_SCALE[axis]
                _set_signed_axis(
                    output["axes"],
                    axis,
                    anchor=anchor,
                    support=support,
                    counter=counter,
                    base_multiplier=base,
                    support_gain=gain,
                    counter_cost=cost,
                    prominence_gain=prominence,
                    cap=cap,
                    reference_weight=reference_weight,
                    signals=signals,
                )
            reading_support, reading_counter, reading_signals = _reading_support(
                output["axes"], components, mods
            )
            base, gain, cost, prominence, cap, reference_weight = _AXIS_SCALE["reading"]
            _set_signed_axis(
                output["axes"],
                "reading",
                anchor=anchor,
                support=reading_support,
                counter=reading_counter,
                base_multiplier=base,
                support_gain=gain,
                counter_cost=cost,
                prominence_gain=prominence,
                cap=cap,
                reference_weight=reference_weight,
                signals=reading_signals,
            )
            diagnostics["v096_signed_axis_gates"] = {
                axis: {"support": values[0], "counterevidence": values[1]}
                for axis, values in {**gates, "reading": (reading_support, reading_counter, reading_signals)}.items()
            }
            output["summaries"] = v092.derive_summaries(output["axes"])
            output["archetype"] = v095._classify_axes_with_low_demand_abstention(
                output["axes"], anchor
            )
    C.scan_finite(output, "model_v096.output")
    return output
