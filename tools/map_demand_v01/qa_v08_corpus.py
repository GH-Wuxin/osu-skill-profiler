"""20k drift QA for the V0.8 Stamina/Endurance taxonomy split."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import contract as C
from . import model_v07 as v07
from . import model_v08 as v08
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
    out_dir = root / "training/datasets/map_demand_qa_v08_stamina_endurance_20k"
    out_dir.mkdir(parents=True, exist_ok=True)
    calibration = load_calibration(calibration_dir)
    feature_by_checksum: dict[str, dict[str, Any]] = {}
    with feature_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            if record.get("ok") and isinstance(record.get("features"), dict):
                feature_by_checksum[str(record["checksum"])] = record["features"]

    v07_stamina: list[float] = []
    v08_stamina: list[float] = []
    endurance: list[float] = []
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
            old = v07.analyze_components(
                checksum=checksum, components=components, calibration=calibration
            )
            new = v08.analyze_components(
                checksum=checksum, components=components, calibration=calibration
            )
            old_value = old["axes"]["stamina"].get("demand_star_equivalent")
            new_value = new["axes"]["stamina"].get("demand_star_equivalent")
            endurance_value = new["axes"]["endurance"].get("demand_star_equivalent")
            if old_value is not None and new_value is not None:
                v07_stamina.append(float(old_value))
                v08_stamina.append(float(new_value))
            if endurance_value is not None:
                endurance.append(float(endurance_value))
            map_count += 1

    stamina_delta = [new - old for old, new in zip(v07_stamina, v08_stamina)]
    report = {
        "schema_version": "map_demand_qa_v0.8.0",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "map_count": map_count,
        "missing_feature_joins": missing_feature_joins,
        "base_calibration_id": calibration["calibration_id"],
        "v08_calibration_id": v08.calibration_id(calibration["calibration_id"]),
        "mechanism_spec": v08.MECHANISM_SPEC,
        "v07_stamina": _summary(v07_stamina),
        "v08_stamina": _summary(v08_stamina),
        "stamina_delta": _summary(stamina_delta),
        "endurance": _summary(endurance),
        "stamina_above_10_before": sum(value > 10.0 for value in v07_stamina),
        "stamina_above_10_after": sum(value > 10.0 for value in v08_stamina),
    }
    (out_dir / "qa_report.json").write_text(
        C.strict_json_dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Map Demand V0.8 Stamina / Endurance QA",
        "",
        f"Maps: {map_count}; missing feature joins: {missing_feature_joins}.",
        "",
        f"V0.7 Stamina median/p99/max: {report['v07_stamina']['median']:.2f} / {report['v07_stamina']['p99']:.2f} / {report['v07_stamina']['max']:.2f}",
        f"V0.8 Stamina median/p99/max: {report['v08_stamina']['median']:.2f} / {report['v08_stamina']['p99']:.2f} / {report['v08_stamina']['max']:.2f}",
        f"Stamina >10 before/after: {report['stamina_above_10_before']} / {report['stamina_above_10_after']}",
        f"Endurance p10/median/p90/p99/max: {report['endurance']['p10']:.2f} / {report['endurance']['median']:.2f} / {report['endurance']['p90']:.2f} / {report['endurance']['p99']:.2f} / {report['endurance']['max']:.2f}",
    ]
    (out_dir / "qa_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
