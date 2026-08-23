"""Bounded Hidden reading proxy for Map Demand.

The direction of the terms follows ppy/osu's current ReadingEvaluator Hidden
branch (preempt, visible density, and cursor velocity).  This is deliberately
not a clean-room port of the full per-object evaluator: angle repetition,
opacity history, and perfect-stack bonuses are outside Local Signal 0.3.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

HIDDEN_PROXY_VERSION = "hidden_proxy_v0.1.0"
HIDDEN_EVIDENCE_TAG = "HEURISTIC_PROXY_INSPIRED_BY_PPY_HIDDEN"
HIDDEN_MAX_READING_BONUS = 0.20
_RAW_SQUASH_MIDPOINT = 2.5


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def hidden_pressure(
    local_rows: Iterable[dict[str, Any]], features: dict[str, Any] | None
) -> float | None:
    """Return a finite 0..1 map-level HD pressure proxy (linear p90)."""
    density = None if features is None else _finite(features.get("section.density_per_s_p95"))
    if density is None:
        density = 0.0
    density = max(0.0, min(density, 20.0))

    values: list[float] = []
    for row in local_rows:
        if row.get("ls.object_type") == "spinner":
            continue
        preempt = _finite(row.get("ls.preempt_ms"))
        if preempt is None or preempt <= 0.0:
            continue
        delta = _finite(row.get("ls.adjusted_delta_time_ms"))
        jump = _finite(row.get("ls.lazy_jump_distance_cs_normalised"))
        velocity = 1.0
        if delta is not None and jump is not None:
            velocity = max(1.0, min(10.0, max(jump, 0.0) / max(delta, 25.0)))

        # Approximate simultaneously relevant objects from section density;
        # cap the count so pathological finite maps cannot dominate output.
        visible_count = min(12.0, density * min(preempt / 1000.0, 3.0))
        preempt_factor = preempt**2.2 * 0.01
        density_factor = visible_count**3.3 * 3.0
        raw = ((preempt_factor + density_factor) * velocity * 0.01) ** 0.4 * 0.28
        pressure = raw / (raw + _RAW_SQUASH_MIDPOINT)
        values.append(max(0.0, min(1.0, pressure)))

    if not values:
        return None
    values.sort()
    if len(values) == 1:
        return values[0]
    position = 0.9 * (len(values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def apply_hidden_reading_adjustment(
    reading_axis: dict[str, Any], pressure: Any
) -> dict[str, Any]:
    """Apply a bounded remaining-headroom bonus to an emitted reading axis."""
    result = dict(reading_axis)
    value = _finite(pressure)
    score = _finite(result.get("score"))
    if result.get("status") != "EMITTED" or value is None or score is None:
        return result
    value = max(0.0, min(1.0, value))
    score = max(0.0, score)
    bonus_fraction = HIDDEN_MAX_READING_BONUS * value
    # V0.6 scores are star-equivalent / 10 and may exceed 1.0. A bounded
    # remaining-headroom adjustment would incorrectly reduce or pin extreme
    # maps, so HD is a bounded multiplicative premium instead.
    result["score"] = score * (1.0 + bonus_fraction)
    result["demand_star_equivalent"] = result["score"] * 10.0
    result["percentile_rank"] = None
    result["scale_method"] = f"{result.get('scale_method', '')}+HD_MULTIPLICATIVE_PREMIUM"
    result["method"] = f"{result.get('method', '')}+{HIDDEN_EVIDENCE_TAG}"
    evidence = list(result.get("evidence", []))
    evidence.append(
        {
            "component": "reading_hidden_pressure",
            "value": value,
            "rank": None,
            "weight": HIDDEN_MAX_READING_BONUS,
            "source": "HD preempt/density/velocity bounded p90 proxy",
            "evidence_tag": HIDDEN_EVIDENCE_TAG,
            "version": HIDDEN_PROXY_VERSION,
            "combination": "bounded_multiplicative_bonus",
        }
    )
    result["evidence"] = evidence
    return result
