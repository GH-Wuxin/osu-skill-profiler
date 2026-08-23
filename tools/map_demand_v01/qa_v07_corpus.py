"""Run distributional drift QA for the V0.7 mechanism overlay on frozen 20k NM."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import contract as C
from . import model as v06
from . import model_v07 as v07
from .calibration import load_calibration


def _quantile(values: list[float], q: float) -> float:
    return C.percentile_linear(sorted(values), q)


def _summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "p10": _quantile(values, 0.10),
        "median": _quantile(values, 0.50),
        "p90": _quantile(values, 0.90),
        "p99": _quantile(values, 0.99),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    calibration_dir = root / "training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k"
    samples_path = calibration_dir / "calibration_samples.jsonl"
    feature_path = root / "training/datasets/feature_qa_v02/feature_qa_20k.jsonl"
    out_dir = root / "training/datasets/map_demand_qa_v07_mechanism_overlay_20k"
    out_dir.mkdir(parents=True, exist_ok=True)
    calibration = load_calibration(calibration_dir)

    feature_by_checksum: dict[str, dict[str, Any]] = {}
    with feature_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            if record.get("ok") and isinstance(record.get("features"), dict):
                feature_by_checksum[str(record["checksum"])] = record["features"]

    by_axis: dict[str, dict[str, list[float]]] = {
        axis: {"v06": [], "v07": [], "delta": []} for axis in C.AXIS_ORDER
    }
    visibility_deficits: list[float] = []
    missing_feature_joins = 0
    map_count = 0
    with samples_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            sample = json.loads(line)
            checksum = str(sample["checksum"])
            components = dict(sample["components"])
            features = feature_by_checksum.get(checksum)
            if features is None:
                missing_feature_joins += 1
            else:
                for component, feature in v07._EXTRA_FEATURES.items():
                    components[component] = features.get(feature)
            old = v06.analyze_components(
                checksum=checksum, components=components, calibration=calibration
            )
            new = v07.analyze_components(
                checksum=checksum, components=components, calibration=calibration
            )
            for axis in C.AXIS_ORDER:
                old_star = old["axes"][axis].get("demand_star_equivalent")
                new_star = new["axes"][axis].get("demand_star_equivalent")
                if old_star is None or new_star is None:
                    continue
                old_value = float(old_star)
                new_value = float(new_star)
                by_axis[axis]["v06"].append(old_value)
                by_axis[axis]["v07"].append(new_value)
                by_axis[axis]["delta"].append(new_value - old_value)
            visibility = new["diagnostics"].get("v07_visibility")
            if visibility is not None:
                visibility_deficits.append(float(visibility["relative_ar_deficit"]))
            map_count += 1

    axes: dict[str, Any] = {}
    for axis, series in by_axis.items():
        deltas = series["delta"]
        axes[axis] = {
            "v06_stars": _summary(series["v06"]),
            "v07_stars": _summary(series["v07"]),
            "delta_stars": _summary(deltas),
            "share_abs_delta_gt_1": (
                sum(abs(value) > 1.0 for value in deltas) / len(deltas) if deltas else None
            ),
            "share_abs_delta_gt_2": (
                sum(abs(value) > 2.0 for value in deltas) / len(deltas) if deltas else None
            ),
        }
    report = {
        "schema_version": "map_demand_qa_v0.7.0",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "map_count": map_count,
        "missing_feature_joins": missing_feature_joins,
        "base_calibration_id": calibration["calibration_id"],
        "v07_calibration_id": v07.calibration_id(calibration["calibration_id"]),
        "mechanism_spec": v07.MECHANISM_SPEC,
        "relative_ar_deficit": _summary(visibility_deficits),
        "axes": axes,
    }
    (out_dir / "qa_report.json").write_text(
        C.strict_json_dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Map Demand V0.7 mechanism overlay — 20k drift QA",
        "",
        f"Maps: {map_count}; missing feature joins: {missing_feature_joins}.",
        "",
        "| Axis | V0.6 median | V0.7 median | median delta | p90 delta | |delta| > 1 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for axis in C.AXIS_ORDER:
        item = axes[axis]
        lines.append(
            f"| {axis} | {item['v06_stars']['median']:.2f} | "
            f"{item['v07_stars']['median']:.2f} | {item['delta_stars']['median']:+.2f} | "
            f"{item['delta_stars']['p90']:+.2f} | {item['share_abs_delta_gt_1']:.1%} |"
        )
    (out_dir / "qa_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
