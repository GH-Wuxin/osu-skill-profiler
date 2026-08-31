"""Read-only real-map regression for beta.2. Never contacts or changes services.

Uses local .osu files referenced by a user-supplied analysis cache. Recalculates
both versions from the same file/mod context; manual labels are NOT fit targets.
Only the explicitly requested report is written.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from map_demand_v01 import model_v010_beta2 as candidate
from map_demand_v01 import model_v010_beta1 as baseline
from map_demand_v01.calibration import load_calibration
from map_demand_v01.cli import DEFAULT_CALIBRATION_DIR

# Evaluation cases only. No beatmap ID is consumed by either algorithm.
FOCUS = {1475722, 1575142, 1483372, 1860169, 4418212, 1620144, 1592916,
         772293, 5648807, 5405912, 2116202, 2809623, 890190, 4288226,
         4437056, 4385157, 4033979, 4303461, 5119288, 2872154}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--limit", default=100, type=int, help="Recent unique maps, plus focused cases")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--songs-root", type=Path)
    parser.add_argument("--osu-db", type=Path)
    parser.add_argument("--extra-map", action="append", nargs=3, default=[], metavar=("BID", "PATH", "NM_STARS"))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    calibration = load_calibration(DEFAULT_CALIBRATION_DIR)
    unique = {}
    malformed = 0
    for path in sorted(args.cache_root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            a = json.loads(path.read_text(encoding="utf-8-sig"))["analysis"]
            b = a["beatmap"]
            mods = tuple(a["identity"]["effective_mods"])
            key = (b["beatmap_id"], mods)
            if key not in unique and Path(b["path_abs"]).is_file():
                unique[key] = {"bid": key[0], "mods": mods, "path": b["path_abs"],
                               "nm_stars": b.get("local_nm_stars"), "title": b.get("title")}
        except (KeyError, ValueError, OSError, TypeError):
            malformed += 1
    samples = list(unique.values())[:args.limit]
    seen = {(s["bid"], s["mods"]) for s in samples}
    for key, sample in unique.items():
        if key[0] in FOCUS and key not in seen:
            samples.append(sample)
            seen.add(key)
    if any((args.manifest, args.songs_root, args.osu_db)):
        if not all((args.manifest, args.songs_root, args.osu_db)):
            parser.error("--manifest, --songs-root and --osu-db must be supplied together")
        from map_demand_v01.osu_db_star_scale import read_nm_star_distribution
        stars_by_path = read_nm_star_distribution(args.osu_db)["relative_path_to_nm_stars"]
        low_counts = {1: 0, 2: 0, 3: 0}
        with args.manifest.open(encoding="utf-8") as source:
            for line in source:
                stripped = line.strip().rstrip(",")
                if not stripped.startswith("{") or '"samples"' in stripped:
                    continue
                record = json.loads(stripped)
                bid = record.get("beatmap_id")
                relative = record.get("relative_path", "")
                stars = stars_by_path.get(relative.replace("\\", "/").casefold())
                bucket = int(stars) if isinstance(stars, (int, float)) else -1
                low_case = bucket in low_counts and low_counts[bucket] < 3
                if ((bid not in FOCUS and not low_case) or (bid, ()) in seen
                        or not isinstance(bid, int) or bid <= 0):
                    continue
                path = args.songs_root / relative
                if not path.is_file():
                    continue
                samples.append({"bid": bid, "mods": (), "path": str(path),
                                "nm_stars": stars, "title": record.get("title")})
                seen.add((bid, ()))
                if low_case:
                    low_counts[bucket] += 1
    for bid, path, stars in args.extra_map:
        samples.append({"bid": int(bid), "mods": (), "path": path, "nm_stars": float(stars), "title": Path(path).stem})
    results, errors = [], []
    started = time.monotonic()
    for index, sample in enumerate(samples):
        try:
            rows, features, metadata = candidate.extract_from_path(sample["path"], requested_mods=sample["mods"])
            components, _ = candidate.extract_components(
                rows, features, metadata.get("difficulty"),
                metadata.get("mod_transform_context", {}).get("clock_rate", 1), sample["mods"])
            if sample["nm_stars"] is not None:
                components["v091_nm_star_anchor"] = sample["nm_stars"]
            kwargs = dict(checksum=candidate.sha256_file_bytes(Path(sample["path"]).read_bytes()),
                          components=components, calibration=calibration, requested_mods=sample["mods"],
                          applied_mod_context=metadata.get("mod_transform_context"))
            before, after = baseline.analyze_components(**kwargs), candidate.analyze_components(**kwargs)
            if before["status"] != "OK" or after["status"] != "OK":
                raise ValueError(f"unsupported result: {before['status']} / {after['status']}")
            unchanged = [a for a in candidate.AXIS_ORDER if a not in candidate.CHANGED_AXES]
            assert all(before["axes"][a] == after["axes"][a] for a in unchanged), "Unrelated axis changed"
            results.append({**sample, "cs": metadata.get("difficulty", {}).get("CircleSize"),
                            "before": {a: before["axes"][a]["demand_star_equivalent"] for a in candidate.AXIS_ORDER},
                            "after": {a: after["axes"][a]["demand_star_equivalent"] for a in candidate.AXIS_ORDER},
                            "measures": components["beta2_measures"], "other_six_exactly_unchanged": True})
        except Exception as exc:
            errors.append({**sample, "error": f"{type(exc).__name__}: {exc}"})
        if (index + 1) % 20 == 0:
            print(f"Checked {index + 1}/{len(samples)}; errors={len(errors)}", flush=True)
    aggregates = {}
    for axis in candidate.CHANGED_AXES:
        aggregates[axis] = {}
        for version in ("before", "after"):
            values = [r[version][axis] for r in results]
            aggregates[axis][version] = {
                "mean": statistics.fmean(values) if values else None,
                "median": statistics.median(values) if values else None,
                "at_least_8": sum(v >= 8 for v in values)}
    report = {"baseline": baseline.MAP_DEMAND_VERSION, "candidate": candidate.MAP_DEMAND_VERSION,
              "scope": "Local convenience sample, not population statistics or label fitting",
              "unique_local_cache_entries": len(unique), "unreadable_cache_entries": malformed,
              "duration_s": time.monotonic() - started, "count": len(results),
              "aggregates": aggregates, "results": results, "errors": errors}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"count": len(results), "errors": len(errors), "aggregates": aggregates}, ensure_ascii=True, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
