"""Reference preprocessing boundary (Layer B, v0.1).

Builds per-object ``RefObject`` records aligned to the .osu file order used
by the pinned ppy/osu difficulty pipeline.  Observable Layer A primitives
(distances, timing, angles, lazy slider geometry) are reused from the audited
Local Signal v0.2 extractor; this module adds only the small reference-only
derivations that official evaluators need (small-circle bonus, repeat-slider
travel distance, raw positions, geometry-blocked flags).

This is an intentional reuse of the private ``_extract_rows`` API (SLF001);
the reference layer never mutates Layer A rows and never changes local signal
semantics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ...parser.model import Beatmap
from ...signals.extractor import LocalSignalExtractor


@dataclass(frozen=True)
class RefObject:
    """One difficulty-row-aligned object for official reference evaluators."""

    original_index: int
    time_sorted_index: int
    start_time_ms: float
    end_time_ms: float
    object_type: str

    delta_time_ms: Optional[float]
    adjusted_delta_time_ms: Optional[float]
    last_object_end_delta_time_ms: Optional[float]
    minimum_jump_time_ms: Optional[float]

    preempt_ms: Optional[float]
    fade_in_ms: Optional[float]
    hit_window_great_ms: Optional[float]
    radius_px: Optional[float]
    cs_scale: Optional[float]
    small_circle_bonus: Optional[float]

    position: tuple[float, float]
    lazy_end_position: Optional[tuple[float, float]]
    tail_position: Optional[tuple[float, float]]

    jump_distance_cs: Optional[float]
    lazy_jump_distance_cs: Optional[float]
    minimum_jump_distance_cs: Optional[float]
    lazy_travel_distance_cs: Optional[float]
    lazy_travel_time_ms: Optional[float]
    travel_distance_cs: Optional[float]
    travel_time_ms: Optional[float]

    angle_rad: Optional[float]
    normalised_vector_angle_rad: Optional[float]
    double_tap_feasibility: Optional[float]

    spinner_context: bool
    geometry_blocked: bool
    provenance: tuple[str, ...] = field(default_factory=tuple)

    @property
    def row_index(self) -> int:
        """Difficulty row index; the first raw object has no difficulty row."""

        return self.original_index - 1

    @property
    def is_slider(self) -> bool:
        return self.object_type == "slider"

    @property
    def is_spinner(self) -> bool:
        return self.object_type == "spinner"


_BLOCKED_FLAGS = (
    "path_blocked:",
    "slider_spans_exceeded:",
    "slider_tick_count_exceeded",
)


def _is_blocked(provenance) -> bool:
    if not isinstance(provenance, (tuple, list)):
        return False
    return any(
        flag.startswith(_BLOCKED_FLAGS[0])
        or flag.startswith(_BLOCKED_FLAGS[1])
        or flag == _BLOCKED_FLAGS[2]
        for flag in provenance
    )


def build_ref_objects(beatmap: Beatmap) -> list[RefObject]:
    """Build file-order ``RefObject`` records from a parsed beatmap.

    Raw object 0 carries structural identity and no difficulty-row values
    (the pinned upstream difficulty list starts at the second raw object).
    """

    geometries_out: list = []
    rows = LocalSignalExtractor()._extract_rows(beatmap, _geometries_out=geometries_out)  # noqa: SLF001 - intentional isolated reuse
    objects = list(beatmap.hit_objects)
    result: list[RefObject] = []

    for row in rows:
        index = int(row["ls.original_index"])
        obj = objects[index]
        provenance = tuple(row["ls.provenance"] or ())
        blocked = _is_blocked(provenance)
        object_type = str(row["ls.object_type"])
        is_slider = object_type == "slider"

        lazy_travel_cs = row.get("ls.lazy_travel_distance_cs_normalised")
        lazy_travel_time = row.get("ls.lazy_travel_time_ms")
        span_count = row.get("ls.slider_span_count")
        travel_distance_cs: Optional[float] = None
        travel_time_ms: Optional[float] = None
        if is_slider:
            if (
                not blocked
                and isinstance(lazy_travel_cs, (int, float))
                and math.isfinite(float(lazy_travel_cs))
                and isinstance(span_count, (int, float))
            ):
                repeat_count = max(0, int(span_count) - 1)
                travel_distance_cs = float(lazy_travel_cs) * max(1.0, math.pow(repeat_count, 0.3))
            if isinstance(lazy_travel_time, (int, float)) and math.isfinite(float(lazy_travel_time)):
                travel_time_ms = max(float(lazy_travel_time), 25.0)
        else:
            travel_time_ms = 0.0

        radius = row.get("ls.radius_px")
        small_circle_bonus: Optional[float] = None
        if isinstance(radius, (int, float)) and math.isfinite(float(radius)):
            small_circle_bonus = max(1.0, 1.0 + (30.0 - float(radius)) / 70.0)

        lazy_end: Optional[tuple[float, float]] = None
        lx = row.get("ls.lazy_end_position_x_px")
        ly = row.get("ls.lazy_end_position_y_px")
        if isinstance(lx, (int, float)) and isinstance(ly, (int, float)):
            lazy_end = (float(lx), float(ly))

        tail_position: Optional[tuple[float, float]] = None
        if is_slider:
            geometry = geometries_out[index] if index < len(geometries_out) else None
            if geometry is not None and geometry.tail_position is not None:
                tail_position = geometry.tail_position

        result.append(
            RefObject(
                original_index=index,
                time_sorted_index=int(row["ls.time_sorted_index"]),
                start_time_ms=float(row["ls.start_time_ms"]),
                end_time_ms=float(row["ls.end_time_ms"]),
                object_type=object_type,
                delta_time_ms=_optional_float(row.get("ls.delta_time_ms")),
                adjusted_delta_time_ms=_optional_float(row.get("ls.adjusted_delta_time_ms")),
                last_object_end_delta_time_ms=_optional_float(row.get("ls.last_object_end_delta_time_ms")),
                minimum_jump_time_ms=_optional_float(row.get("ls.minimum_jump_time_ms")),
                preempt_ms=_optional_float(row.get("ls.preempt_ms")),
                fade_in_ms=_optional_float(row.get("ls.fade_in_ms")),
                hit_window_great_ms=_optional_float(row.get("ls.hit_window_great_ms")),
                radius_px=radius if isinstance(radius, (int, float)) else None,
                cs_scale=_optional_float(row.get("ls.cs_scale")),
                small_circle_bonus=small_circle_bonus,
                position=(float(obj.x), float(obj.y)),
                lazy_end_position=lazy_end,
                tail_position=tail_position,
                jump_distance_cs=_optional_float(row.get("ls.jump_distance_cs_normalised")),
                lazy_jump_distance_cs=_optional_float(row.get("ls.lazy_jump_distance_cs_normalised")),
                minimum_jump_distance_cs=_optional_float(row.get("ls.minimum_jump_distance_cs_normalised")),
                lazy_travel_distance_cs=_optional_float(lazy_travel_cs),
                lazy_travel_time_ms=_optional_float(lazy_travel_time),
                travel_distance_cs=travel_distance_cs,
                travel_time_ms=travel_time_ms,
                angle_rad=_optional_float(row.get("ls.slider_aware_angle_rad")),
                normalised_vector_angle_rad=_optional_float(row.get("ls.normalised_vector_angle_rad")),
                double_tap_feasibility=_optional_float(row.get("ls.double_tap_feasibility")),
                spinner_context=bool(row.get("ls.spinner_context")),
                geometry_blocked=blocked,
                provenance=provenance,
            )
        )
    return result


def _optional_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


__all__ = ["RefObject", "build_ref_objects"]
