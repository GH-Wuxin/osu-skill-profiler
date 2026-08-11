"""Small, dependency-free descriptive statistics with stable semantics."""

from __future__ import annotations

import math
from typing import Iterable, Optional


def _finite(values: Iterable[Optional[float]]) -> list[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def percentile(sorted_values: list[float], q: float) -> Optional[float]:
    """Linear-interpolation percentile on a sorted list (0 <= q <= 1)."""

    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def describe(values: Iterable[Optional[float]]) -> dict:
    """Return mean/std/p50/p75/p90/p95/max/min for a value sequence.

    Empty sequences produce None for every key; std of a single value is 0.
    """

    data = _finite(values)
    if not data:
        return {"mean": None, "std": None, "p50": None, "p75": None, "p90": None, "p95": None, "max": None, "min": None}
    data.sort()
    scale = max(abs(v) for v in data)
    if scale == 0:
        mean = 0.0
        std = 0.0
    else:
        mean = scale * (sum(v / scale for v in data) / len(data))
        std = scale * math.sqrt(sum(((v - mean) / scale) ** 2 for v in data) / len(data))
    return {
        "mean": mean,
        "std": std,
        "p50": percentile(data, 0.50),
        "p75": percentile(data, 0.75),
        "p90": percentile(data, 0.90),
        "p95": percentile(data, 0.95),
        "max": data[-1],
        "min": data[0],
    }


def shannon_entropy_bits(counts: Iterable[int]) -> float:
    """Shannon entropy (bits) over a distribution of counts."""

    values = [int(c) for c in counts if int(c) > 0]
    total = sum(values)
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in values)
