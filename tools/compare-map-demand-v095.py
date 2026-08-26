"""Compare frozen V0.92.2 with V0.95 on local BID samples."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import contract as C  # noqa: E402
from map_demand_v01 import model_v092, model_v095  # noqa: E402
from map_demand_v01.bid_review_ui_v01 import BidMapIndex  # noqa: E402
from map_demand_v01.calibration import load_calibration  # noqa: E402
from map_demand_v01.osu_db_star_scale import read_nm_star_distribution  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bids", nargs="+", type=int)
    parser.add_argument("--mods", nargs="*", default=[])
    parser.add_argument("--manifest", default="training/datasets/std_manifest.json")
    parser.add_argument("--songs-root", default="G:/osu! 20210821/Songs")
    parser.add_argument(
        "--calibration-dir",
        default="training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k",
    )
    parser.add_argument("--osu-db", default="G:/osu! 20210821/osu!.db")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    index = BidMapIndex(
        manifest_path=(root / args.manifest).resolve(),
        songs_root=Path(args.songs_root).resolve(),
    )
    calibration = load_calibration((root / args.calibration_dir).resolve())
    stars = read_nm_star_distribution(Path(args.osu_db).resolve())[
        "relative_path_to_nm_stars"
    ]
    results = []
    for beatmap_id in args.bids:
        record = index.lookup(beatmap_id)
        path = Path(record["path_abs"])
        relative = str(record.get("relative_path") or record.get("reference") or "")
        anchor = stars.get(relative.replace("\\", "/").casefold())
        versions = {}
        component_snapshot = {}
        for name, model in (("v0922", model_v092), ("v095", model_v095)):
            rows, features, metadata = model.extract_from_path(
                str(path), requested_mods=args.mods
            )
            applied = metadata.get("mod_transform_context", {})
            mods = metadata.get("mod_context", {})
            components, warnings = model.extract_components(
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
                requested_mods=args.mods,
                components=components,
                calibration=calibration,
                applied_mod_context=applied,
            )
            versions[name] = {
                axis: output["axes"][axis].get("demand_star_equivalent")
                for axis in model.AXIS_ORDER
            }
            if name == "v095":
                component_snapshot = {
                    key: value
                    for key, value in components.items()
                    if key.startswith("v095_")
                    or key
                    in {
                        "reading_preempt_median_ms",
                        "reading_density",
                        "reading_visual_change",
                        "reading_hidden_pressure",
                        "v091_visible_overlap_load_p90",
                        "v091_visible_cluster_load_p90",
                        "v091_visible_overlap_pair_share",
                        "v091_visible_stack_object_share",
                        "v091_finger_nontrivial_change_share",
                        "v091_finger_novelty_p90",
                        "finger_control_interval_diversity",
                        "finger_control_interval_entropy",
                        "finger_control_interval_ratio",
                        "v091_precision_micro_correction_count",
                        "v091_precision_micro_correction_p90",
                        "v092_jump_tail_activation",
                    }
                }
                component_snapshot["warnings"] = warnings
        results.append(
            {
                "beatmap_id": beatmap_id,
                "title": record.get("title"),
                "version": record.get("version"),
                "mods": args.mods,
                "nm_star_anchor": anchor,
                "axes": versions,
                "v095_components": component_snapshot,
            }
        )
    print(C.strict_json_dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
