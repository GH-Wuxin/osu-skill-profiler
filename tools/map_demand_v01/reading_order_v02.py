"""Availability-aware local-order Reading measure.

This is an opt-in successor to :mod:`reading_order_v01`.  It deliberately
keeps the published v1 pressure calculation for explainable object sequences,
while putting a versioned evidence boundary around it:

* missing decision geometry is not a zero Reading observation;
* exact simultaneous heads are preserved as an unsupported ordering case;
* partial signal coverage is reported and gated before a value is published;
* Hidden may add memory pressure, but never reduce the NM value; and
* no total-star or other-axis input participates in the measure.

The module consumes the release-agnostic bundle from
``paired_transition_geometry_v01``.  Difficulty fallback (including legacy
AR=OD materialisation) belongs at the extractor boundary; this module only
uses the resolved per-object preempt carried by the bundle.
"""

from __future__ import annotations

from collections import Counter
import math
from typing import Any, Iterable, Mapping

from . import paired_transition_geometry_v01 as paired
from . import reading_order_v01 as legacy


SCHEMA_VERSION = "reading_order_v0.3.0"
LOCAL_SIGNAL_VERSION = paired.LOCAL_SIGNAL_VERSION

FULL = "FULL"
DEGRADED = "DEGRADED"
INSUFFICIENT = "INSUFFICIENT"

FULL_COVERAGE_MIN = 0.95
MIN_PUBLISHABLE_COVERAGE = 0.80

SCALE = "INDEPENDENT_LOCAL_ORDER_MEMORY_LOG_SCALE"
AGGREGATION = "EIGHT_CONSECUTIVE_DECISIONS_WITHIN_THREE_SECONDS"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def _normalise_mods(effective_mods: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(mod).strip().upper()
                for mod in effective_mods
                if str(mod).strip()
            }
        )
    )


def _validate_bundle(bundle: Mapping[str, Any]) -> None:
    if not isinstance(bundle, Mapping):
        raise TypeError("Reading v2 requires a transition bundle mapping")
    if bundle.get("schema_version") != paired.SCHEMA_VERSION:
        raise ValueError("Reading v2 requires paired transition geometry v0.1")
    if bundle.get("local_signal_version") != LOCAL_SIGNAL_VERSION:
        raise ValueError(
            "Reading v2 requires Local Signal "
            f"{LOCAL_SIGNAL_VERSION}"
        )
    if not isinstance(bundle.get("objects"), list):
        raise ValueError("Reading v2 bundle.objects must be a list")
    if not isinstance(bundle.get("transitions"), list):
        raise ValueError("Reading v2 bundle.transitions must be a list")


def _object_ready(obj: Any) -> bool:
    if not isinstance(obj, Mapping) or not obj.get("geometry_available"):
        return False
    required = ("time", "x", "y", "radius", "preempt")
    values = {key: _finite(obj.get(key)) for key in required}
    return (
        all(values[key] is not None for key in required)
        and values["radius"] > 0.0
        and values["preempt"] > 0.0
        and obj.get("structural_status")
        not in {
            "SIMULTANEOUS_ISOLATED",
            "INVALID_TIME_ISOLATED",
            "NONMONOTONIC_TIME_ISOLATED",
        }
    )


def _geometry_reasons(obj: Any) -> list[str]:
    if not isinstance(obj, Mapping):
        return ["MALFORMED_OBJECT"]
    reasons = obj.get("geometry_missing_reasons", [])
    if isinstance(reasons, list):
        clean = [str(reason) for reason in reasons if str(reason)]
        if clean:
            return clean
    return ["UNAVAILABLE_DECISION_GEOMETRY"]


def _decision_availability(
    bundle: Mapping[str, Any],
) -> tuple[int, int, float, set[tuple[int, int]], dict[str, int]]:
    objects = bundle["objects"]
    eligible_pairs: set[tuple[int, int]] = set()
    reasons: Counter[str] = Counter()
    transitions = bundle["transitions"]

    for transition in transitions:
        if not isinstance(transition, Mapping):
            reasons["MALFORMED_TRANSITION"] += 1
            continue
        from_index = transition.get("from_object_index")
        to_index = transition.get("to_object_index")
        if (
            isinstance(from_index, bool)
            or isinstance(to_index, bool)
            or not isinstance(from_index, int)
            or not isinstance(to_index, int)
            or not 0 <= from_index < len(objects)
            or not 0 <= to_index < len(objects)
        ):
            reasons["MALFORMED_TRANSITION_INDEX"] += 1
            continue
        source = objects[from_index]
        target = objects[to_index]
        wall_time = _finite(transition.get("wall_time_ms"))
        missing: list[str] = []
        if not _object_ready(source):
            missing.extend(_geometry_reasons(source))
        if not _object_ready(target):
            missing.extend(_geometry_reasons(target))
        if wall_time is None or wall_time <= 0.0:
            missing.append("NONPOSITIVE_DECISION_TIME")
        if missing:
            reasons.update(dict.fromkeys(missing, 1))
            continue
        eligible_pairs.add((from_index, to_index))

    ambiguous = bundle.get("ambiguous_transition_count", 0)
    if isinstance(ambiguous, bool) or not isinstance(ambiguous, int) or ambiguous < 0:
        raise ValueError("ambiguous_transition_count must be a non-negative integer")
    if ambiguous:
        reasons["UNSUPPORTED_SIMULTANEOUS_ORDER"] += ambiguous
    candidate_count = len(transitions) + ambiguous
    eligible_count = len(eligible_pairs)
    coverage = eligible_count / candidate_count if candidate_count else 0.0
    return (
        candidate_count,
        eligible_count,
        coverage,
        eligible_pairs,
        dict(sorted(reasons.items())),
    )


