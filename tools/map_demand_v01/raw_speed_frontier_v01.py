"""Shared Raw Speed assembly for frozen beta releases.

Beta.8 owns the linear v03 implementation.  Beta.9 and later use this module
so their rate calibration and frontier objective cannot mutate that frozen
module.  The caller supplies the versioned frontier evaluator and selector.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Callable, Iterable, Mapping

from . import tapping_axes_v03 as beta8
from . import axis_support_frontier_v01 as linear_frontier


FrontierEvaluator = Callable[[Iterable[Mapping[str, Any]], float], dict[str, Any]]
FrontierSelector = Callable[..., dict[str, Any]]


def _finite_nonnegative(value: Any, *, default: float = 0.0) -> float:
    return beta8._finite_nonnegative(value, default=default)  # noqa: SLF001


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return beta8._clamp(value, low, high)  # noqa: SLF001


def _validate_frontier(
    raw: Mapping[str, Any],
    *,
    expected_schema_version: str,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise TypeError("support frontier must return a mapping")
    if raw.get("schema_version") != expected_schema_version:
        raise ValueError(
            "support frontier schema mismatch: "
            f"expected {expected_schema_version!r}, "
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


def legacy_powered_frontier(
    samples: Iterable[Mapping[str, Any]],
    evidence_confidence: float,
    *,
    partial_support_exponent: float,
) -> dict[str, Any]:
    """Replay beta.9's post-selection exponent exactly.

    This intentionally preserves the beta.9 objective-order bug.  Beta.9.1
    uses the v02 frontier engine instead of this compatibility function.
    """

    result = beta8._frontier(  # noqa: SLF001
        samples,
        evidence_confidence=evidence_confidence,
    )
    exponent = float(partial_support_exponent)
    if not math.isfinite(exponent) or exponent < 1.0:
        raise ValueError("partial_support_exponent must be finite and at least 1")
    if exponent == 1.0:
        return result

    adjusted = copy.deepcopy(result)
    target = linear_frontier.RAW_SPEED_SUPPORT_POLICY.frontier_support_target
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


def raw_records(
    bundle: Mapping[str, Any],
    *,
    rate_baseline_per_s: float,
    rate_per_star: float,
) -> list[dict[str, Any]]:
    if rate_per_star <= 0.0:
        raise ValueError("rate_per_star must be positive")
    records: list[dict[str, Any]] = []
    for block in beta8.previous._tap_blocks(dict(bundle)):  # noqa: SLF001
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
                    "section_id": 0,
                    "weight": 1.0 - feasibility,
                    "rate_per_s": rate,
                    "double_tap_feasibility": feasibility_raw,
                }
            )
    return records


def winning_run(
    records: list[Mapping[str, Any]],
    frontier: Mapping[str, Any],
    *,
    rate_baseline_per_s: float,
    rate_per_star: float,
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
    total_weight = sum(
        _finite_nonnegative(item.get("weight")) for item in winner
    )
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
        "rate_per_s": (
            weighted_rate / total_weight if total_weight > 0.0 else 0.0
        ),
        "rate_band_per_s": rate_baseline_per_s + threshold * rate_per_star,
        "double_tap_feasibility_mean": (
            sum(valid_feasibilities) / len(valid_feasibilities)
            if valid_feasibilities
            else None
        ),
        "frontier_threshold_star": threshold,
    }


def raw_speed_measure(
    bundle: Mapping[str, Any],
    *,
    rate_baseline_per_s: float,
    rate_per_star: float,
    partial_support_exponent: float,
    scale: str,
    output_schema_version: str,
    event_bundle_basis_schema_version: str,
    frontier_engine_schema_version: str,
    frontier_evaluator: FrontierEvaluator,
    frontier_selector: FrontierSelector,
    public_frontier_policy_id: str,
) -> dict[str, Any]:
    coverage = beta8.previous._coverage_view(  # noqa: SLF001
        dict(bundle),
        include_double_tap=True,
    )
    evidence_confidence = _clamp(
        _finite_nonnegative(coverage.get("ratio"))
    )
    records = raw_records(
        bundle,
        rate_baseline_per_s=rate_baseline_per_s,
        rate_per_star=rate_per_star,
    )
    frontier = _validate_frontier(
        frontier_evaluator(records, evidence_confidence),
        expected_schema_version=frontier_engine_schema_version,
    )
    public_frontier = frontier_selector(
        frontier,
        components=("establishment", "sustain"),
        policy_id=public_frontier_policy_id,
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
        "schema_version": output_schema_version,
        "status": published_status,
        "reason": reason,
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
        "winning_run": winning_run(
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
            "frontier_engine": frontier_engine_schema_version,
            "frontier_policy": frontier.get("policy"),
            "public_value_policy": "SELECTED_SUPPORT_FRONTIER_STAR",
            "public_frontier_policy": public_frontier_policy_id,
            "rate_baseline_per_s": rate_baseline_per_s,
            "rate_per_star": rate_per_star,
            "partial_support_exponent": partial_support_exponent,
            "confidence_not_applied_to_value": True,
            "event_bundle_basis_schema_version": (
                event_bundle_basis_schema_version
            ),
        },
    }


__all__ = [
    "legacy_powered_frontier",
    "raw_records",
    "raw_speed_measure",
    "winning_run",
]
