"""Read-only adjacent-release nine-axis corpus comparison.

Only ignored artifacts below ``tmp`` are written.  Source beatmaps,
calibration data, runtime selection, and model files are never mutated.

The default replay remains beta.7/beta.8.  Setting
``MAP_DEMAND_AUDIT_PAIR=beta8-beta9`` reuses the same frozen audit contract for
the beta.8/beta.9 release comparison, including in spawned worker processes.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
TMP = ROOT / "tmp"
for path in (TOOLS, TMP):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from map_demand_v01 import model_v010_beta7 as BETA7  # noqa: E402
from map_demand_v01 import model_v010_beta8 as BETA8  # noqa: E402
from map_demand_v01 import model_v010_beta9 as BETA9  # noqa: E402
from map_demand_v01.calibration import load_calibration  # noqa: E402
from map_demand_v01.osu_db_star_scale import (  # noqa: E402
    read_nm_star_distribution,
)
import profile_audit_v01 as selection_basis  # noqa: E402


if os.environ.get("MAP_DEMAND_AUDIT_PAIR") == "beta8-beta9":
    BETA7, BETA8 = BETA8, BETA9


CALIBRATION: dict[str, Any] | None = None


def _init_worker(calibration_dir: str) -> None:
    global CALIBRATION
    CALIBRATION = load_calibration(Path(calibration_dir))


def _checksum(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _category(
    task: dict[str, Any],
    alternative_mechanism: Mapping[str, Any] | None = None,
    input_role: str | None = None,
) -> str:
    relative = str(task.get("relative_path") or "").casefold()
    meta = task.get("selection_meta") or {}
    if "aspire" in relative:
        return "aspire"
    if input_role == BETA8.AUXILIARY_HITSOUND_INPUT_ROLE:
        return "auxiliary_input_layer"
    if isinstance(alternative_mechanism, Mapping):
        excluded = alternative_mechanism.get("excluded_transition_count")
        candidates = alternative_mechanism.get("candidate_transition_count")
        maximum = alternative_mechanism.get("max_concurrent_active_sliders")
        excluded_share = (
            float(excluded) / float(candidates)
            if isinstance(excluded, (int, float))
            and isinstance(candidates, (int, float))
            and float(candidates) > 0.0
            else 0.0
        )
        high_concurrency_cluster = (
            isinstance(maximum, (int, float))
            and float(maximum) >= 8.0
            and excluded_share >= 0.05
        )
        map_level_abstention = alternative_mechanism.get(
            "map_level_abstention"
        ) is True
        invalid_geometry = alternative_mechanism.get(
            "invalid_single_cursor_geometry_count"
        )
        if (
            excluded_share >= 0.15
            or high_concurrency_cluster
            or map_level_abstention
            or (
                isinstance(invalid_geometry, (int, float))
                and float(invalid_geometry) > 0.0
            )
        ):
            return "alternative_mechanism"
    if meta.get("pathological") or meta.get("known_broken") or meta.get("flags"):
        return "non_aspire_pathological"
    reasons = set(task.get("selection_reasons") or ())
    if reasons - {"systematic_regular"}:
        return "legal_extreme"
    return "ordinary"


def _axis_view(item: dict[str, Any]) -> dict[str, Any]:
    physical = item.get("physical_peak")
    if isinstance(physical, dict):
        physical = physical.get("star")
    confidence = item.get("evidence_confidence")
    if isinstance(confidence, dict):
        confidence = confidence.get("value")
    return {
        "status": item.get("status"),
        "value": item.get("demand_star_equivalent"),
        "stars": item.get("stars"),
        "physical_peak": physical,
        "evidence_confidence": confidence,
        "establishment": (
            item.get("establishment", {}).get("frontier_star")
            if isinstance(item.get("establishment"), dict)
            else None
        ),
        "sustain": (
            item.get("sustain", {}).get("frontier_star")
            if isinstance(item.get("sustain"), dict)
            else None
        ),
        "recurrence": (
            item.get("recurrence", {}).get("frontier_star")
            if isinstance(item.get("recurrence"), dict)
            else None
        ),
        "public_frontier": (
            item.get("public_frontier", {}).get("frontier_star")
            if isinstance(item.get("public_frontier"), dict)
            else None
        ),
        "public_frontier_component": (
            item.get("public_frontier", {}).get("selected_component")
            if isinstance(item.get("public_frontier"), dict)
            else None
        ),
        "axis_contract_version": item.get("axis_contract_version"),
    }


def _analyse(task: dict[str, Any]) -> dict[str, Any]:
    assert CALIBRATION is not None
    started = time.perf_counter()
    path = Path(task["absolute_path"])
    try:
        observed_checksum = _checksum(path)
        frozen_checksum = task.get("checksum")
        checksum_matches = (
            frozen_checksum is None or observed_checksum == frozen_checksum
        )
        rows, features, metadata = BETA8.extract_from_path(str(path))
        components, warnings = BETA8.extract_components(
            rows,
            features,
            metadata.get("difficulty"),
            clock_rate=metadata.get("mod_transform_context", {}).get(
                "clock_rate", 1.0
            ),
            effective_mods=metadata.get("mod_context", {}).get(
                "effective_mods", ()
            ),
            source_local_signal_version=metadata.get("local_signal_version"),
        )
        if task.get("nm_star_anchor") is not None:
            components["v091_nm_star_anchor"] = task["nm_star_anchor"]
        kwargs = {
            "checksum": observed_checksum,
            "components": components,
            "calibration": CALIBRATION,
            "requested_mods": (),
            "applied_mod_context": metadata.get("mod_transform_context"),
        }
        old = BETA7.analyze_components(**kwargs)
        new = BETA8.analyze_components(**kwargs)
        alternative_mechanism = (
            components.get("beta8_spatial_axes", {})
            .get("jump_aim", {})
            .get("signals", {})
            .get("alternative_mechanism")
        )
        input_role_payload = components.get("beta8_input_role")
        input_role = (
            input_role_payload.get("role")
            if isinstance(input_role_payload, Mapping)
            else None
        )
        return {
            **task,
            "category": _category(task, alternative_mechanism, input_role),
            "ok": old.get("status") == "OK" and new.get("status") == "OK",
            "observed_checksum": observed_checksum,
            "source_checksum_matches_frozen": checksum_matches,
            "provenance_warning": (
                None
                if checksum_matches
                else f"expected {frozen_checksum}, observed {observed_checksum}"
            ),
            "seconds": time.perf_counter() - started,
            "object_count": metadata.get("object_count"),
            "component_warnings": warnings,
            "model_warnings": new.get("warnings", []),
            "input_role": input_role_payload,
            "alternative_mechanism": alternative_mechanism,
            "beta7": {
                axis: _axis_view(item)
                for axis, item in old.get("axes", {}).items()
            },
            "beta8": {
                axis: _axis_view(item)
                for axis, item in new.get("axes", {}).items()
            },
        }
    except Exception as exc:
        return {
            **task,
            "category": _category(task),
            "ok": False,
            "seconds": time.perf_counter() - started,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _stats(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "p50": _quantile(values, 0.50),
        "p90": _quantile(values, 0.90),
        "p99": _quantile(values, 0.99),
        "max": max(values) if values else None,
        "mean": statistics.fmean(values) if values else None,
        "lt_1_count": sum(value < 1.0 for value in values),
        "lt_2_count": sum(value < 2.0 for value in values),
        "gt_10_count": sum(value > 10.0 for value in values),
    }


def _finite_values(
    rows: list[dict[str, Any]], version: str, axis: str, field: str
) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(version, {}).get(axis, {}).get(field)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        ):
            values.append(float(value))
    return values


def _summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [row for row in results if row.get("ok")]
    failed = [row for row in results if not row.get("ok")]
    source_drift = [
        row
        for row in results
        if row.get("source_checksum_matches_frozen") is False
    ]
    cohorts: dict[str, Any] = {}
    for category in (
        "ordinary",
        "legal_extreme",
        "auxiliary_input_layer",
        "alternative_mechanism",
        "non_aspire_pathological",
        "aspire",
        "all",
    ):
        rows = ok if category == "all" else [
            row for row in ok if row["category"] == category
        ]
        axes: dict[str, Any] = {}
        for axis in BETA8.AXIS_ORDER:
            before = _finite_values(rows, "beta7", axis, "value")
            after = _finite_values(rows, "beta8", axis, "value")
            paired_delta = [
                float(row["beta8"][axis]["value"])
                - float(row["beta7"][axis]["value"])
                for row in rows
                if row.get("beta7", {}).get(axis, {}).get("value") is not None
                and row.get("beta8", {}).get(axis, {}).get("value") is not None
            ]
            axes[axis] = {
                "beta7": _stats(before),
                "beta8": _stats(after),
                "delta": _stats(paired_delta),
            }
            if axis in BETA8.SUPPORT_AWARE_AXES:
                axes[axis]["physical_peak"] = _stats(
                    _finite_values(rows, "beta8", axis, "physical_peak")
                )
                axes[axis]["sustain"] = _stats(
                    _finite_values(rows, "beta8", axis, "sustain")
                )
                axes[axis]["recurrence"] = _stats(
                    _finite_values(rows, "beta8", axis, "recurrence")
                )
        cohorts[category] = {"count": len(rows), "axes": axes}

    ranked: dict[str, Any] = {}
    for axis in BETA8.AXIS_ORDER:
        emitted = [
            row
            for row in ok
            if row.get("beta8", {}).get(axis, {}).get("value") is not None
        ]
        rank_payload: dict[str, Any] = {
            "highest_public": sorted(
                (
                    {
                        "relative_path": row["relative_path"],
                        "category": row["category"],
                        "nm_star_anchor": row.get("nm_star_anchor"),
                        "beta7": row["beta7"][axis]["value"],
                        "beta8": row["beta8"][axis]["value"],
                        "physical_peak": row["beta8"][axis]["physical_peak"],
                    }
                    for row in emitted
                ),
                key=lambda item: item["beta8"],
                reverse=True,
            )[:20],
            "highest_ratio_to_nm_star": sorted(
                (
                    {
                        "relative_path": row["relative_path"],
                        "category": row["category"],
                        "nm_star_anchor": row.get("nm_star_anchor"),
                        "beta8": row["beta8"][axis]["value"],
                        "ratio": row["beta8"][axis]["value"]
                        / float(row["nm_star_anchor"]),
                    }
                    for row in emitted
                    if isinstance(row.get("nm_star_anchor"), (int, float))
                    and not isinstance(row.get("nm_star_anchor"), bool)
                    and math.isfinite(float(row["nm_star_anchor"]))
                    and float(row["nm_star_anchor"]) > 0.0
                ),
                key=lambda item: item["ratio"],
                reverse=True,
            )[:20],
            "largest_drop": sorted(
                (
                    {
                        "relative_path": row["relative_path"],
                        "category": row["category"],
                        "beta7": row["beta7"][axis]["value"],
                        "beta8": row["beta8"][axis]["value"],
                        "physical_peak": row["beta8"][axis]["physical_peak"],
                        "delta": row["beta8"][axis]["value"]
                        - row["beta7"][axis]["value"],
                    }
                    for row in emitted
                ),
                key=lambda item: item["delta"],
            )[:20],
        }
        if axis in BETA8.SUPPORT_AWARE_AXES:
            rank_payload["highest_physical_peak"] = sorted(
                (
                    {
                        "relative_path": row["relative_path"],
                        "category": row["category"],
                        "beta8": row["beta8"][axis]["value"],
                        "physical_peak": row["beta8"][axis]["physical_peak"],
                    }
                    for row in emitted
                    if isinstance(
                        row["beta8"][axis]["physical_peak"], (int, float)
                    )
                ),
                key=lambda item: item["physical_peak"],
                reverse=True,
            )[:20]
        ranked[axis] = rank_payload

    invariant_violations: list[dict[str, Any]] = []
    for row in ok:
        for axis in BETA8.AXIS_ORDER:
            before = row["beta7"][axis].get("value")
            after = row["beta8"][axis].get("value")
            if axis in BETA8.INHERITED_AXIS_CONTRACTS:
                if before != after:
                    invariant_violations.append(
                        {
                            "relative_path": row["relative_path"],
                            "axis": axis,
                            "code": "INHERITED_AXIS_NUMERIC_DRIFT",
                            "beta7": before,
                            "beta8": after,
                        }
                    )
                expected_contract = BETA8.INHERITED_AXIS_CONTRACTS[axis]
                if row["beta8"][axis].get("axis_contract_version") != expected_contract:
                    invariant_violations.append(
                        {
                            "relative_path": row["relative_path"],
                            "axis": axis,
                            "code": "INHERITED_AXIS_CONTRACT_MISMATCH",
                        }
                    )
                continue
            if axis in BETA8.REBUILT_LOCAL_AXES:
                view = row["beta8"][axis]
                if view.get("status") != "EMITTED":
                    continue
                value = view.get("value")
                stars = view.get("stars")
                expected_contract = BETA8.REBUILT_LOCAL_AXIS_CONTRACTS[axis]
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    or value != stars
                    or view.get("axis_contract_version") != expected_contract
                ):
                    invariant_violations.append(
                        {
                            "relative_path": row["relative_path"],
                            "axis": axis,
                            "code": "REBUILT_LOCAL_AXIS_CONTRACT_MISMATCH",
                            "value": value,
                            "stars": stars,
                            "axis_contract_version": view.get(
                                "axis_contract_version"
                            ),
                        }
                    )
                continue
            view = row["beta8"][axis]
            if view.get("status") != "EMITTED":
                continue
            numeric = {
                field: view.get(field)
                for field in (
                    "value",
                    "stars",
                    "physical_peak",
                    "public_frontier",
                    "establishment",
                    "sustain",
                    "recurrence",
                    "evidence_confidence",
                )
            }
            if not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in numeric.values()
            ):
                invariant_violations.append(
                    {
                        "relative_path": row["relative_path"],
                        "axis": axis,
                        "code": "SUPPORT_AXIS_NONFINITE_OR_MISSING",
                        "values": numeric,
                    }
                )
                continue
            if (
                numeric["value"] != numeric["stars"]
                or numeric["value"] != numeric["public_frontier"]
            ):
                invariant_violations.append(
                    {
                        "relative_path": row["relative_path"],
                        "axis": axis,
                        "code": "PUBLIC_FRONTIER_ALIAS_MISMATCH",
                        "values": numeric,
                    }
                )
            selected_component = view.get("public_frontier_component")
            if (
                selected_component not in {"establishment", "sustain", "recurrence"}
                or numeric["value"] != numeric[selected_component]
            ):
                invariant_violations.append(
                    {
                        "relative_path": row["relative_path"],
                        "axis": axis,
                        "code": "PUBLIC_FRONTIER_COMPONENT_MISMATCH",
                        "selected_component": selected_component,
                        "values": numeric,
                    }
                )
            peak = float(numeric["physical_peak"])
            if any(
                not 0.0 <= float(numeric[field]) <= peak + 1e-12
                for field in ("establishment", "sustain", "recurrence")
            ):
                invariant_violations.append(
                    {
                        "relative_path": row["relative_path"],
                        "axis": axis,
                        "code": "FRONTIER_OUTSIDE_PHYSICAL_ENVELOPE",
                        "values": numeric,
                    }
                )
            if not 0.0 <= float(numeric["evidence_confidence"]) <= 1.0:
                invariant_violations.append(
                    {
                        "relative_path": row["relative_path"],
                        "axis": axis,
                        "code": "CONFIDENCE_OUT_OF_RANGE",
                        "values": numeric,
                    }
                )
    return {
        "schema": "map_demand_beta8_nine_axis_audit_v01",
        "beta7": BETA7.MAP_DEMAND_VERSION,
        "beta8": BETA8.MAP_DEMAND_VERSION,
        "map_count": len(results),
        "ok_count": len(ok),
        "failure_count": len(failed),
        "failures": [
            {
                "relative_path": row.get("relative_path"),
                "error_type": row.get("error_type"),
                "error": row.get("error"),
            }
            for row in failed
        ],
        "source_drift_count": len(source_drift),
        "source_drift": [
            {
                "relative_path": row.get("relative_path"),
                "expected_checksum": row.get("checksum"),
                "observed_checksum": row.get("observed_checksum"),
            }
            for row in source_drift
        ],
        "cohorts": cohorts,
        "axis_extremes": ranked,
        "invariant_violation_count": len(invariant_violations),
        "invariant_violations": invariant_violations[:200],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--regular-count", type=int, default=1000)
    parser.add_argument(
        "--tasks",
        help=(
            "Replay an exact frozen tasks.json instead of selecting from the "
            "current osu!.db and QA manifests"
        ),
    )
    parser.add_argument(
        "--workers", type=int, default=max(1, min(8, os.cpu_count() or 1))
    )
    parser.add_argument("--output-dir", default="tmp/profile-audit-beta8")
    args = parser.parse_args()

    calibration_dir = ROOT / (
        "training/datasets/"
        "map_demand_calibration_v04_unbounded_star_scale_20k"
    )
    if args.tasks:
        task_path = Path(args.tasks).resolve()
        tasks = json.loads(task_path.read_text(encoding="utf-8"))
        if not isinstance(tasks, list) or not all(
            isinstance(task, dict) for task in tasks
        ):
            raise ValueError("--tasks must point to a JSON array of task objects")
        star_info: dict[str, Any] = {}
        task_source = {
            "mode": "frozen_replay",
            "path": str(task_path),
            "file_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
        }
    else:
        selection = selection_basis._read_jsonl(  # noqa: SLF001
            ROOT / "training/datasets/feature_qa_v02/selection_20k.jsonl"
        )
        star_info = read_nm_star_distribution(Path(r"G:\osu! 20210821\osu!.db"))
        tasks = selection_basis._select_tasks(  # noqa: SLF001
            selection,
            star_info["relative_path_to_nm_stars"],
            songs_root=Path(r"G:\osu! 20210821\Songs"),
            regular_count=args.regular_count,
            old_extremes=selection_basis._old_extreme_checksums(  # noqa: SLF001
                ROOT
                / "training/datasets/"
                "map_demand_qa_v04_unbounded_star_scale_20k/qa_report.json"
            ),
        )
        task_source = {
            "mode": "selected_from_current_inputs",
            "osu_db_sha256": star_info.get("database_sha256"),
        }
    out_dir = (ROOT / args.output_dir).resolve()
    expected_tmp = (ROOT / "tmp").resolve()
    if not out_dir.is_relative_to(expected_tmp):
        raise ValueError("--output-dir must remain below repository tmp")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tasks.json").write_text(
        json.dumps(tasks, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )

    started = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=_init_worker,
        initargs=(str(calibration_dir),),
    ) as executor:
        results = list(executor.map(_analyse, tasks, chunksize=2))
    results.sort(key=lambda row: row["checksum"])
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(
                json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n"
            )
    summary = _summarise(results)
    summary["seconds_wall"] = time.perf_counter() - started
    summary["workers"] = args.workers
    summary["osu_db_sha256"] = star_info.get("database_sha256")
    summary["task_source"] = task_source
    summary["tasks_sha256"] = hashlib.sha256(
        json.dumps(
            tasks,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=2))
    return int(bool(summary["failure_count"]))


if __name__ == "__main__":
    raise SystemExit(main())
