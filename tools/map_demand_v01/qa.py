"""Canonical QA for MAP_DEMAND_ATOMIC_V04.

Consumes the calibration artifacts built from the existing 5k QA selection.
Produces a new independent QA directory:
    training/datasets/map_demand_qa_v01/
        qa_report.json
        qa_report.md
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from . import contract as C
from .calibration import load_calibration, load_samples
from .model import analyze_components, extract_components

OUT_DIRNAME = "map_demand_qa_v01"


def _rank_average(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    ranks = [0.0] * len(values)
    i = 0
    n = len(order)
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0.0 or vy == 0.0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


def _spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    return _pearson(_rank_average(xs), _rank_average(ys))


def _correlation_matrix(scores_by_axis: dict[str, list[tuple[str, float]]]) -> dict[str, Any]:
    axes = C.AXIS_ORDER
    spearman: dict[str, dict[str, float]] = {a: {} for a in axes}
    pearson: dict[str, dict[str, float]] = {a: {} for a in axes}
    common: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for i, a in enumerate(axes):
        sa = dict(scores_by_axis.get(a, []))
        for b in axes[i:]:
            sb = dict(scores_by_axis.get(b, []))
            keys = sorted(set(sa) & set(sb))
            pairs = [(sa[k], sb[k]) for k in keys]
            common[(a, b)] = pairs
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            spearman[a][b] = spearman[b][a] = _spearman(xs, ys)
            pearson[a][b] = pearson[b][a] = _pearson(xs, ys)

    strongest: dict[str, Any] = {"pair": None, "spearman": None}
    above_08: list[dict[str, Any]] = []
    above_09: list[dict[str, Any]] = []
    rank_identical: list[dict[str, Any]] = []
    for i, a in enumerate(axes):
        for b in axes[i + 1:]:
            rho = spearman[a][b]
            if math.isfinite(rho):
                if strongest["spearman"] is None or abs(rho) > abs(float(strongest["spearman"])):
                    strongest = {"pair": f"{a}/{b}", "spearman": rho, "n": len(common[(a, b)])}
                if abs(rho) > 0.8:
                    above_08.append({"pair": f"{a}/{b}", "spearman": rho})
                if abs(rho) > 0.9:
                    above_09.append({"pair": f"{a}/{b}", "spearman": rho})
                if abs(abs(rho) - 1.0) < 1e-9:
                    rank_identical.append({"pair": f"{a}/{b}", "spearman": rho})
    return {
        "axes": axes,
        "spearman": spearman,
        "pearson": pearson,
        "pairwise_n": {f"{a}/{b}": len(common[(a, b)]) for i, a in enumerate(axes) for b in axes[i + 1:]},
        "strongest_pair": strongest,
        "pairs_abs_rho_gt_0_8": above_08,
        "pairs_abs_rho_gt_0_9": above_09,
        "rank_identical_pairs": rank_identical,
    }


def _synthetic_cases(calibration: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    def run(name: str, rows: list[dict[str, Any]], features: dict[str, Any] | None, mods: list[str] | None = None) -> dict[str, Any]:
        components, warnings = extract_components(rows, features)
        output = analyze_components(
            checksum=f"sha256:synthetic-{name}",
            requested_mods=mods or [],
            components=components,
            calibration=calibration,
        )
        output["diagnostics"]["synthetic_case"] = name
        output["diagnostics"]["component_warnings"] = warnings
        return {
            "case": name,
            "status": output["status"],
            "axis_status": {a: output["axes"][a]["status"] for a in C.AXIS_ORDER},
            "warnings": output["warnings"],
        }

    cases.append(run("empty_map", [], {}))

    from osu_skill_profiler.parser.osu_parser import parse_osu
    from osu_skill_profiler.signals.extractor import LocalSignalExtractor

    single_map = parse_osu(
        "osu file format v14\n"
        "[Difficulty]\nCircleSize:4\nApproachRate:9\nOverallDifficulty:8\n"
        "[HitObjects]\n64,64,1000,1,0\n"
    )
    single_rows = LocalSignalExtractor().extract(single_map)["objects"]
    cases.append(run("single_object_real_parse", single_rows, {}))

    sim_rows = [
        {
            "ls.adjusted_delta_time_ms": 0.0,
            "ls.hit_window_great_ms": 80.0,
            "ls.double_tap_feasibility": 0.0,
            "ls.minimum_jump_distance_cs_normalised": 100.0,
            "ls.minimum_jump_time_ms": 25.0,
            "ls.lazy_jump_distance_cs_normalised": 100.0,
            "ls.slider_aware_angle_rad": math.pi / 2,
            "ls.preempt_ms": 600.0,
        },
        {
            "ls.adjusted_delta_time_ms": 0.0,
            "ls.hit_window_great_ms": 80.0,
            "ls.double_tap_feasibility": 1.0,
            "ls.minimum_jump_distance_cs_normalised": 100.0,
            "ls.minimum_jump_time_ms": 25.0,
            "ls.lazy_jump_distance_cs_normalised": 100.0,
            "ls.slider_aware_angle_rad": math.pi,
            "ls.preempt_ms": 600.0,
        },
    ]
    cases.append(run("near_simultaneous", sim_rows, {}))

    blocked_rows = [
        {
            "ls.adjusted_delta_time_ms": None,
            "ls.hit_window_great_ms": None,
            "ls.double_tap_feasibility": None,
            "ls.minimum_jump_distance_cs_normalised": None,
            "ls.minimum_jump_time_ms": None,
            "ls.lazy_jump_distance_cs_normalised": None,
            "ls.slider_aware_angle_rad": None,
            "ls.preempt_ms": None,
            "ls.provenance": "geometry_blocked",
        }
    ]
    cases.append(run("geometry_blocked_rows", blocked_rows, {}))

    pathological_features = {
        "temporal.longest_dense_section_ms": 1.0e10,
        "temporal.map_duration_ms": 1.0e298,
        "section.duration_weighted_density_per_s": 999999999.9999999,
        "temporal.rhythm_entropy_bits": 2.5,
        "temporal.interval_diversity": 0.05,
        "temporal.interval_ratio_mean": 2.0,
        "section.density_per_s_p95": 999999999.9999999,
        "spatial.direction_change_ratio_ge_90": 0.8,
    }
    cases.append(run("pathological_finite_features", sim_rows, pathological_features))
    cases.append(run("unsupported_mods", sim_rows, pathological_features, mods=["DT"]))
    return cases


def _direct_recompute_consistency(
    calibration: dict[str, Any],
    samples: list[dict[str, Any]],
    feature_qa_path: Path,
    limit: int,
) -> dict[str, Any]:
    feature_map: dict[str, dict[str, Any]] = {}
    with feature_qa_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("checksum"):
                feature_map[rec["checksum"]] = rec

    from .model import extract_from_path, high_ar_pressure_ms

    comparisons: list[dict[str, Any]] = []
    checked = 0
    missing_path = 0
    ordered = sorted(
        samples,
        key=lambda s: s["components"].get("reading_high_ar_pressure") is not None,
        reverse=True,
    )
    for sample in ordered:
        if checked >= limit:
            break
        checksum = sample["checksum"]
        rec = feature_map.get(checksum)
        path = rec.get("path_abs") if rec else None
        if not path or not Path(path).exists():
            missing_path += 1
            continue
        try:
            rows, features, meta = extract_from_path(path)
            recomputed, _warnings = extract_components(
                rows, features, difficulty=meta.get("difficulty")
            )
            preempt = recomputed.get("reading_preempt_median_ms")
            recomputed["reading_high_ar_pressure"] = (
                None if preempt is None else high_ar_pressure_ms(preempt)
            )
        except Exception as exc:  # noqa: BLE001 - QA must record and continue
            comparisons.append({"checksum": checksum, "error": f"{type(exc).__name__}: {exc}"})
            checked += 1
            continue
        deltas: dict[str, Any] = {}
        for name in C.component_labels():
            expected = sample["components"].get(name)
            got = recomputed.get(name)
            if expected is None and got is None:
                continue
            if expected is None or got is None:
                deltas[name] = {"cached": expected, "recomputed": got}
                continue
            deltas[name] = {
                "cached": expected,
                "recomputed": got,
                "abs_delta": got - expected,
            }
        comparisons.append({"checksum": checksum, "deltas": deltas})
        checked += 1

    max_abs = 0.0
    max_pair = None
    for comp in comparisons:
        for name, delta in comp.get("deltas", {}).items():
            if isinstance(delta, dict) and isinstance(delta.get("abs_delta"), (int, float)):
                value = abs(float(delta["abs_delta"]))
                if value > max_abs:
                    max_abs = value
                    max_pair = (comp["checksum"], name)
    return {
        "requested": limit,
        "recomputed": checked,
        "missing_source_path": missing_path,
        "max_abs_delta": max_abs,
        "max_delta_pair": list(max_pair) if max_pair else None,
        "comparisons": comparisons,
    }


def _sanitize_nonfinite(obj: Any) -> Any:
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _sanitize_nonfinite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nonfinite(v) for v in obj]
    return obj


def run_qa(
    *,
    calibration_dir: Path,
    feature_qa_path: Path,
    out_dir: Path,
    recompute_limit: int = 20,
) -> dict[str, Any]:
    calibration = load_calibration(calibration_dir)
    samples = load_samples(calibration_dir / "calibration_samples.jsonl")

    ar_provenance_counts: dict[str, int] = {}
    for sample in samples:
        prov = sample.get("reading_ar_provenance")
        key = "missing" if prov is None else str(prov)
        ar_provenance_counts[key] = ar_provenance_counts.get(key, 0) + 1

    scores_by_axis: dict[str, list[tuple[str, float]]] = {a: [] for a in C.AXIS_ORDER}
    emitted: dict[str, int] = {a: 0 for a in C.AXIS_ORDER}
    abstained: dict[str, int] = {a: 0 for a in C.AXIS_ORDER}
    nonfinite_axis = 0

    per_map: list[dict[str, Any]] = []
    for sample in samples:
        axes, _warnings, abstentions = model_score(calibration, sample)
        row: dict[str, Any] = {"checksum": sample["checksum"], "axes": {}}
        for axis in C.AXIS_ORDER:
            axis_obj = axes[axis]
            if axis_obj["status"] == "EMITTED":
                score = float(axis_obj["score"])
                if not math.isfinite(score):
                    nonfinite_axis += 1
                    continue
                scores_by_axis[axis].append((sample["checksum"], score))
                emitted[axis] += 1
                row["axes"][axis] = {"score": score, "status": "EMITTED"}
            else:
                abstained[axis] += 1
                row["axes"][axis] = {"score": None, "status": axis_obj["status"]}
        per_map.append(row)

    matrix = _correlation_matrix(scores_by_axis)

    per_axis_stats: dict[str, Any] = {}
    extremes: dict[str, Any] = {}
    for axis in C.AXIS_ORDER:
        ordered = sorted(scores_by_axis[axis], key=lambda kv: (kv[1], kv[0]))
        if ordered:
            values = [v for _, v in ordered]
            per_axis_stats[axis] = {
                "n": len(values),
                "min": values[0],
                "p50": C.percentile_linear(sorted(values), 0.50),
                "max": values[-1],
                "mean": sum(values) / len(values),
            }
            extremes[axis] = {
                "top20": [{"checksum": c, "score": s} for c, s in ordered[-20:][::-1]],
                "bottom20": [{"checksum": c, "score": s} for c, s in ordered[:20]],
            }
        else:
            per_axis_stats[axis] = {"n": 0}

    def quantile(values: list[float], q: float) -> float:
        return C.percentile_linear(sorted(values), q)

    def score_map(axis: str) -> dict[str, float]:
        return dict(scores_by_axis[axis])

    separation: dict[str, Any] = {}
    checks = [
        ("raw_speed", "stamina"),
        ("jump_aim", "flow_aim"),
        ("aim_control", "spatial_precision"),
        ("finger_control", "raw_speed"),
        ("reading", "raw_speed"),
    ]
    for high_axis, ordinary_axis in checks:
        high_map = score_map(high_axis)
        ordinary_map = score_map(ordinary_axis)
        common = sorted(set(high_map) & set(ordinary_map))
        if not common:
            separation[f"{high_axis}_high_{ordinary_axis}_ordinary"] = {"count": 0}
            continue
        high_threshold = quantile([high_map[k] for k in common], 0.80)
        ordinary_low = quantile([ordinary_map[k] for k in common], 0.40)
        ordinary_high = quantile([ordinary_map[k] for k in common], 0.60)
        cases = [
            {
                "checksum": k,
                f"{high_axis}_score": high_map[k],
                f"{ordinary_axis}_score": ordinary_map[k],
            }
            for k in common
            if high_map[k] >= high_threshold and ordinary_low <= ordinary_map[k] <= ordinary_high
        ]
        cases = sorted(cases, key=lambda r: r[f"{ordinary_axis}_score"])[:20]
        separation[f"{high_axis}_high_{ordinary_axis}_ordinary"] = {
            "count": sum(
                1
                for k in common
                if high_map[k] >= high_threshold and ordinary_low <= ordinary_map[k] <= ordinary_high
            ),
            "examples": cases,
        }

    synthetic = _synthetic_cases(calibration)

    ref_gate_result: dict[str, Any] = {"leak_blocked": True, "error": None}
    try:
        bad = {"ref.ppy.reading": 1.0, "jump_aim_strain_p90": 1.0}
        C.assert_no_reference_signals(bad, "qa_ref_gate_test")
        ref_gate_result["leak_blocked"] = False
    except C.ReferenceSignalLeakageError as exc:
        ref_gate_result["error"] = str(exc)

    direct = _direct_recompute_consistency(calibration, samples, feature_qa_path, recompute_limit)

    report: dict[str, Any] = {
        "schema_version": "map_demand_qa_v1",
        "calibration_id": calibration["calibration_id"],
        "source_scope": calibration["source_scope"],
        "map_count": len(samples),
        "reading_ar_provenance_counts": ar_provenance_counts,
        "emitted": emitted,
        "abstained": abstained,
        "nonfinite_axis_scores": nonfinite_axis,
        "per_axis_stats": per_axis_stats,
        "correlation_matrix": matrix,
        "extremes": extremes,
        "separation_cases": separation,
        "synthetic_pathological_cases": synthetic,
        "reference_gate": ref_gate_result,
        "direct_recompute_consistency": direct,
    }
    report = _sanitize_nonfinite(report)
    C.scan_finite(report, "qa_report")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "qa_report.json").write_text(C.strict_json_dumps(report, indent=2), encoding="utf-8")
    markdown = _render_markdown(report)
    (out_dir / "qa_report.md").write_text(markdown, encoding="utf-8")
    return report


def model_score(calibration: dict[str, Any], sample: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    from .model import score_components

    return score_components(sample["components"], calibration)


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# MAP_DEMAND_ATOMIC_V04 — unbounded star-scaled QA report\n")
    lines.append(f"- calibration_id: `{report['calibration_id']}`")
    lines.append(f"- source_scope: `{report['source_scope']}`")
    lines.append(f"- maps: {report['map_count']}\n")
    lines.append("## Emission / abstention\n")
    lines.append("| axis | emitted | abstained |")
    lines.append("|---|---:|---:|")
    for axis in C.AXIS_ORDER:
        lines.append(f"| {axis} | {report['emitted'][axis]} | {report['abstained'][axis]} |")
    lines.append("\n## Spearman correlation (8x8)\n")
    matrix = report["correlation_matrix"]
    lines.append("| axis | " + " | ".join(matrix["axes"]) + " |")
    lines.append("|---|" + "|".join("---:" for _ in matrix["axes"]) + "|")
    for a in matrix["axes"]:
        cells = []
        for b in matrix["axes"]:
            rho = matrix["spearman"][a][b]
            cells.append("nan" if not math.isfinite(rho) else f"{rho:.3f}")
        lines.append(f"| {a} | " + " | ".join(cells) + " |")
    strongest = matrix["strongest_pair"]
    lines.append(f"\nStrongest pair: `{strongest['pair']}` rho={strongest['spearman']:.3f} n={strongest['n']}")
    lines.append(f"|rho|>0.8: {matrix['pairs_abs_rho_gt_0_8']}")
    lines.append(f"|rho|>0.9: {matrix['pairs_abs_rho_gt_0_9']}")
    lines.append(f"Rank-identical: {matrix['rank_identical_pairs']}")
    lines.append("\n## Reference gate\n")
    lines.append(f"leak blocked: {report['reference_gate']['leak_blocked']}")
    lines.append("\n## Direct recompute consistency\n")
    direct = report["direct_recompute_consistency"]
    lines.append(
        f"recomputed={direct['recomputed']}, missing_source_path={direct['missing_source_path']}, "
        f"max_abs_delta={direct['max_abs_delta']}"
    )
    return "\n".join(lines) + "\n"
