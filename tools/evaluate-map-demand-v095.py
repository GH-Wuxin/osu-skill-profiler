"""Evaluate frozen V0.92.2 and V0.95 against local approximate reviews.

The review JSONL remains private and is only read at runtime. This script emits
aggregate errors and score shifts; it never copies source records into output.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import contract as C  # noqa: E402
from map_demand_v01 import model_v092, model_v095  # noqa: E402
from map_demand_v01.bid_review_ui_v01 import BidMapIndex  # noqa: E402
from map_demand_v01.calibration import load_calibration  # noqa: E402
from map_demand_v01.osu_db_star_scale import read_nm_star_distribution  # noqa: E402


def mean(values: list[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--responses",
        default="training/datasets/map_demand_bid_review_v01/human_responses.jsonl",
    )
    parser.add_argument("--manifest", default="training/datasets/std_manifest.json")
    parser.add_argument("--songs-root", default="G:/osu! 20210821/Songs")
    parser.add_argument(
        "--calibration-dir",
        default="training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k",
    )
    parser.add_argument("--osu-db", default="G:/osu! 20210821/osu!.db")
    parser.add_argument(
        "--details",
        action="store_true",
        help="include per-review prediction errors for local regression audits",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    responses = []
    superseded: set[str] = set()
    with (root / args.responses).resolve().open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            responses.append(item)
            if item.get("supersedes_response_id"):
                superseded.add(str(item["supersedes_response_id"]))
    responses = [
        item for item in responses if str(item.get("response_id")) not in superseded
    ]

    index = BidMapIndex(
        manifest_path=(root / args.manifest).resolve(),
        songs_root=Path(args.songs_root).resolve(),
    )
    calibration = load_calibration((root / args.calibration_dir).resolve())
    stars = read_nm_star_distribution(Path(args.osu_db).resolve())[
        "relative_path_to_nm_stars"
    ]
    cache: dict[tuple[int, tuple[str, ...]], dict[str, dict[str, float]]] = {}

    def analyze(beatmap_id: int, requested_mods: list[str]) -> dict[str, dict[str, float]]:
        key = (beatmap_id, tuple(requested_mods))
        if key in cache:
            return cache[key]
        record = index.lookup(beatmap_id)
        path = Path(record["path_abs"])
        relative = str(record.get("relative_path") or record.get("reference") or "")
        anchor = stars.get(relative.replace("\\", "/").casefold())
        outputs = {}
        for name, model in (("v0922", model_v092), ("v095", model_v095)):
            rows, features, metadata = model.extract_from_path(
                str(path), requested_mods=requested_mods
            )
            applied = metadata.get("mod_transform_context", {})
            mods = metadata.get("mod_context", {})
            components, _ = model.extract_components(
                rows,
                features,
                difficulty=metadata.get("difficulty"),
                clock_rate=applied.get("clock_rate", 1.0),
                effective_mods=mods.get("effective_mods", []),
            )
            if anchor is not None and float(anchor) > 0.0:
                components["v091_nm_star_anchor"] = float(anchor)
            output = model.analyze_components(
                checksum=model.sha256_file_bytes(path.read_bytes()),
                requested_mods=requested_mods,
                components=components,
                calibration=calibration,
                applied_mod_context=applied,
            )
            outputs[name] = {
                axis: float(output["axes"][axis]["demand_star_equivalent"])
                for axis in model.AXIS_ORDER
                if output["axes"][axis].get("demand_star_equivalent") is not None
            }
        cache[key] = outputs
        return outputs

    errors: dict[str, dict[str, list[float]]] = {
        "v0922": defaultdict(list),
        "v095": defaultdict(list),
    }
    shifts: dict[str, list[float]] = defaultdict(list)
    signed_errors: dict[str, dict[str, list[float]]] = {
        "v0922": defaultdict(list),
        "v095": defaultdict(list),
    }
    used_ratings = 0
    detail_rows = []
    for response in responses:
        beatmap_id = int(response["beatmap"]["beatmap_id"])
        requested_mods = list(response.get("mod_context", {}).get("requested_mods", []))
        outputs = analyze(beatmap_id, requested_mods)
        for axis, rating in response.get("ratings", {}).items():
            if rating.get("qualifier") != "APPROXIMATE" or rating.get("value") is None:
                continue
            target = float(rating["value"])
            if not math.isfinite(target):
                continue
            used_ratings += 1
            for version in ("v0922", "v095"):
                predicted = outputs[version].get(axis)
                if predicted is None:
                    continue
                errors[version][axis].append(abs(predicted - target))
                signed_errors[version][axis].append(predicted - target)
            if axis in outputs["v0922"] and axis in outputs["v095"]:
                shifts[axis].append(outputs["v095"][axis] - outputs["v0922"][axis])
            if args.details:
                detail_rows.append(
                    {
                        "beatmap_id": beatmap_id,
                        "title": response.get("beatmap", {}).get("title"),
                        "nm_star_anchor": response.get("beatmap", {}).get(
                            "local_nm_stars"
                        ),
                        "approach_rate": response.get("beatmap", {})
                        .get("metadata", {})
                        .get("difficulty", {})
                        .get("AR"),
                        "mods": requested_mods,
                        "axis": axis,
                        "target": target,
                        "v0922": outputs["v0922"].get(axis),
                        "v095": outputs["v095"].get(axis),
                        "v095_signed_error": (
                            None
                            if outputs["v095"].get(axis) is None
                            else outputs["v095"][axis] - target
                        ),
                    }
                )

    axes = sorted(set(errors["v0922"]) | set(errors["v095"]))
    report = {
        "active_response_count": len(responses),
        "unique_analysis_count": len(cache),
        "approximate_rating_count": used_ratings,
        "axes": {
            axis: {
                "sample_count": len(errors["v095"].get(axis, [])),
                "v0922_mae": mean(errors["v0922"].get(axis, [])),
                "v095_mae": mean(errors["v095"].get(axis, [])),
                "v0922_signed_bias": mean(signed_errors["v0922"].get(axis, [])),
                "v095_signed_bias": mean(signed_errors["v095"].get(axis, [])),
                "mean_v095_minus_v0922": mean(shifts.get(axis, [])),
            }
            for axis in axes
        },
        "overall_mae": {
            version: mean(
                [value for values in errors[version].values() for value in values]
            )
            for version in ("v0922", "v095")
        },
    }
    if args.details:
        report["details"] = sorted(
            detail_rows,
            key=lambda item: abs(item["v095_signed_error"] or 0.0),
            reverse=True,
        )
    print(C.strict_json_dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
