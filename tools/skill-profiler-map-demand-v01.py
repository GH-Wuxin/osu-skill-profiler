#!/usr/bin/env python3
"""Thin entry point for the experimental MAP_DEMAND_ATOMIC_V02 tools package."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from map_demand_v01.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
