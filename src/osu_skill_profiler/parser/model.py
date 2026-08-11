"""Data model for a parsed .osu beatmap.

Only osu!standard (mode 0) is supported by the profiler. The parser itself is
kept permissive enough to read the fields the profiler needs and to reject
clearly malformed input deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TimingPoint:
    """A single [TimingPoints] entry.

    Red (uninherited) points define BPM; green (inherited) points define an SV
    multiplier relative to the most recent red point. ``degenerate`` marks
    points whose beat length is non-finite or overflows (seen in some real
    meme/Aspire maps); such points fall back to 120 BPM / SV 1.0 downstream.
    """

    time_ms: float
    beat_length_ms: float
    meter: int
    uninherited: bool
    bpm: Optional[float] = None
    sv: float = 1.0
    degenerate: bool = False


@dataclass(frozen=True)
class HitObject:
    """One parsed [HitObjects] entry."""

    x: float
    y: float
    time_ms: float
    object_type: str
    type_bits: int
    hit_sound: int
    slider_curve_type: Optional[str] = None
    slider_points: tuple[tuple[float, float], ...] = ()
    slider_slides: Optional[int] = None
    slider_pixel_length: Optional[float] = None
    spinner_end_ms: Optional[float] = None

    def end_time_ms(self) -> float:
        if self.object_type == "spinner":
            return float(self.spinner_end_ms or self.time_ms)
        return self.time_ms


@dataclass(frozen=True)
class Beatmap:
    """Normalized container for everything the parser extracts from a .osu file."""

    format_version: int
    mode: int
    metadata: dict = field(default_factory=dict)
    difficulty: dict = field(default_factory=dict)
    timing_points: tuple[TimingPoint, ...] = ()
    hit_objects: tuple[HitObject, ...] = ()
