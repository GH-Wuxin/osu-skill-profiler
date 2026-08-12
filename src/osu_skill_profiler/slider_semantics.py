"""Canonical slider repeat/span and timing terminology.

This module is the single semantic boundary shared by corrected Feature,
Local, and Reference layers.  The raw ``.osu`` slider ``slides`` value is a
span count.  A repeat is a transition between spans, therefore a valid slider
has ``repeat_count = span_count - 1``.

Historical Feature v0.1 and Local v0.2 compatibility paths remain elsewhere;
new semantic code must use the explicit names defined here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

SLIDER_SEMANTICS_VERSION = "1.0.0"

SLIDER_SEMANTICS_CONTRACT = {
    "version": SLIDER_SEMANTICS_VERSION,
    "parsed_slides": "the .osu slider field; number of spans",
    "span_count": "max(1, parsed_slides) under the existing malformed guard",
    "repeat_count": "span_count - 1",
    "single_span_duration_ms": "path_distance / velocity",
    "total_slider_duration_ms": "single_span_duration_ms * span_count",
    "end_time_ms": "start_time_ms + total_slider_duration_ms",
}


@dataclass(frozen=True)
class SliderCounts:
    """Canonical counts plus any compatibility-guard provenance."""

    repeat_count: int
    span_count: int
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class SliderTiming:
    """Canonical one-span and total slider durations."""

    single_span_duration_ms: float
    total_slider_duration_ms: float


def canonical_slider_counts(parsed_slides: Optional[int]) -> SliderCounts:
    """Interpret the raw ``.osu`` slides field without semantic overloading."""

    provenance: list[str] = []
    if parsed_slides is None:
        span_count = 1
    else:
        span_count = int(parsed_slides)
        if span_count <= 0:
            provenance.append("slider_slides_nonpositive")
            span_count = 1
    return SliderCounts(
        repeat_count=span_count - 1,
        span_count=span_count,
        provenance=tuple(provenance),
    )


def canonical_slider_timing(
    path_distance: float,
    velocity_px_per_ms: float,
    span_count: int,
) -> Optional[SliderTiming]:
    """Return finite positive canonical timing, else ``None``.

    This deliberately performs no clipping.  Callers retain their existing
    provenance/blocked behavior when the timing is unavailable.
    """

    if span_count < 1 or velocity_px_per_ms <= 0:
        return None
    try:
        single_span_duration_ms = path_distance / velocity_px_per_ms
        total_slider_duration_ms = single_span_duration_ms * span_count
    except OverflowError:
        return None
    if (
        not math.isfinite(single_span_duration_ms)
        or not math.isfinite(total_slider_duration_ms)
        or single_span_duration_ms <= 0
        or total_slider_duration_ms <= 0
    ):
        return None
    return SliderTiming(
        single_span_duration_ms=single_span_duration_ms,
        total_slider_duration_ms=total_slider_duration_ms,
    )


__all__ = [
    "SLIDER_SEMANTICS_CONTRACT",
    "SLIDER_SEMANTICS_VERSION",
    "SliderCounts",
    "SliderTiming",
    "canonical_slider_counts",
    "canonical_slider_timing",
]
