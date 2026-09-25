"""Estimate a player Skill Rating from prepared normalized evidence JSONL.

This command reads evidence; it does not fetch scores or reinterpret raw score
fields. A score/replay adapter must first emit the normalized axis outcomes
required by ``player_skill_rating_v01``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01.player_skill_rating_v01 import (  # noqa: E402
    estimate_player_skill_profile,
)


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            text = line.strip()
            if not text:
                continue
            record = json.loads(text, parse_constant=_reject_constant)
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: evidence must be an object")
            records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--player-id")
    parser.add_argument("--normalization-id")
    parser.add_argument("--reference-lower", type=float)
    parser.add_argument("--reference-upper", type=float)
    parser.add_argument("--min-evidence", type=int, default=3)
    parser.add_argument("--min-maps", type=int, default=3)
    parser.add_argument("--min-timepoints", type=int, default=2)
    args = parser.parse_args()
    reference_range = None
    if args.reference_lower is not None or args.reference_upper is not None:
        if args.reference_lower is None or args.reference_upper is None:
            parser.error("reference-lower and reference-upper must be supplied together")
        reference_range = (args.reference_lower, args.reference_upper)
    result = estimate_player_skill_profile(
        _load_records(args.records),
        player_id=args.player_id,
        normalization_id=args.normalization_id,
        reference_range=reference_range,
        min_evidence=args.min_evidence,
        min_maps=args.min_maps,
        min_timepoints=args.min_timepoints,
    )
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
