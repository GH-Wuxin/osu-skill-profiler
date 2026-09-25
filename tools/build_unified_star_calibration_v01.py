"""Build a bounded unified-star calibration artifact from prepared records.

The tool never walks the Songs directory.  The caller supplies a JSONL corpus
whose rows already contain map identity, ppy NM reference context, and raw axis
values.  A separate reference artifact supplies the sorted ppy NM population.
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

from map_demand_v01.unified_star_scale_v01 import (  # noqa: E402
    fit_calibration,
    save_calibration,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            text = line.strip()
            if not text:
                continue
            value = json.loads(text, parse_constant=_reject_constant)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: record must be an object")
            records.append(value)
    return records


def _reference_stars(path: Path) -> list[float]:
    payload = _load_json(path)
    if isinstance(payload, list):
        return [float(value) for value in payload]
    if not isinstance(payload, dict):
        raise ValueError("reference artifact must be a list or object")
    candidates = [
        payload.get("nm_stars"),
        (payload.get("demand_scale") or {}).get("nm_stars"),
        (payload.get("reference_distribution") or {}).get("nm_stars"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            return [float(value) for value in candidate]
    raise ValueError("reference artifact has no NM star distribution")


def build(args: argparse.Namespace) -> Path:
    records = _load_records(Path(args.records))
    reference = _reference_stars(Path(args.reference))
    calibration = fit_calibration(
        records,
        reference,
        source_scope=args.source_scope,
        corpus_id=args.corpus_id,
        min_formal_maps=args.min_formal_maps,
        min_formal_axis_samples=args.min_formal_axis_samples,
        min_formal_strata=args.min_formal_strata,
    )
    target = save_calibration(calibration, args.output)
    print(json.dumps({
        "output": str(target),
        "calibration_id": calibration["calibration_id"],
        "status": calibration["status"],
        "map_count": calibration["map_count"],
        "axis_counts": calibration["axis_counts"],
        "strata": calibration["strata"],
    }, ensure_ascii=False, sort_keys=True))
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="prepared map corpus JSONL")
    parser.add_argument("--reference", type=Path, required=True, help="ppy NM star artifact JSON")
    parser.add_argument("--output", type=Path, required=True, help="output calibration.json or directory")
    parser.add_argument("--source-scope", required=True)
    parser.add_argument("--corpus-id")
    parser.add_argument("--min-formal-maps", type=int, default=256)
    parser.add_argument("--min-formal-axis-samples", type=int, default=128)
    parser.add_argument("--min-formal-strata", type=int, default=4)
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
