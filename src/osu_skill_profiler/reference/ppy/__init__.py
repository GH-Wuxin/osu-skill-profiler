"""Pinned ppy/osu reference evaluator namespace (Layer B, v0.1).

All semantics are pinned to ppy/osu commit
``b45c1a26e5db0ef94d6ecaca4fed9f77ce78e29e`` (difficulty version 20260706).
The implementation is an independent Python reimplementation from the audited
upstream semantics; no upstream source file is vendored and no network access
is required.

Exposed signals:

  ref.ppy.snap_include_sliders
  ref.ppy.snap_exclude_sliders
  ref.ppy.agility
  ref.ppy.flow_include_sliders
  ref.ppy.flow_exclude_sliders
  ref.ppy.speed
  ref.ppy.rhythm
  ref.ppy.speed_with_rhythm
  ref.ppy.reading

Final difficulty aggregation (strain peaks, weighted sums, star rating, PP)
is intentionally NOT implemented or exposed.
"""

from .contract import (
    LEGACY_REFERENCE_VERSION,
    REFERENCE_NUMERIC_SIGNALS,
    REFERENCE_SCHEMA,
    REFERENCE_VERSION,
    REFERENCE_SCHEMA_V01,
    REFERENCE_SCHEMA_V02,
    SEGMENT_SUMMARY_FIELDS,
    UPSTREAM_COMMIT,
    UPSTREAM_DIFFICULTY_VERSION,
    UPSTREAM_REPOSITORY,
)
from .extractor import ReferenceSignalExtractor, segment_reference_signals

__all__ = [
    "REFERENCE_SCHEMA",
    "REFERENCE_SCHEMA_V01",
    "REFERENCE_SCHEMA_V02",
    "REFERENCE_NUMERIC_SIGNALS",
    "REFERENCE_VERSION",
    "LEGACY_REFERENCE_VERSION",
    "SEGMENT_SUMMARY_FIELDS",
    "UPSTREAM_REPOSITORY",
    "UPSTREAM_COMMIT",
    "UPSTREAM_DIFFICULTY_VERSION",
    "ReferenceSignalExtractor",
    "segment_reference_signals",
]
