"""Experimental MAP_DEMAND_ATOMIC_V04.

This package lives under tools/ only. It must not be imported by production
src/osu_skill_profiler code paths and must never become a final model.
"""

from .contract import (
    ALGORITHM_ID,
    MAP_DEMAND_VERSION,
    SCHEMA_VERSION,
)

__all__ = ["ALGORITHM_ID", "MAP_DEMAND_VERSION", "SCHEMA_VERSION"]
