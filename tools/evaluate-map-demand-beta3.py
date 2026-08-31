"""Replay a local beta.2 evaluation sample; no network or running service writes."""
import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from map_demand_v01 import model_v010_beta3 as candidate
from map_demand_v01 import model_v010_beta2 as baseline
from map_demand_v01.calibration import load_calibration
from map_demand_v01.cli import DEFAULT_CALIBRATION_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    calibration = load_calibration(DEFAULT_CALIBRATION_DIR)
    samples = json.loads(args.sample.read_text(encoding="utf-8-sig"))["results"]
    results, errors = [], []
    for i, sample in enumerate(samples):
        try:
            mods = sample["mods"]
            rows, features, meta = candidate.extract_from_path(sample["path"], requested_mods=mods)
            comp, _ = candidate.extract_components(rows, features, meta["difficulty"],
                meta["mod_transform_context"]["clock_rate"], mods)
            if sample.get("nm_stars") is not None:
                comp["v091_nm_star_anchor"] = sample["nm_stars"]
            kw = dict(checksum=candidate.sha256_file_bytes(Path(sample["path"]).read_bytes()),
                      components=comp, calibration=calibration, requested_mods=mods,
                      applied_mod_context=meta["mod_transform_context"])
            old, new = baseline.analyze_components(**kw), candidate.analyze_components(**kw)
            assert old["status"] == new["status"] == "OK"
            assert all(old["axes"][a] == new["axes"][a] for a in candidate.AXIS_ORDER if a != "spatial_precision")
            results.append({**{k: sample[k] for k in ("bid", "mods", "title", "path", "nm_stars")},
                            "cs": meta["difficulty"]["CircleSize"],
                            "before": {a: old["axes"][a]["demand_star_equivalent"] for a in candidate.AXIS_ORDER},
                            "after": {a: new["axes"][a]["demand_star_equivalent"] for a in candidate.AXIS_ORDER},
                            "measure": comp["beta3_precision"], "other_eight_exactly_unchanged": True})
        except Exception as exc:
            errors.append({"bid": sample["bid"], "mods": sample["mods"], "error": str(exc)})
        if (i + 1) % 20 == 0:
            print(f"Checked {i + 1}/{len(samples)}; errors={len(errors)}", flush=True)
    aggregates = {version: {"mean": statistics.fmean(r[version]["spatial_precision"] for r in results),
                            "median": statistics.median(r[version]["spatial_precision"] for r in results)}
                  for version in ("before", "after")} if results else {}
    report = {"baseline": baseline.MAP_DEMAND_VERSION, "candidate": candidate.MAP_DEMAND_VERSION,
              "scope": "Local convenience sample, not population statistics or label fitting",
              "count": len(results), "aggregates": aggregates, "results": results, "errors": errors}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"count": len(results), "errors": errors, "aggregates": aggregates}))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