def _explainable_objects(
    objects: list[dict[str, Any]],
    eligible_pairs: set[tuple[int, int]],
) -> list[dict[str, Any]]:
    """Copy contiguous explainable runs without bridging missing objects."""

    result: list[dict[str, Any]] = []
    previous_source_index: int | None = None
    run = -1
    for source_index, obj in enumerate(objects):
        if not _object_ready(obj):
            previous_source_index = None
            continue
        linked = (
            previous_source_index is not None
            and (previous_source_index, source_index) in eligible_pairs
        )
        if not linked:
            run += 1
        current = dict(obj)
        current["segment"] = run
        current["block"] = run
        current["reading_source_object_index"] = source_index
        if not linked:
            # A missing object or structural separator begins a fresh causal
            # scene.  Do not let the compatibility placeholders bridge it.
            current.update(
                dt=0.0,
                distance=0.0,
                head_distance=0.0,
                free_time=0.0,
                turn=0.0,
                signed_turn=0.0,
                heading_rad=None,
            )
        result.append(current)
        previous_source_index = source_index
    return result


def _availability_reason(
    bundle: Mapping[str, Any],
    *,
    candidate_count: int,
    eligible_count: int,
    coverage: float,
    missing_reasons: Mapping[str, int],
) -> str:
    has_simultaneous_order = (
        int(bundle.get("simultaneous_group_count", 0) or 0) > 0
    )
    if not bundle["objects"]:
        if int(bundle.get("spinner_count", 0) or 0) > 0:
            return "NO_NONSPINNER_OBJECTS"
        return "NO_OBJECTS"
    if candidate_count == 0 or eligible_count == 0:
        if has_simultaneous_order:
            return "UNSUPPORTED_SIMULTANEOUS_ORDER"
        if missing_reasons.get("MISSING_PREEMPT", 0):
            return "MISSING_APPROACH_TIMING_CONTEXT"
        return "NO_VALID_READING_DECISION"
    if coverage < MIN_PUBLISHABLE_COVERAGE:
        return "INSUFFICIENT_DECISION_COVERAGE"
    if has_simultaneous_order:
        return "ISOLATED_SIMULTANEOUS_ORDER"
    if coverage < FULL_COVERAGE_MIN:
        return "PARTIAL_EVIDENCE"
    return "COMPLETE_EVIDENCE"


def _coverage_status(coverage: float) -> str:
    if coverage >= FULL_COVERAGE_MIN:
        return FULL
    if coverage >= MIN_PUBLISHABLE_COVERAGE:
        return DEGRADED
    return INSUFFICIENT


def _base_result(
    bundle: Mapping[str, Any],
    *,
    mods: tuple[str, ...],
    status: str,
    reason: str,
    candidate_count: int,
    eligible_count: int,
    coverage: float,
    missing_reasons: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "local_signal_version": LOCAL_SIGNAL_VERSION,
        "status": status,
        "reason": reason,
        "value": None,
        "support": 0.0,
        "counterevidence": 0.0,
        "eligible_count": eligible_count,
        "coverage": coverage,
        "activation": 0.0,
        "winning_section": None,
        "total_sr_used": False,
        "scale": SCALE,
        "aggregation": AGGREGATION,
        "signals": {
            "effective_mods": list(mods),
            "candidate_decision_count": candidate_count,
            "eligible_decision_count": eligible_count,
            # A structurally isolated ambiguity caps the public quality at
            # DEGRADED even when its numerical share is below five percent.
            "coverage_status": status,
            "missing_reasons": dict(missing_reasons),
            "source_row_count": int(bundle.get("source_row_count", 0) or 0),
            "nonspinner_object_count": len(bundle["objects"]),
            "spinner_count": int(bundle.get("spinner_count", 0) or 0),
            "simultaneous_group_count": int(
                bundle.get("simultaneous_group_count", 0) or 0
            ),
            "simultaneous_object_count": int(
                bundle.get("simultaneous_object_count", 0) or 0
            ),
            "availability_reason": reason,
        },
    }


