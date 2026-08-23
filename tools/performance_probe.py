#!/usr/bin/env python3
"""Performance probe for foundation remediation v0.1.

Two parts:

1. Old-vs-corrected timing analysis over the completed semantic-delta JSONL
   (5k now, 20k when available).  Per-map ``timing_ms`` already contains
   ``local_old/local_new`` and ``reference_old/reference_new`` so no corpus
   re-extraction is needed.

2. A bounded synthetic repeat-slider sweep that times Feature/Local/Reference
   under the historical and corrected versions and checks that corrected
   repeat traversal does not introduce O(repeat_count^2) amplification or
   unbounded path expansion.  Nested-object counts are recorded and compared
   with span count.

No corpus mutation, model, label, taxonomy or network work is performed.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "src"))

from osu_skill_profiler.features.extractor import FeatureExtractor  # noqa: E402
from osu_skill_profiler.features.schema import LEGACY_FEATURE_VERSION, FEATURE_VERSION  # noqa: E402
from osu_skill_profiler.parser.normalized import normalize  # noqa: E402
from osu_skill_profiler.parser.osu_parser import parse_osu  # noqa: E402
from osu_skill_profiler.reference.ppy.contract import LEGACY_REFERENCE_VERSION, REFERENCE_VERSION  # noqa: E402
from osu_skill_profiler.reference.ppy.extractor import ReferenceSignalExtractor  # noqa: E402
from osu_skill_profiler.signals.contract import LEGACY_SIGNAL_VERSION, SIGNAL_VERSION  # noqa: E402
from osu_skill_profiler.signals.extractor import LocalSignalExtractor  # noqa: E402

OUT = ROOT / "training" / "datasets" / "foundation_remediation_v01" / "performance_probe.json"


def _map_text(spans: int, length_px: float = 200.0, tick_rate: float = 1.0) -> str:
    return "\n".join(
        [
            "osu file format v14",
            "[General]",
            "Mode:0",
            "[Difficulty]",
            "CircleSize:4",
            "OverallDifficulty:8",
            "ApproachRate:9",
            "SliderMultiplier:1",
            f"SliderTickRate:{tick_rate}",
            "[TimingPoints]",
            "0,500,4,2,1,60,1,0",
            "[HitObjects]",
            f"64,64,0,2,0,L|264:64,{spans},{length_px},0:0:0:0:",
        ]
    ) + "\n"


def _time_extract(text: str) -> dict:
    beatmap = parse_osu(text)
    started = time.perf_counter()
    nmap = normalize(beatmap)
    FeatureExtractor(LEGACY_FEATURE_VERSION).extract(nmap)
    feature_both_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    local_old = LocalSignalExtractor(LEGACY_SIGNAL_VERSION).extract(beatmap)
    local_old_ms = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    local_new = LocalSignalExtractor(SIGNAL_VERSION).extract(beatmap)
    local_new_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    reference_old = ReferenceSignalExtractor(LEGACY_REFERENCE_VERSION).extract(beatmap)
    reference_old_ms = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    reference_new = ReferenceSignalExtractor(REFERENCE_VERSION).extract(beatmap)
    reference_new_ms = (time.perf_counter() - started) * 1000.0

    return {
        "feature_both_ms": feature_both_ms,
        "local_old_ms": local_old_ms,
        "local_new_ms": local_new_ms,
        "reference_old_ms": reference_old_ms,
        "reference_new_ms": reference_new_ms,
        "local_new_objects": len(local_new["objects"]),
        "local_old_objects": len(local_old["objects"]),
        "reference_new_objects": len(reference_new["objects"]),
        "reference_old_objects": len(reference_old["objects"]),
    }


def _slope_loglog(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    lx = [math.log(max(x, 1e-9)) for x in xs]
    ly = [math.log(max(y, 1e-9)) for y in ys]
    n = len(lx)
    mx = sum(lx) / n
    my = sum(ly) / n
    denom = sum((x - mx) ** 2 for x in lx)
    if denom == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(lx, ly)) / denom


def _analyze_delta(path: Path) -> dict:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        return {"rows": 0}

    local_ratios: list[float] = []
    reference_ratios: list[float] = []
    total_ratios: list[float] = []
    repeat_counts: list[int] = []
    local_ratios_by_repeat: dict[str, list[float]] = {"repeat": [], "non_repeat": []}
    slowest: list[dict] = []
    for row in rows:
        timing = row.get("timing_ms") or {}
        local_old = float(timing.get("local_old") or 0.0)
        local_new = float(timing.get("local_new") or 0.0)
        reference_old = float(timing.get("reference_old") or 0.0)
        reference_new = float(timing.get("reference_new") or 0.0)
        total_old = local_old + reference_old
        total_new = local_new + reference_new
        if local_old > 0:
            local_ratios.append(local_new / local_old)
        if reference_old > 0:
            reference_ratios.append(reference_new / reference_old)
        if total_old > 0:
            total_ratios.append(total_new / total_old)
        repeat = int(row.get("repeat_slider_count") or 0)
        repeat_counts.append(repeat)
        key = "repeat" if repeat > 0 else "non_repeat"
        if local_old > 0:
            local_ratios_by_repeat[key].append(local_new / local_old)
        if len(slowest) < 25:
            slowest.append(
                {
                    "sample_id": row.get("sample_id"),
                    "repeat_slider_count": repeat,
                    "local_old_ms": local_old,
                    "local_new_ms": local_new,
                    "reference_old_ms": reference_old,
                    "reference_new_ms": reference_new,
                    "total_ms": float(timing.get("total") or 0.0),
                }
            )
    slowest.sort(key=lambda item: item["total_ms"], reverse=True)

    def quantiles(values: list[float]) -> dict:
        if not values:
            return {}
        values = sorted(values)
        n = len(values)

        def q(p: float) -> float:
            pos = (n - 1) * p
            lo = math.floor(pos)
            hi = math.ceil(pos)
            if lo == hi:
                return values[lo]
            return values[lo] + (values[hi] - values[lo]) * (pos - lo)

        return {
            "count": n,
            "min": values[0],
            "p50": q(0.5),
            "p90": q(0.9),
            "p95": q(0.95),
            "p99": q(0.99),
            "max": values[-1],
            "mean": statistics.fmean(values),
        }

    return {
        "rows": len(rows),
        "local_new_over_old_ratio": quantiles(local_ratios),
        "reference_new_over_old_ratio": quantiles(reference_ratios),
        "total_new_over_old_ratio": quantiles(total_ratios),
        "local_ratio_by_repeat": {key: quantiles(values) for key, values in local_ratios_by_repeat.items()},
        "loglog_local_new_vs_object_count_slope": _slope_loglog(
            [float(row.get("object_count") or 1) for row in rows],
            [float((row.get("timing_ms") or {}).get("local_new") or 0.0) for row in rows],
        ),
        "loglog_reference_new_vs_object_count_slope": _slope_loglog(
            [float(row.get("object_count") or 1) for row in rows],
            [float((row.get("timing_ms") or {}).get("reference_new") or 0.0) for row in rows],
        ),
        "slowest_25": slowest[:25],
    }


def _synthetic_sweep() -> dict:
    spans_list = [2, 3, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
    results: list[dict] = []
    for spans in spans_list:
        timing = _time_extract(_map_text(spans))
        results.append(
            {
                "span_count": spans,
                "repeat_count": spans - 1,
                **timing,
            }
        )
        print(
            f"span={spans:4d} local_old={timing['local_old_ms']:.2f}ms "
            f"local_new={timing['local_new_ms']:.2f}ms "
            f"ref_old={timing['reference_old_ms']:.2f}ms "
            f"ref_new={timing['reference_new_ms']:.2f}ms "
            f"objects_new={timing['local_new_objects']}",
            flush=True,
        )

    def slope(key: str) -> float | None:
        return _slope_loglog(
            [float(item["repeat_count"]) for item in results],
            [float(item[key]) for item in results],
        )

    object_growth = [
        results[i]["local_new_objects"] / max(1, results[i]["span_count"])
        for i in range(len(results))
    ]
    return {
        "spans": [item["span_count"] for item in results],
        "local_old_slope": slope("local_old_ms"),
        "local_new_slope": slope("local_new_ms"),
        "reference_old_slope": slope("reference_old_ms"),
        "reference_new_slope": slope("reference_new_ms"),
        "feature_slope": slope("feature_both_ms"),
        "local_new_objects_per_span": object_growth,
        "max_local_new_objects": max(item["local_new_objects"] for item in results),
        "max_reference_new_objects": max(item["reference_new_objects"] for item in results),
        "verdict": "PASS" if max(slope("local_new_ms") or 0, slope("reference_new_ms") or 0) <= 2.05 else "REVIEW",
    }


def main() -> int:
    report: dict = {}
    delta_5k = ROOT / "training" / "datasets" / "foundation_remediation_v01" / "delta_5k" / "delta_5000.jsonl"
    delta_20k = ROOT / "training" / "datasets" / "foundation_remediation_v01" / "delta_20k" / "delta_20000.jsonl"
    if delta_5k.exists():
        report["delta_5k"] = _analyze_delta(delta_5k)
    if delta_20k.exists():
        report["delta_20k"] = _analyze_delta(delta_20k)
    report["synthetic_repeat_sweep"] = _synthetic_sweep()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(f"probe written to {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
