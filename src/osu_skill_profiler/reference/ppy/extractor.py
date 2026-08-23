"""Reference Signal extraction (Layer B, v0.2 current; v0.1 replayable).

``ReferenceSignalExtractor.extract`` runs the pinned ppy/osu per-object
evaluators over the file-order timeline and aligns them with stable object
identity (original index / time-sorted index / start time).  Segment
summaries are descriptive statistics only; they never form a final segment
difficulty scalar.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Callable, Optional

from ...parser.model import Beatmap
from .contract import (
    LEGACY_REFERENCE_VERSION,
    REFERENCE_NUMERIC_SIGNALS,
    REFERENCE_SCHEMA,
    REFERENCE_VERSION,
    SEGMENT_AGGREGATION_POLICY,
    SEGMENT_SUMMARY_FIELDS,
    UPSTREAM_COMMIT,
    UPSTREAM_DIFFICULTY_VERSION,
    UPSTREAM_REPOSITORY,
    reference_schema,
)
from . import evaluators as _evaluators
from .preprocess import RefObject, build_ref_objects

SEGMENT_WINDOW_MS = 5000.0

_EVALUATORS: dict[str, Callable[..., Optional[float]]] = {
    "ref.ppy.snap_include_sliders": lambda objects, i: _evaluators.snap_aim(objects, i, True),
    "ref.ppy.snap_exclude_sliders": lambda objects, i: _evaluators.snap_aim(objects, i, False),
    "ref.ppy.agility": _evaluators.agility,
    "ref.ppy.flow_include_sliders": lambda objects, i: _evaluators.flow_aim(objects, i, True),
    "ref.ppy.flow_exclude_sliders": lambda objects, i: _evaluators.flow_aim(objects, i, False),
    "ref.ppy.speed": _evaluators.speed,
    "ref.ppy.rhythm": _evaluators.rhythm,
    "ref.ppy.speed_with_rhythm": _evaluators.speed_with_rhythm,
    "ref.ppy.reading": _evaluators.reading,
}


def _percentile(sorted_values: list[float], q: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _scaled_mean(values: list[float]) -> float:
    scale = max(abs(v) for v in values)
    if scale == 0:
        return 0.0
    return scale * (sum(v / scale for v in values) / len(values))


def reference_rows(
    objects: list[RefObject],
    reference_version: str = REFERENCE_VERSION,
) -> list[dict]:
    """Emit per-object reference rows aligned to the raw file order."""

    reference_schema(reference_version)

    rows: list[dict[str, Any]] = []
    for obj in objects:
        i = obj.original_index
        row: dict[str, Any] = {
            "ref.original_index": i,
            "ref.time_sorted_index": obj.time_sorted_index,
            "ref.start_time_ms": obj.start_time_ms,
            "ref.object_type": obj.object_type,
        }
        provenance: list[str] = list(obj.provenance)
        if i == 0:
            for signal in REFERENCE_NUMERIC_SIGNALS:
                row[signal] = None
            provenance.append("no_difficulty_row")
        else:
            for signal, evaluator in _EVALUATORS.items():
                value: Optional[float]
                try:
                    if signal == "ref.ppy.reading":
                        value = _evaluators.reading(
                            objects,
                            i,
                            reference_version=reference_version,
                        )
                    else:
                        value = evaluator(objects, i)
                except (ArithmeticError, ValueError):
                    value = None
                if value is not None and not math.isfinite(value):
                    value = None
                row[signal] = value
                if value is None:
                    provenance.append(f"ref_unavailable:{signal}")
        row["ref.provenance"] = tuple(dict.fromkeys(provenance))
        rows.append(row)
    return rows


def segment_reference_signals(
    rows: list[dict],
    window_ms: float = SEGMENT_WINDOW_MS,
) -> list[dict]:
    """Fixed-time-window descriptive summaries for reference signals."""

    if not rows:
        return []
    ordered = sorted(rows, key=lambda r: (r["ref.start_time_ms"], r["ref.original_index"]))
    start = ordered[0]["ref.start_time_ms"]
    end = max(r["ref.start_time_ms"] for r in ordered)
    buckets: dict[int, list[int]] = {}
    for pos, row in enumerate(ordered):
        bucket = int((row["ref.start_time_ms"] - start) // window_ms)
        buckets.setdefault(bucket, []).append(pos)

    segments: list[dict] = []
    for bucket in sorted(buckets):
        indices = buckets[bucket]
        window_start = start + bucket * window_ms
        window_end = window_start + window_ms
        members = [ordered[idx] for idx in indices]
        aggregates: dict[str, dict[str, float]] = {}
        for signal in REFERENCE_NUMERIC_SIGNALS:
            policy = SEGMENT_AGGREGATION_POLICY.get(signal, SEGMENT_SUMMARY_FIELDS)
            values = [
                float(member[signal])
                for member in members
                if isinstance(member.get(signal), (int, float)) and math.isfinite(float(member[signal]))
            ]
            if not values:
                continue
            sorted_values = sorted(values)
            agg: dict[str, float] = {}
            if "count" in policy:
                agg["count"] = len(values)
            if "mean" in policy:
                agg["mean"] = _scaled_mean(values)
            if "median" in policy:
                agg["median"] = statistics.median(values)
            if "p90" in policy:
                agg["p90"] = _percentile(sorted_values, 0.90)
            if "p95" in policy:
                agg["p95"] = _percentile(sorted_values, 0.95)
            if "max" in policy:
                agg["max"] = sorted_values[-1]
            aggregates[signal] = agg
        segments.append(
            {
                "start_ms": window_start,
                "end_ms": window_end,
                "start_idx": indices[0],
                "end_idx": indices[-1] + 1,
                "object_count": len(members),
                "aggregates": aggregates,
            }
        )
    return segments


class ReferenceSignalExtractor:
    """Extract a version-selected official reference signal table."""

    reference_version = REFERENCE_VERSION

    def __init__(self, reference_version: str = REFERENCE_VERSION) -> None:
        reference_schema(reference_version)
        self.reference_version = reference_version

    def extract(self, beatmap: Beatmap) -> dict:
        objects = build_ref_objects(beatmap, reference_version=self.reference_version)
        rows = reference_rows(objects, reference_version=self.reference_version)
        segments = segment_reference_signals(rows)
        missing_counts: dict[str, int] = {}
        nonfinite_counts: dict[str, int] = {}
        for row in rows:
            for signal in REFERENCE_NUMERIC_SIGNALS:
                value = row.get(signal)
                if value is None:
                    missing_counts[signal] = missing_counts.get(signal, 0) + 1
                elif isinstance(value, float) and not math.isfinite(value):
                    nonfinite_counts[signal] = nonfinite_counts.get(signal, 0) + 1
        geometry_blocked = sum(1 for obj in objects if obj.geometry_blocked)
        return {
            "reference_version": self.reference_version,
            "upstream_repository": UPSTREAM_REPOSITORY,
            "upstream_commit": UPSTREAM_COMMIT,
            "upstream_difficulty_version": UPSTREAM_DIFFICULTY_VERSION,
            "classification": "OFFICIAL_REFERENCE",
            "object_count": len(rows),
            "objects": rows,
            "segments": segments,
            "summary": {
                "segment_count": len(segments),
                "geometry_blocked_object_count": geometry_blocked,
                "missing_counts": missing_counts,
                "nonfinite_counts": nonfinite_counts,
                "schema_field_count": len(REFERENCE_SCHEMA),
            },
        }


__all__ = ["ReferenceSignalExtractor", "segment_reference_signals", "reference_rows", "SEGMENT_WINDOW_MS"]
