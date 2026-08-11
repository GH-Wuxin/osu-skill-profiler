"""Deterministic parser for the .osu text format (osu!standard subset).

The parser extracts only what the profiler needs:

- metadata: BeatmapID / BeatmapSetID / mapper / difficulty name
- difficulty: AR / OD / CS / HP / slider multiplier / tick rate
- timing: red (BPM) and green (SV) timing points, in file order
- hit objects: circles, sliders and spinners with their geometric data

Anything else (storyboard, colours, skin hints) is intentionally ignored.
Malformed input raises OsuParseError with a stable, human-readable message.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from .model import Beatmap, HitObject, TimingPoint


class OsuParseError(ValueError):
    """Raised when a .osu file cannot be parsed deterministically."""


_FLOAT_KEYS = {
    "HPDrainRate",
    "CircleSize",
    "OverallDifficulty",
    "ApproachRate",
    "SliderMultiplier",
    "SliderTickRate",
}
_INT_KEYS = {"BeatmapID", "BeatmapSetID", "Mode"}
_TEXT_KEYS = {"Title", "TitleUnicode", "Artist", "ArtistUnicode", "Creator", "Version"}


def _parse_float(value: str, what: str) -> float:
    try:
        number = float(value.strip())
    except ValueError as exc:
        raise OsuParseError(f"invalid numeric value for {what}: {value!r}") from exc
    if not math.isfinite(number):
        raise OsuParseError(f"non-finite numeric value for {what}: {value!r}")
    return number


def _parse_beat_length(value: str) -> float:
    """Parse a timing point beat length, allowing NaN/Inf (degenerate maps)."""

    try:
        return float(value.strip())
    except ValueError as exc:
        raise OsuParseError(f"invalid timing point beat length: {value!r}") from exc


def _parse_slider_pixel_length(value: str) -> Optional[float]:
    """Parse a slider pixel length, treating NaN/Inf as unknown (degenerate).

    Some real (meme/Aspire) maps store ``NaN`` as the pixel length. The value
    carries no geometry, so it is mapped to ``None`` exactly like a missing
    field; downstream normalization then treats the slider duration as unknown.
    """

    try:
        number = float(value.strip())
    except ValueError as exc:
        raise OsuParseError(f"invalid slider pixel length: {value!r}") from exc
    return number if math.isfinite(number) else None


def _parse_timing_point(line: str) -> TimingPoint:
    parts = line.split(",")
    if len(parts) < 2:
        raise OsuParseError(f"timing point has fewer than 2 fields: {line!r}")
    time_ms = _parse_float(parts[0], "timing point time")
    beat_length = _parse_beat_length(parts[1])
    try:
        meter = int(parts[2].strip() or "4") if len(parts) >= 3 else 4
    except ValueError as exc:
        raise OsuParseError(f"invalid timing point meter: {parts[2]!r}") from exc
    # Legacy v3/v4 timing lines may omit the trailing fields. When field 7 is
    # missing, a positive beat length means a red (uninherited) point and a
    # negative beat length means a green (inherited/SV) point.
    if len(parts) >= 7:
        try:
            uninherited = int(parts[6].strip() or "0") == 1
        except ValueError as exc:
            raise OsuParseError(f"invalid timing point uninherited flag: {parts[6]!r}") from exc
    else:
        uninherited = beat_length > 0
    degenerate = not math.isfinite(beat_length)
    if uninherited and not degenerate and beat_length == 0:
        raise OsuParseError(f"red timing point with zero beat length: {line!r}")
    if uninherited:
        bpm = None
        try:
            candidate = 60000.0 / beat_length
            bpm = candidate if math.isfinite(candidate) else None
        except OverflowError:
            bpm = None
        if bpm is None:
            degenerate = True
        return TimingPoint(
            time_ms=time_ms,
            beat_length_ms=beat_length,
            meter=meter,
            uninherited=True,
            bpm=bpm,
            sv=1.0,
            degenerate=degenerate,
        )
    if not degenerate and beat_length == 0:
        raise OsuParseError(f"green timing point with zero beat length: {line!r}")
    sv = None
    try:
        candidate = -100.0 / beat_length
        sv = candidate if math.isfinite(candidate) else None
    except OverflowError:
        sv = None
    if sv is None:
        degenerate = True
        sv = 1.0
    return TimingPoint(
        time_ms=time_ms,
        beat_length_ms=beat_length,
        meter=meter,
        uninherited=False,
        bpm=None,
        sv=sv,
        degenerate=degenerate,
    )


def _parse_slider_params(params: str) -> tuple[Optional[str], tuple[tuple[float, float], ...], Optional[int], Optional[float]]:
    segments = params.split(",")
    curve_and_points = segments[0]
    if "|" not in curve_and_points:
        # Some real (Aspire) maps store a single-letter curve type with no
        # control points, e.g. "I" or "L". Accept those; anything longer is
        # malformed.
        candidate = curve_and_points.strip()
        if len(candidate) == 1 and candidate.isalpha():
            return candidate, (), None, None
        raise OsuParseError(f"slider params missing curve type: {params!r}")
    curve_type = curve_and_points.split("|", 1)[0]
    raw_points = curve_and_points.split("|")[1:]
    points: list[tuple[float, float]] = []
    for raw in raw_points:
        if ":" not in raw:
            # Some real (Aspire) maps embed non-coordinate tokens such as
            # "I|C|K|S|B" inside the control-point list. They carry no
            # geometry, so they are skipped deterministically.
            continue
        try:
            x_raw, y_raw = raw.split(":", 1)
            points.append((_parse_float(x_raw, "slider point x"), _parse_float(y_raw, "slider point y")))
        except ValueError as exc:
            raise OsuParseError(f"invalid slider point {raw!r}: {exc}") from exc
    slides: Optional[int] = None
    pixel_length: Optional[float] = None
    if len(segments) >= 2:
        slides = int(segments[1].strip())
    if len(segments) >= 3:
        pixel_length = _parse_slider_pixel_length(segments[2])
    return curve_type, tuple(points), slides, pixel_length


def _parse_hit_object(line: str) -> HitObject:
    parts = line.split(",")
    if len(parts) < 5:
        raise OsuParseError(f"hit object has fewer than 5 fields: {line!r}")
    x = _parse_float(parts[0], "hit object x")
    y = _parse_float(parts[1], "hit object y")
    time_ms = _parse_float(parts[2], "hit object time")
    type_bits = int(parts[3].strip())
    hit_sound = int(parts[4].strip() or "0")
    params = parts[5] if len(parts) > 5 else ""

    if type_bits & 128:
        raise OsuParseError("mania hit objects are not supported by the osu!standard profiler")
    if type_bits & 1:
        return HitObject(x, y, time_ms, "circle", type_bits, hit_sound)
    if type_bits & 2:
        curve_type, points, _, _ = _parse_slider_params(params)
        slides: Optional[int] = None
        pixel_length: Optional[float] = None
        if len(parts) >= 7:
            slides = int(parts[6].strip())
        if len(parts) >= 8:
            pixel_length = _parse_slider_pixel_length(parts[7])
        return HitObject(
            x,
            y,
            time_ms,
            "slider",
            type_bits,
            hit_sound,
            slider_curve_type=curve_type,
            slider_points=points,
            slider_slides=slides if slides is not None else None,
            slider_pixel_length=pixel_length,
        )
    if type_bits & 8:
        end_raw = params.split(",", 1)[0].strip()
        if not end_raw:
            raise OsuParseError(f"spinner without end time: {line!r}")
        return HitObject(x, y, time_ms, "spinner", type_bits, hit_sound, spinner_end_ms=_parse_float(end_raw, "spinner end time"))
    raise OsuParseError(f"unsupported hit object type bits {type_bits} in line: {line!r}")


def parse_osu(text: str) -> Beatmap:
    """Parse .osu text into a Beatmap. Pure and deterministic."""

    format_version: Optional[int] = None
    mode = 0
    metadata: dict = {}
    difficulty: dict = {}
    timing_points: list[TimingPoint] = []
    hit_objects: list[HitObject] = []
    section: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("osu file format v"):
            try:
                format_version = int(line.rsplit("v", 1)[1].strip())
            except ValueError as exc:
                raise OsuParseError(f"malformed format line: {line!r}") from exc
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section is None:
            continue
        if section == "General":
            if line.startswith("Mode:"):
                mode = int(line.split(":", 1)[1].strip() or "0")
        elif section == "Metadata":
            for key in _TEXT_KEYS:
                if line.startswith(f"{key}:"):
                    metadata[key] = line.split(":", 1)[1].strip()
                    break
            for key in _INT_KEYS:
                if line.startswith(f"{key}:"):
                    raw = line.split(":", 1)[1].strip()
                    metadata[key] = int(raw) if raw else 0
                    break
        elif section == "Difficulty":
            for key in _FLOAT_KEYS:
                if line.startswith(f"{key}:"):
                    difficulty[key] = _parse_float(line.split(":", 1)[1], key)
                    break
        elif section == "TimingPoints":
            timing_points.append(_parse_timing_point(line))
        elif section == "HitObjects":
            hit_objects.append(_parse_hit_object(line))

    if format_version is None:
        raise OsuParseError("missing 'osu file format vNN' header")
    if not hit_objects:
        raise OsuParseError("no hit objects found")
    timing_points.sort(key=lambda point: (point.time_ms, 0 if point.uninherited else 1))
    return Beatmap(
        format_version=format_version,
        mode=mode,
        metadata=metadata,
        difficulty=difficulty,
        timing_points=tuple(timing_points),
        hit_objects=tuple(hit_objects),
    )


def parse_osu_file(path: str | Path) -> Beatmap:
    """Read and parse a .osu file from disk."""

    data = Path(path).read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16")
    else:
        text = data.decode("utf-8-sig", errors="replace")
    return parse_osu(text)


def effective_timing(timing_points: tuple[TimingPoint, ...], time_ms: float) -> tuple[float, float, float]:
    """Return (bpm, sv, beat_length_ms) in effect at ``time_ms``.

    Rules (documented behaviour):
    - before the first timing point, the first point's values apply;
    - the most recent point at or before ``time_ms`` wins;
    - a green point inherits BPM from the most recent red point, or defaults
      to 120 BPM when no red point exists yet.
    """

    if not timing_points:
        return 120.0, 1.0, 500.0
    current: Optional[TimingPoint] = None
    last_red: Optional[TimingPoint] = None
    for point in timing_points:
        if point.time_ms > time_ms:
            break
        current = point
        if point.uninherited:
            last_red = point
    if current is None:
        current = timing_points[0]
        if current.uninherited:
            last_red = current
    if current.uninherited:
        if current.degenerate or current.bpm is None:
            return 120.0, 1.0, 500.0
        return current.bpm, 1.0, current.beat_length_ms
    sv = 1.0 if current.degenerate else current.sv
    if last_red is not None and last_red.bpm is not None and not last_red.degenerate:
        return last_red.bpm, sv, last_red.beat_length_ms
    return 120.0, sv, 500.0