def _winning_section(
    core: Mapping[str, Any], objects: list[dict[str, Any]]
) -> dict[str, Any]:
    start = _finite(core.get("start_ms"))
    end = _finite(core.get("end_ms"))
    winner = next(
        (
            obj
            for obj in reversed(objects)
            if end is not None and _finite(obj.get("time")) == end
        ),
        None,
    )
    support_count = int(core.get("support_count", 0) or 0)
    return {
        "segment": winner.get("segment") if winner else None,
        "block": winner.get("block") if winner else None,
        "run": winner.get("segment") if winner else None,
        "start_ms": start,
        "end_ms": end,
        "event_count": int(core.get("window_event_count", 0) or 0),
        "support_count": support_count,
        "support": _clamp(support_count / float(legacy.SUPPORT_EVENTS)),
        "value": float(core["value"]),
        "signals": dict(core.get("signals", {})),
    }


def extract_reading_measure(
    bundle: Mapping[str, Any], effective_mods: Iterable[str] = ()
) -> dict[str, Any]:
    """Return a versioned Reading measure from paired transition geometry.

    A publishable value is bit-for-bit the v1 core value for the explainable
    object runs.  Coverage and activation determine whether that value may be
    routed; they never turn unavailable observations into numeric zeroes.
    """

    _validate_bundle(bundle)
    mods = _normalise_mods(effective_mods)
    (
        candidate_count,
        eligible_count,
        coverage,
        eligible_pairs,
        missing_reasons,
    ) = _decision_availability(bundle)
    reason = _availability_reason(
        bundle,
        candidate_count=candidate_count,
        eligible_count=eligible_count,
        coverage=coverage,
        missing_reasons=missing_reasons,
    )
    status = _coverage_status(coverage)
    if (
        int(bundle.get("simultaneous_group_count", 0) or 0) > 0
        and status == FULL
    ):
        # The bundle has already removed the ambiguous group and both causal
        # boundaries from eligible_pairs.  Preserve all remaining independent
        # sections, but never describe the resulting evidence as FULL.
        status = DEGRADED
    if candidate_count == 0 or eligible_count == 0:
        status = INSUFFICIENT

    result = _base_result(
        bundle,
        mods=mods,
        status=status,
        reason=reason,
        candidate_count=candidate_count,
        eligible_count=eligible_count,
        coverage=coverage,
        missing_reasons=missing_reasons,
    )
    if status == INSUFFICIENT:
        return result

    explainable = _explainable_objects(bundle["objects"], eligible_pairs)
    novelty = paired.predictability(explainable)
    core = legacy.reading_measure(explainable, novelty, mods)
    if int(core.get("event_count", 0) or 0) != eligible_count:
        # This indicates a bundle/core contract mismatch, not observed zero
        # Reading.  Fail closed without throwing on adversarial input.
        result["status"] = INSUFFICIENT
        result["reason"] = "NO_VALID_READING_DECISION"
        result["signals"]["availability_reason"] = result["reason"]
        result["signals"]["core_event_count"] = int(
            core.get("event_count", 0) or 0
        )
        return result

    value = _finite(core.get("value"))
    if value is None or value < 0.0:
        result["status"] = INSUFFICIENT
        result["reason"] = "INVALID_READING_CORE_VALUE"
        result["signals"]["availability_reason"] = result["reason"]
        return result

    # Invert the v1 log scale into a bounded mechanism-strength diagnostic.
    # This does not clip or otherwise modify the published Reading value.
    support = _clamp(1.0 - 2.0 ** (-value / 4.05))
    result.update(
        value=value,
        support=support,
        counterevidence=(1.0 - support) * coverage,
        activation=coverage,
        winning_section=_winning_section(core, explainable),
    )
    result["signals"].update(
        core_event_count=int(core.get("event_count", 0) or 0),
        core_support_count=int(core.get("support_count", 0) or 0),
        neighbourhood_truncated_events=int(
            core.get("neighbourhood_truncated_events", 0) or 0
        ),
        visibility=core.get("visibility"),
        core_signals=dict(core.get("signals", {})),
    )
    return result


__all__ = [
    "SCHEMA_VERSION",
    "LOCAL_SIGNAL_VERSION",
    "FULL",
    "DEGRADED",
    "INSUFFICIENT",
    "FULL_COVERAGE_MIN",
    "MIN_PUBLISHABLE_COVERAGE",
    "extract_reading_measure",
]
