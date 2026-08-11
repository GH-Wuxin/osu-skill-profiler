"""Numerical utilities transcribed from the pinned ppy/osu ``DiffUtils``.

Independent reimplementation of the audited upstream semantics (commit
``b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e``, difficulty version 20260706).
The functions are pure and deterministic; they intentionally mirror upstream
clamps (Smoothstep/Smootherstep/ReverseLerp/Clamp are semantic clamps present
in the official source, not statistical clipping).
"""

from __future__ import annotations

import math


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def smoothstep(x: float, start: float, end: float) -> float:
    x = clamp((x - start) / (end - start), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def smootherstep(x: float, start: float, end: float) -> float:
    x = clamp((x - start) / (end - start), 0.0, 1.0)
    return x * x * x * (x * (6.0 * x - 15.0) + 10.0)


def reverse_lerp(x: float, start: float, end: float) -> float:
    return clamp((x - start) / (end - start), 0.0, 1.0)


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation (``double.Lerp`` in the pinned upstream)."""

    return a + (b - a) * t


def smoothstep_bell_curve(x: float, mean: float, width: float) -> float:
    x = x - mean
    x = (width - x) if x > 0 else (width + x)
    return smoothstep(x, 0.0, width)


def smoothstep_bell_curve_unit(x: float) -> float:
    """Parameterless smoothstep bell curve: 1 at 0.5, 0 at 0 and 1."""

    x = 0.5 - abs(x - 0.5)
    x = clamp(x * 2.0, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def bell_curve(x: float, mean: float, width: float, multiplier: float = 1.0) -> float:
    return multiplier * math.exp(math.e * -(pow(x - mean, 2) / pow(width, 2)))


def logistic(x: float, midpoint_offset: float, multiplier: float, max_value: float = 1.0) -> float:
    return max_value / (1.0 + math.exp(multiplier * (midpoint_offset - x)))


def logistic_simple(exponent: float, max_value: float = 1.0) -> float:
    return max_value / (1.0 + math.exp(exponent))


def norm(p: float, *values: float) -> float:
    total = 0.0
    for value in values:
        total += pow(value, p)
    return pow(total, 1.0 / p)


def ms_to_bpm(ms: float, delimiter: int = 4) -> float:
    return 60000.0 / (ms * delimiter)


def bpm_to_ms(bpm: float, delimiter: int = 4) -> float:
    return 60000.0 / delimiter / bpm


def to_radians(degrees: float) -> float:
    return math.radians(degrees)


def to_degrees(radians: float) -> float:
    return math.degrees(radians)


__all__ = [
    "clamp",
    "smoothstep",
    "smootherstep",
    "reverse_lerp",
    "lerp",
    "smoothstep_bell_curve",
    "smoothstep_bell_curve_unit",
    "bell_curve",
    "logistic",
    "logistic_simple",
    "norm",
    "ms_to_bpm",
    "bpm_to_ms",
    "to_radians",
    "to_degrees",
]
