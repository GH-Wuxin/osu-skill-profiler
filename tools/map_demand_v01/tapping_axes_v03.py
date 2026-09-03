"""Beta.8 tapping repairs over the frozen beta.7 event contract.

The event contract and Endurance calculator remain the frozen
:mod:`tapping_axes_v02` implementations.  Beta.8 changes three axes:

* ``physical_peak`` is the strongest instantaneous execution-rate sample;
* ``value`` is selected from establishment and sustain, not the instantaneous
  peak or recurrence of separated short bursts;
* establishment, sustain, recurrence, and evidence confidence are published
  independently; and
* evidence confidence never scales any difficulty value;
* Stamina retains the bounded v02 scale while discounting tapping mass that
  the Local Signal contract identifies as double-tappable; and
* Finger Control retains the v02 local rhythm-transition scale, but cadence
  contrasts which can be resolved as a double tap contribute only their
  remaining single-alternation mechanism weight.

The small ``_frontier`` adapter is deliberately fail-closed around the single
shared ``axis_support_frontier_v01`` implementation.  There is no private
second frontier formula in this module.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Iterable, Mapping

from . import tapping_axes_v02 as previous
from .axis_support_frontier_v01 import (
    RAW_SPEED_SUPPORT_POLICY,
    SCHEMA_VERSION as SUPPORT_FRONTIER_SCHEMA_VERSION,
    SupportSample,
    evaluate_support_frontier,
    select_public_frontier,
)


SCHEMA_VERSION = "tapping_axes_v0.5.0"
VERSION = SCHEMA_VERSION
EVENT_BUNDLE_BASIS_SCHEMA_VERSION = previous.SCHEMA_VERSION
RAW_SPEED_SCALE = "INDEPENDENT_PHYSICAL_RATE_ESTABLISHED_FRONTIER_V04"
FINGER_CONTROL_SCALE = (
    "INDEPENDENT_LOCAL_TRANSITION_LOAD_DOUBLE_TAP_WEIGHTED_V05"
)
FINGER_DOUBLE_TAP_WEIGHT_POLICY = (
    "ONE_MINUS_MAX_ADJACENT_DOUBLE_TAP_FEASIBILITY_V01"
)
STAMINA_DOUBLE_TAP_WEIGHT_POLICY = (
    "ONE_MINUS_EVENT_DOUBLE_TAP_FEASIBILITY_V01"
)
RAW_SPEED_PUBLIC_FRONTIER_POLICY_ID = (
    "RAW_MAX_ESTABLISHMENT_SUSTAIN_EXCLUDE_RECURRENCE_V01"
)

FULL_COVERAGE = previous.FULL_COVERAGE
DEGRADED_COVERAGE = previous.DEGRADED_COVERAGE
PHRASE_GAP_MS = previous.PHRASE_GAP_MS

RAW_RATE_BASELINE_PER_S = 4.5
RAW_RATE_PER_STAR = 1.15

_SAMPLE_FIELDS = (
    "difficulty",
    "time_ms",
    "duration_ms",
    "episode_id",
    "section_id",
    "weight",
)


def _finite_nonnegative(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) and number >= 0.0 else default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def build_event_bundle(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Expose the frozen event builder under the v03 component identity."""

    bundle = previous.build_event_bundle(rows)
    bundle["schema_version"] = SCHEMA_VERSION
    bundle["version"] = VERSION
    bundle["basis_schema_version"] = EVENT_BUNDLE_BASIS_SCHEMA_VERSION
    return bundle


