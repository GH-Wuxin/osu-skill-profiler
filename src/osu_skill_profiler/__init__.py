"""osu-skill-profiler: deterministic infrastructure for osu!standard skill profiling.

This package intentionally has no runtime dependencies and no knowledge of any
specific bot or consumer. It implements the non-human foundation only:

  .osu -> parse -> normalize -> deterministic features -> segments
        -> dataset infrastructure -> weak supervision infrastructure
        -> future annotation/model contracts

Everything skill-related that has not been validated by human labels is
explicitly PROVISIONAL. No score is ever fabricated.
"""

from __future__ import annotations

__version__ = "0.1.0"

SCHEMA_VERSION = "0.1.0"

