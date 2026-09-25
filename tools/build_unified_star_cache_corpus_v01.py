"""Create a bounded common-scale corpus from an explicit .osu cache.

This is intentionally not a Songs scanner.  It processes only the directory
passed by the caller, one worker, and writes portable map IDs plus raw axis
values.  The resulting corpus is a candidate calibration input until the
declared breadth gates are satisfied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import model_v040_formal  # noqa: E402
from map_demand_v01.calibration import load_calibration  # noqa: E402
from map_demand_v01.osu_db_star_scale import read_nm_star_distribution  # noqa: E402
from osu_skill_profiler.formal_release import AXES  # noqa: E402


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324 - osu! beatmap identity


def _stratum(star: float, reference: list[float]) -> str:
    # Four fixed reference quartiles provide a stable coverage label; they are
    # not used as a model target or a weight.
    n = len(reference)
    cutoffs = [
        reference[int(0.25 * (n - 1))],
        reference[int(0.50 * (n - 1))],
        reference[int(0.75 * (n - 1))],
    ]
    if star <= cutoffs[0]:
        return "nm_q1"
    if star <= cutoffs[1]:
        return "nm_q2"
    if star <= cutoffs[2]:
        return "nm_q3"
    return "nm_q4"


def build(args: argparse.Namespace) -> dict[str, Any]:
    cache = Path(args.cache).resolve()
    db = read_nm_star_distribution(args.osu_db)
    reference_calibration = load_calibration(args.reference_calibration)
    reference = list(reference_calibration["demand_scale"]["nm_stars"])
    paths = sorted(cache.glob("*.osu"))
    if args.max_maps is not None:
        paths = paths[: args.max_maps]
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for path in paths:
        try:
            md5 = _md5(path)
            star = db["md5_to_nm_stars"].get(md5.lower())
            if star is None:
                skipped.append({"file": path.name, "reason": "nm_star_not_in_osu_db"})
                continue
            rows, features, metadata = model_v040_formal.extract_from_path(str(path), ())
            components, warnings = model_v040_formal.extract_components(
                rows,
                features,
                metadata["difficulty"],
                clock_rate=metadata["mod_transform_context"].get("clock_rate", 1.0),
                effective_mods=metadata["mod_context"].get("effective_mods", ()),
                source_local_signal_version=metadata["local_signal_version"],
            )
            output = model_v040_formal.analyze_components(
                checksum=model_v040_formal.sha256_file_bytes(path.read_bytes()),
                requested_mods=(),
                components=components,
                calibration=reference_calibration,
                applied_mod_context=metadata["mod_transform_context"],
            )
            axes = {
                axis: output["axes"].get(axis, {}).get("demand_star_equivalent")
                for axis in AXES
            }
            records.append(
                {
                    "map_id": md5,
                    "ppy_nm_star": float(star),
                    "stratum": _stratum(float(star), reference),
                    "axes": axes,
                    "source": "explicit_osu_cache",
                    "warnings": warnings,
                }
            )
        except Exception as exc:  # bounded corpus builder reports and continues
            skipped.append({"file": path.name, "reason": f"{type(exc).__name__}:{exc}"})

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n")
    summary = {
        "records_path": str(output_path),
        "requested_map_count": len(paths),
        "record_count": len(records),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "source_scope": "explicit_osu_cache_v040_outputs",
    }
    summary_path = output_path.with_suffix(output_path.suffix + ".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True, help="explicit directory of .osu files")
    parser.add_argument("--osu-db", type=Path, required=True)
    parser.add_argument("--reference-calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-maps", type=int)
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
