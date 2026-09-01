"""Verify the public wrapper against beta.3 and the saved V03 replay."""
import argparse
import json
from pathlib import Path

from map_demand_v01 import model_v010_beta4 as candidate
from map_demand_v01 import model_v010_beta3 as baseline
from map_demand_v01.calibration import load_calibration
from map_demand_v01.cli import DEFAULT_CALIBRATION_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    replay = json.loads(args.replay.read_text(encoding="utf-8"))
    calibration = load_calibration(DEFAULT_CALIBRATION_DIR)
    results = []
    for i, item in enumerate(replay["results"]):
        rows, features, meta = candidate.extract_from_path(item["path"], requested_mods=item["mods"])
        components, _ = candidate.extract_components(rows, features, meta["difficulty"],
            meta["mod_transform_context"]["clock_rate"], item["mods"])
        if item.get("nm_stars") is not None:
            components["v091_nm_star_anchor"] = item["nm_stars"]
        kwargs = dict(checksum=candidate.sha256_file_bytes(Path(item["path"]).read_bytes()),
                      components=components, calibration=calibration, requested_mods=item["mods"],
                      applied_mod_context=meta["mod_transform_context"])
        before, after = baseline.analyze_components(**kwargs), candidate.analyze_components(**kwargs)
        assert before["status"] == after["status"] == "OK", (item["bid"], item["mods"])
        for axis in candidate.AXIS_ORDER:
            if axis != "aim_control":
                assert before["axes"][axis] == after["axes"][axis], (item["bid"], item["mods"], axis)
        value = after["axes"]["aim_control"]["demand_star_equivalent"]
        assert value == item["after"]["aim_control"], (item["bid"], item["mods"], "V03 mismatch")
        results.append(dict(bid=item["bid"], mods=item["mods"], control=value,
                            other_eight_equal_beta3=True, control_equal_v03=True))
        if (i + 1) % 20 == 0:
            print(f"Verified {i+1}/{len(replay['results'])}", flush=True)
    report = dict(version=candidate.MAP_DEMAND_VERSION, count=len(results), results=results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(version=report["version"], count=report["count"], result="PASS")))


if __name__ == "__main__":
    main()
