"""Build a bounded unified-star calibration artifact from prepared records.

The tool never walks the Songs directory.  The caller supplies a JSONL corpus
whose rows already contain map identity, one ppy reference context, and raw axis
values.  A separate reference artifact supplies the sorted ppy population for
that exact context.  Build one artifact per non-FL mod context; never mix HD,
DT, or other contexts into the NM ruler.
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
    canonical_mod_context,
    fit_calibration,
    save_calibration,
)
from map_demand_v01.osu_db_star_scale import read_standard_star_index  # noqa: E402


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


def _reference_stars(path: Path, mod_context: str) -> list[float]:
    mod_context = canonical_mod_context(mod_context)
    if path.is_dir():
        path = path / "calibration.json"
    if path.suffix.lower() == ".db":
        payload = read_standard_star_index(path)
        stars = (payload.get("stars_by_mod") or {}).get(str(mod_context).upper())
        if isinstance(stars, list) and stars:
            return [float(value) for value in stars]
        raise ValueError(f"osu!.db has no non-FL star distribution for {mod_context}")
    payload = _load_json(path)
    if isinstance(payload, list):
        return [float(value) for value in payload]
    if not isinstance(payload, dict):
        raise ValueError("reference artifact must be a list or object")
    candidates = [
        (payload.get("stars_by_mod") or {}).get(str(mod_context).upper()),
        (payload.get("mod_stars") or {}).get(str(mod_context).upper()),
        payload.get("nm_stars") if str(mod_context).upper() == "NM" else None,
        (payload.get("demand_scale") or {}).get("nm_stars")
        if str(mod_context).upper() == "NM" else None,
        (payload.get("reference_distribution") or {}).get("stars")
        if str(payload.get("mod_context") or "NM").upper() == str(mod_context).upper()
        else None,
        (payload.get("reference_distribution") or {}).get("nm_stars")
        if str(mod_context).upper() == "NM" else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            return [float(value) for value in candidate]
    raise ValueError(f"reference artifact has no star distribution for {mod_context}")


def build(args: argparse.Namespace) -> Path:
    records = _load_records(Path(args.records))
    mod_context = canonical_mod_context(args.mod_context)
    reference = _reference_stars(Path(args.reference), mod_context)
    calibration = fit_calibration(
        records,
        reference,
        source_scope=args.source_scope,
        corpus_id=args.corpus_id,
        mod_context=mod_context,
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
        "mod_context": calibration["mod_context"],
    }, ensure_ascii=False, sort_keys=True))
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="prepared map corpus JSONL")
    parser.add_argument("--reference", type=Path, required=True, help="ppy star artifact JSON for the selected mod context")
    parser.add_argument("--output", type=Path, required=True, help="output calibration.json or directory")
    parser.add_argument("--source-scope", required=True)
    parser.add_argument("--corpus-id")
    parser.add_argument("--mod-context", default="NM")
    parser.add_argument("--min-formal-maps", type=int, default=256)
    parser.add_argument("--min-formal-axis-samples", type=int, default=128)
    parser.add_argument("--min-formal-strata", type=int, default=4)
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