def _validate_frontier(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise TypeError("support frontier must return a mapping")
    if raw.get("schema_version") != SUPPORT_FRONTIER_SCHEMA_VERSION:
        raise ValueError(
            "support frontier schema mismatch: "
            f"expected {SUPPORT_FRONTIER_SCHEMA_VERSION!r}, "
            f"got {raw.get('schema_version')!r}"
        )
    result = dict(raw)
    confidence = result.get("evidence_confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(float(confidence))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise ValueError("support frontier evidence_confidence is invalid")
    for name in ("establishment", "sustain", "recurrence"):
        metric = result.get(name)
        if not isinstance(metric, Mapping):
            raise ValueError(f"support frontier missing {name}")
        for field in ("frontier_star", "support", "winning_threshold_star"):
            value = metric.get(field)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(f"support frontier {name}.{field} is invalid")
    return result


def _frontier(
    samples: Iterable[Mapping[str, Any]],
    *,
    evidence_confidence: float,
    partial_support_exponent: float = 1.0,
) -> dict[str, Any]:
    """Evaluate Raw support through the shared API behind a narrow adapter."""

    payloads = [
        {field: sample.get(field) for field in _SAMPLE_FIELDS}
        for sample in samples
    ]
    confidence = _clamp(_finite_nonnegative(evidence_confidence))
    frontier_samples = [
        SupportSample(**payload)
        for payload in payloads
    ]
    raw = evaluate_support_frontier(
        frontier_samples,
        policy=RAW_SPEED_SUPPORT_POLICY,
        evidence_confidence=confidence,
    )
    result = _validate_frontier(raw)
    exponent = float(partial_support_exponent)
    if not math.isfinite(exponent) or exponent < 1.0:
        raise ValueError("partial_support_exponent must be finite and at least 1")
    if exponent == 1.0:
        return result

    # Beta.8 keeps the historical linear frontier.  Later releases may ask
    # this adapter to make incomplete evidence genuinely sub-linear without
    # changing the shared Jump policy or clipping an established extreme.
    adjusted = copy.deepcopy(result)
    target = RAW_SPEED_SUPPORT_POLICY.frontier_support_target
    for name in ("establishment", "sustain", "recurrence"):
        component = adjusted[name]
        threshold = _finite_nonnegative(component.get("winning_threshold_star"))
        support = _clamp(_finite_nonnegative(component.get("support")))
        support_ratio = min(1.0, support / target)
        component["frontier_star"] = threshold * support_ratio**exponent
    combined_support = _clamp(
        _finite_nonnegative(adjusted.get("combined_support"))
    )
    combined_threshold = _finite_nonnegative(
        adjusted.get("combined_winning_threshold_star")
    )
    adjusted["combined_frontier_star"] = (
        combined_threshold
        * min(1.0, combined_support / target) ** exponent
    )
    adjusted.setdefault("diagnostics", {})[
        "partial_support_exponent"
    ] = exponent
    adjusted["diagnostics"]["partial_support_mapping"] = (
        "THRESHOLD_TIMES_SUPPORT_RATIO_POWER"
    )
    return adjusted


def _raw_records(
    bundle: Mapping[str, Any],
    *,
    rate_baseline_per_s: float = RAW_RATE_BASELINE_PER_S,
    rate_per_star: float = RAW_RATE_PER_STAR,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for block in previous._tap_blocks(dict(bundle)):  # noqa: SLF001 - frozen adapter
        for event in block:
            execution_dt = _finite_nonnegative(event.get("execution_dt_ms"))
            if execution_dt <= 0.0:
                continue
            rate = 1000.0 / execution_dt
            physical_star = max(
                0.0,
                (rate - rate_baseline_per_s) / rate_per_star,
            )
            feasibility_raw = event.get("double_tap_feasibility")
            feasibility = (
                _clamp(_finite_nonnegative(feasibility_raw))
                if feasibility_raw is not None
                else 1.0
            )
            records.append(
                {
                    "difficulty": physical_star,
                    "time_ms": _finite_nonnegative(event.get("start_ms")),
                    "duration_ms": execution_dt,
                    "episode_id": int(event.get("block_id", 0)),
                    # Tapping v02 exposes blocks, not a broader section id.  A
                    # map-wide section lets distinct blocks express recurrence.
                    "section_id": 0,
                    "weight": 1.0 - feasibility,
                    "rate_per_s": rate,
                    "double_tap_feasibility": feasibility_raw,
                }
            )
    return records


def _winning_run(
    records: list[Mapping[str, Any]],
    frontier: Mapping[str, Any],
    *,
    rate_baseline_per_s: float = RAW_RATE_BASELINE_PER_S,
    rate_per_star: float = RAW_RATE_PER_STAR,
) -> dict[str, Any] | None:
    if not records:
        return None
    establishment = frontier["establishment"]
    assert isinstance(establishment, Mapping)
    threshold = _finite_nonnegative(
        establishment.get("winning_threshold_star"),
        default=_finite_nonnegative(frontier.get("physical_peak")),
    )
    if threshold <= 0.0:
        threshold = _finite_nonnegative(frontier.get("physical_peak"))

    runs: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    current_episode: Any = None
    for record in records:
        qualifies = (
            _finite_nonnegative(record.get("difficulty")) + 1e-12 >= threshold
            and _finite_nonnegative(record.get("weight")) > 0.0
        )
        episode = record.get("episode_id")
        if not qualifies or (current and episode != current_episode):
            if current:
                runs.append(current)
            current = []
        if qualifies:
            current.append(record)
            current_episode = episode
        else:
            current_episode = None
    if current:
        runs.append(current)
    if not runs:
        return None

    winner = max(
        runs,
        key=lambda run: (
            sum(_finite_nonnegative(item.get("weight")) for item in run),
            len(run),
            max(_finite_nonnegative(item.get("difficulty")) for item in run),
        ),
    )
    total_weight = sum(_finite_nonnegative(item.get("weight")) for item in winner)
    weighted_rate = sum(
        _finite_nonnegative(item.get("rate_per_s"))
        * _finite_nonnegative(item.get("weight"))
        for item in winner
    )
    valid_feasibilities = [
        float(item["double_tap_feasibility"])
        for item in winner
        if item.get("double_tap_feasibility") is not None
    ]
    return {
        "block_id": winner[0].get("episode_id"),
        "start_ms": _finite_nonnegative(winner[0].get("time_ms")),
        "end_ms": _finite_nonnegative(winner[-1].get("time_ms")),
        "execution_duration_s": sum(
            _finite_nonnegative(item.get("duration_ms")) for item in winner
        )
        / 1000.0,
        "effective_pairs": total_weight,
        "opportunity_pairs": float(len(winner)),
        "observed_pairs": len(winner),
        "rate_per_s": weighted_rate / total_weight if total_weight > 0.0 else 0.0,
        "rate_band_per_s": (
            rate_baseline_per_s + threshold * rate_per_star
        ),
        "double_tap_feasibility_mean": (
            sum(valid_feasibilities) / len(valid_feasibilities)
            if valid_feasibilities
            else None
        ),
        "frontier_threshold_star": threshold,
    }


def _raw_speed_measure(
    bundle: Mapping[str, Any],
    *,
    rate_baseline_per_s: float = RAW_RATE_BASELINE_PER_S,
    rate_per_star: float = RAW_RATE_PER_STAR,
    partial_support_exponent: float = 1.0,
    scale: str = RAW_SPEED_SCALE,
) -> dict[str, Any]:
    coverage = previous._coverage_view(  # noqa: SLF001 - frozen adapter
        dict(bundle),
        include_double_tap=True,
    )
    evidence_confidence = _clamp(
        _finite_nonnegative(coverage.get("ratio"))
    )
    if rate_per_star <= 0.0:
        raise ValueError("rate_per_star must be positive")
    records = _raw_records(
        bundle,
        rate_baseline_per_s=rate_baseline_per_s,
        rate_per_star=rate_per_star,
    )
    frontier = _frontier(
        records,
        evidence_confidence=evidence_confidence,
        partial_support_exponent=partial_support_exponent,
    )
    public_frontier = select_public_frontier(
        frontier,
        components=("establishment", "sustain"),
        policy_id=RAW_SPEED_PUBLIC_FRONTIER_POLICY_ID,
    )
    establishment = frontier["establishment"]
    assert isinstance(establishment, Mapping)
    frontier_status = str(frontier.get("status") or "INSUFFICIENT_EVIDENCE")
    has_positive_mechanism_evidence = (
        frontier_status == "FULL"
        and frontier.get("physical_peak") is not None
        and establishment.get("frontier_star") is not None
    )
    value = _finite_nonnegative(public_frontier.get("frontier_star"))
    selected_component = public_frontier.get("selected_component")
    selected_payload = (
        frontier.get(selected_component)
        if isinstance(selected_component, str)
        else None
    )
    support = _clamp(
        _finite_nonnegative(
            selected_payload.get("support")
            if isinstance(selected_payload, Mapping)
            else None
        )
    )
    peak_rate = max(
        (_finite_nonnegative(record.get("rate_per_s")) for record in records),
        default=0.0,
    )
    peak_record = max(
        records,
        key=lambda record: (
            _finite_nonnegative(record.get("difficulty")),
            -_finite_nonnegative(record.get("time_ms")),
        ),
        default=None,
    )
    physical_peak_details = {
        "star": frontier["physical_peak"],
        "unit": "star_equivalent",
        "scale_method": scale,
        "atomic_window": (
            None
            if peak_record is None
            else {
                "start_ms": peak_record.get("time_ms"),
                "end_ms": _finite_nonnegative(peak_record.get("time_ms"))
                + _finite_nonnegative(peak_record.get("duration_ms")),
                "duration_ms": peak_record.get("duration_ms"),
                "rate_per_s": peak_record.get("rate_per_s"),
                "episode_id": peak_record.get("episode_id"),
                "double_tap_feasibility": peak_record.get(
                    "double_tap_feasibility"
                ),
            }
        ),
    }
    published_status = (
        coverage["status"] if has_positive_mechanism_evidence else "INSUFFICIENT"
    )
    reason = (
        "NO_POSITIVE_RAW_SPEED_MECHANISM_EVIDENCE"
        if not has_positive_mechanism_evidence
        else "COMPLETE_EVIDENCE"
        if published_status == "FULL"
        else "PARTIAL_EVIDENCE"
        if published_status == "DEGRADED"
        else "INSUFFICIENT_EVIDENCE_COVERAGE"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": published_status,
        "reason": reason,
        # Compatibility/publication path: beta.8 publishes the established
        # frontier while keeping the unattenuated instantaneous peak explicit.
        "value": value,
        "physical_peak": frontier["physical_peak"],
        "physical_peak_details": physical_peak_details,
        "evidence_confidence": frontier["evidence_confidence"],
        "establishment": frontier["establishment"],
        "sustain": frontier["sustain"],
        "recurrence": frontier["recurrence"],
        "public_frontier": public_frontier,
        "combined_frontier_star": frontier["combined_frontier_star"],
        "support": support,
        "counterevidence": (
            0.0 if coverage["status"] == "INSUFFICIENT" else 1.0 - support
        ),
        "activation": support,
        "evidence_count": len(records),
        "coverage": coverage,
        "winning_run": _winning_run(
            records,
            frontier,
            rate_baseline_per_s=rate_baseline_per_s,
            rate_per_star=rate_per_star,
        ),
        "winning_window": None,
        "total_sr_used": False,
        "scale": scale,
        "signals": {
            "scale": scale,
            "physical_peak_unit": "star_equivalent",
            "physical_peak_rate_per_s": peak_rate,
            "sample_count": len(records),
            "effective_pair_weight": sum(
                _finite_nonnegative(record.get("weight")) for record in records
            ),
            "frontier_engine": SUPPORT_FRONTIER_SCHEMA_VERSION,
            "frontier_policy": frontier.get("policy"),
            "public_value_policy": "SELECTED_SUPPORT_FRONTIER_STAR",
            "public_frontier_policy": RAW_SPEED_PUBLIC_FRONTIER_POLICY_ID,
            "rate_baseline_per_s": rate_baseline_per_s,
            "rate_per_star": rate_per_star,
            "partial_support_exponent": partial_support_exponent,
            "confidence_not_applied_to_value": True,
            "event_bundle_basis_schema_version": EVENT_BUNDLE_BASIS_SCHEMA_VERSION,
        },
    }


def _stamina_measure(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return the frozen bounded Stamina scale with double-tap-aware mass."""

    frozen_bundle = dict(bundle)
    coverage = previous._coverage_view(  # noqa: SLF001 - frozen adapter
        frozen_bundle,
        include_double_tap=True,
    )
    if coverage["status"] == "INSUFFICIENT":
        return previous._empty_measure(  # noqa: SLF001 - frozen adapter
            "INSUFFICIENT",
            coverage,
        )

    best: dict[str, Any] | None = None
    for block in previous._tap_blocks(frozen_bundle):  # noqa: SLF001
        for threshold in previous._STAMINA_RATE_BANDS:  # noqa: SLF001
            for segment in previous._weighted_segments(  # noqa: SLF001
                block,
                threshold,
            ):
                facts = previous._segment_facts(  # noqa: SLF001
                    segment,
                    threshold,
                    apply_double_tap=True,
                )
                effective_pairs = facts["effective_pairs"]
                rate = facts["rate_per_s"]
                wall_s = facts["wall_duration_s"]
                notes_activation = 1.0 - math.exp(
                    -max(0.0, effective_pairs - 4.0) / 8.0
                )
                duration_activation = 1.0 - math.exp(-wall_s / 4.0)
                speed_activation = previous._smoothstep(  # noqa: SLF001
                    5.0,
                    7.0,
                    rate,
                )
                repetition = 0.85 + 0.15 * (
                    1.0 - math.exp(-wall_s / 25.0)
                )
                speed_pressure = (max(0.0, rate - 4.0) / 8.0) ** 1.55
                load = (
                    speed_pressure
                    * notes_activation**0.65
                    * duration_activation**0.35
                    * repetition
                )
                value = 10.0 * (1.0 - math.exp(-0.75 * load))
                activation = (
                    speed_activation * notes_activation * duration_activation
                )
                candidate = dict(facts)
                candidate.update(
                    {
                        # Preserve the frozen bounded Stamina scale exactly.
                        "value": _clamp(value, 0.0, 10.0),
                        "activation": activation,
                        "notes_activation": notes_activation,
                        "duration_activation": duration_activation,
                        "speed_pressure": speed_pressure,
                        "repetition": repetition,
                    }
                )
                if best is None or candidate["value"] > best["value"]:
                    best = candidate

    if best is None:
        result = previous._empty_measure(  # noqa: SLF001 - frozen adapter
            coverage["status"],
            coverage,
        )
        result["signals"] = {
            "run_count": 0,
            "scale": "BOUNDED_0_10",
            "double_tap_weight_policy": STAMINA_DOUBLE_TAP_WEIGHT_POLICY,
        }
        return result

    support = _clamp(best["value"] / 10.0)
    return {
        "status": coverage["status"],
        "value": best["value"],
        "support": support,
        "counterevidence": 1.0 - support,
        "activation": best["activation"],
        "evidence_count": best["observed_pairs"],
        "coverage": coverage,
        "winning_run": best,
        "winning_window": None,
        "total_sr_used": False,
        "signals": {
            "rate_per_s": best["rate_per_s"],
            "wall_duration_s": best["wall_duration_s"],
            "effective_pairs": best["effective_pairs"],
            "opportunity_pairs": best["opportunity_pairs"],
            "double_tap_feasibility_mean": best[
                "double_tap_feasibility_mean"
            ],
            "notes_activation": best["notes_activation"],
            "duration_activation": best["duration_activation"],
            "repetition_within_winning_run": best["repetition"],
            "scale": "BOUNDED_0_10",
            "double_tap_weight_policy": STAMINA_DOUBLE_TAP_WEIGHT_POLICY,
        },
    }


def _finger_event_weight(event: Mapping[str, Any]) -> float | None:
    """Return non-double-tappable Finger evidence without inventing missing zero."""

    if not event.get("double_tap_valid"):
        return None
    feasibility = event.get("double_tap_feasibility")
    if isinstance(feasibility, bool):
        return None
    try:
        number = float(feasibility)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        return None
    return 1.0 - number


def _finger_measure(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Measure established rhythm control after removing double-tap relief.

    The v02 cadence, predictability, recovery, window, and unbounded value
    formulas stay intact.  The only mechanism change is that a contrast between
    adjacent execution intervals receives the smaller of their two independent
    single-alternation weights.  Equivalently, its evidence mass is
    ``1 - max(adjacent double_tap_feasibility)``.  This suppresses both sides of
    a cheesable stacked double while leaving genuine non-cheesable rhythm
    changes bit-for-bit unchanged.
    """

    frozen_bundle = dict(bundle)
    coverage = previous._coverage_view(  # noqa: SLF001 - frozen adapter
        frozen_bundle,
        include_double_tap=True,
    )
    if coverage["status"] == "INSUFFICIENT":
        result = previous._empty_measure(  # noqa: SLF001 - frozen adapter
            "INSUFFICIENT",
            coverage,
        )
        result["signals"] = {
            "transition_count": 0,
            "cadence_membership": "CONTINUOUS_LOG_RATIO",
            "scale": FINGER_CONTROL_SCALE,
            "double_tap_weight_policy": FINGER_DOUBLE_TAP_WEIGHT_POLICY,
        }
        return result

    best: dict[str, Any] | None = None
    total_transition_count = 0
    unavailable_transition_count = 0
    for block in previous._tap_blocks(frozen_bundle):  # noqa: SLF001
        if len(block) < 2:
            continue
        dts = [float(event["execution_dt_ms"]) for event in block]
        strengths = [
            previous._cadence_strength(dts, index)  # noqa: SLF001
            for index in range(len(dts))
        ]
        event_weights = [_finger_event_weight(event) for event in block]
        baselines = [
            0.85
            * (1000.0 / dt / 10.0) ** 0.65
            * (1.0 - math.exp(-max(0.0, strength - 1.0) / 8.0))
            for dt, strength in zip(dts, strengths)
        ]

        # Missing double-tap observations are structural evidence boundaries.
        # Keep separate transition runs so a six-second window cannot bridge
        # unavailable events and borrow support from both sides.
        transition_runs: list[list[dict[str, Any]]] = []
        transitions: list[dict[str, Any]] = []
        for index in range(1, len(block)):
            weight_a = event_weights[index - 1]
            weight_b = event_weights[index]
            if weight_a is None or weight_b is None:
                unavailable_transition_count += 1
                if transitions:
                    transition_runs.append(transitions)
                    transitions = []
                continue

            contrast = abs(math.log2(dts[index - 1] / dts[index]))
            amplitude = 1.0 - math.exp(-contrast / 0.45)
            if amplitude <= 0.0:
                continue
            rate = 1000.0 / min(dts[index - 1], dts[index])
            speed = (rate / 10.0) ** 0.65
            establishment = 1.0 - math.exp(
                -min(strengths[index - 1], strengths[index]) / 3.0
            )
            motif = previous._motif_predictability(dts, index)  # noqa: SLF001
            pulse = previous._pulse_predictability(dts, index)  # noqa: SLF001
            predictability = max(motif, pulse)
            recovery = 1.0 / (
                1.0 + (max(dts[index - 1], dts[index]) / 450.0) ** 2
            )
            hold = max(
                float(block[index - 1]["hold_ratio"]),
                float(block[index]["hold_ratio"]),
            )
            cost = (
                speed
                * (0.25 + 1.05 * amplitude)
                * (0.65 + 0.35 * establishment)
                * (1.0 + 0.10 * hold)
                * (1.0 - 0.75 * predictability)
                * recovery
            )
            mechanism_weight = min(weight_a, weight_b)
            transitions.append(
                {
                    "time_ms": float(block[index]["start_ms"]),
                    "event_index": index,
                    "cost": cost,
                    "rate_per_s": rate,
                    "contrast_octaves": contrast,
                    "amplitude": amplitude,
                    "predictability": predictability,
                    "pulse_predictability": pulse,
                    "mechanism_weight": mechanism_weight,
                    "double_tap_feasibility": 1.0 - mechanism_weight,
                }
            )
        if transitions:
            transition_runs.append(transitions)

        total_transition_count += sum(len(run) for run in transition_runs)
        for run in transition_runs:
            left = 0
            for right, transition in enumerate(run):
                while run[left]["time_ms"] < transition["time_ms"] - 6000.0:
                    left += 1
                window = run[left : right + 1]
                first_event_index = max(0, window[0]["event_index"] - 1)
                last_event_index = window[-1]["event_index"]
                weighted_baselines = [
                    baselines[index] * float(event_weights[index] or 0.0)
                    for index in range(first_event_index, last_event_index + 1)
                ]
                local_baseline = min(1.5, max(weighted_baselines, default=0.0))
                duration_s = max(
                    3.0,
                    (window[-1]["time_ms"] - window[0]["time_ms"])
                    / 1000.0
                    + 0.5,
                )
                raw_load = sum(item["cost"] ** 1.30 for item in window) / duration_s
                load = (
                    sum(
                        item["cost"] ** 1.30 * item["mechanism_weight"]
                        for item in window
                    )
                    / duration_s
                )
                transition_peak = 3.50 * load**0.60
                value = transition_peak + local_baseline
                effective_weight = sum(
                    item["mechanism_weight"] for item in window
                )
                mean_predictability = (
                    sum(
                        item["predictability"] * item["mechanism_weight"]
                        for item in window
                    )
                    / effective_weight
                    if effective_weight > 0.0
                    else 1.0
                )
                activation = 1.0 - math.exp(
                    -sum(
                        item["amplitude"] * item["mechanism_weight"]
                        for item in window
                    )
                    / 3.0
                )
                candidate = {
                    "block_id": block[0]["block_id"],
                    "start_ms": window[0]["time_ms"],
                    "end_ms": window[-1]["time_ms"],
                    "transition_count": len(window),
                    "effective_transition_weight": effective_weight,
                    "double_tap_relief_mean": 1.0
                    - effective_weight / len(window),
                    "raw_load_per_s": raw_load,
                    "load_per_s": load,
                    "transition_peak": transition_peak,
                    "local_baseline": local_baseline,
                    "mean_predictability": mean_predictability,
                    "activation": activation,
                    "value": value,
                }
                if best is None or candidate["value"] > best["value"]:
                    best = candidate

    if best is None:
        result = previous._empty_measure(  # noqa: SLF001 - frozen adapter
            coverage["status"],
            coverage,
        )
        result["signals"] = {
            "transition_count": 0,
            "unavailable_transition_count": unavailable_transition_count,
            "cadence_membership": "CONTINUOUS_LOG_RATIO",
            "scale": FINGER_CONTROL_SCALE,
            "double_tap_weight_policy": FINGER_DOUBLE_TAP_WEIGHT_POLICY,
        }
        return result

    support = _clamp(
        best["activation"] * (1.0 - 0.50 * best["mean_predictability"])
    )
    return {
        "status": coverage["status"],
        "value": best["value"],
        "support": support,
        "counterevidence": 1.0 - support,
        "activation": best["activation"],
        "evidence_count": total_transition_count,
        "coverage": coverage,
        "winning_run": None,
        "winning_window": best,
        "total_sr_used": False,
        "signals": {
            "transition_count": total_transition_count,
            "unavailable_transition_count": unavailable_transition_count,
            "winning_transition_count": best["transition_count"],
            "winning_effective_transition_weight": best[
                "effective_transition_weight"
            ],
            "winning_double_tap_relief_mean": best["double_tap_relief_mean"],
            "transition_peak": best["transition_peak"],
            "winning_window_baseline": best["local_baseline"],
            "mean_predictability": best["mean_predictability"],
            "cadence_membership": "CONTINUOUS_LOG_RATIO",
            "scale": FINGER_CONTROL_SCALE,
            "double_tap_weight_policy": FINGER_DOUBLE_TAP_WEIGHT_POLICY,
            "confidence_not_applied_to_value": True,
        },
    }


def extract_tapping_measures(
    rows: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return beta.8 Raw/Stamina/Finger repairs plus frozen v02 Endurance."""

    bundle = build_event_bundle(rows)
    measures = {
        "raw_speed": _raw_speed_measure(bundle),
        "stamina": _stamina_measure(bundle),
        "finger_control": _finger_measure(bundle),
        "endurance": previous._endurance_measure(bundle),  # noqa: SLF001
    }
    for axis, measure in measures.items():
        measure["schema_version"] = SCHEMA_VERSION
        if axis == "endurance":
            measure["implementation_basis_schema_version"] = previous.SCHEMA_VERSION
        elif axis in {"stamina", "finger_control"}:
            measure["implementation_basis_schema_version"] = SCHEMA_VERSION
    return measures


__all__ = [
    "SCHEMA_VERSION",
    "VERSION",
    "EVENT_BUNDLE_BASIS_SCHEMA_VERSION",
    "RAW_SPEED_SCALE",
    "FINGER_CONTROL_SCALE",
    "FINGER_DOUBLE_TAP_WEIGHT_POLICY",
    "STAMINA_DOUBLE_TAP_WEIGHT_POLICY",
    "RAW_SPEED_PUBLIC_FRONTIER_POLICY_ID",
    "FULL_COVERAGE",
    "DEGRADED_COVERAGE",
    "PHRASE_GAP_MS",
    "RAW_RATE_BASELINE_PER_S",
    "RAW_RATE_PER_STAR",
    "build_event_bundle",
    "extract_tapping_measures",
]
