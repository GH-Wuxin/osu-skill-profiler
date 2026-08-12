#!/usr/bin/env python3
"""Old-vs-corrected semantic delta QA for foundation remediation v0.1.

The same parsed map is evaluated under Feature 0.1/0.2, Local 0.2/0.3 and
Reference 0.1/0.2.  Output is resumable JSONL plus an exact aggregate summary.
No model, label, network request or corpus mutation is involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from osu_skill_profiler.features.extractor import FeatureExtractor  # noqa: E402
from osu_skill_profiler.features.schema import (  # noqa: E402
    FEATURE_SCHEMA_V01,
    FEATURE_SCHEMA_V02,
    FEATURE_VERSION,
    LEGACY_FEATURE_VERSION,
)
from osu_skill_profiler.parser.normalized import normalize  # noqa: E402
from osu_skill_profiler.parser.osu_parser import parse_osu_file  # noqa: E402
from osu_skill_profiler.reference.ppy.contract import (  # noqa: E402
    LEGACY_REFERENCE_VERSION,
    REFERENCE_NUMERIC_SIGNALS,
    REFERENCE_VERSION,
)
from osu_skill_profiler.reference.ppy.extractor import ReferenceSignalExtractor  # noqa: E402
from osu_skill_profiler.signals.contract import (  # noqa: E402
    LEGACY_SIGNAL_VERSION,
    NUMERIC_SIGNALS_V02,
    SIGNAL_VERSION,
)
from osu_skill_profiler.signals.extractor import LocalSignalExtractor  # noqa: E402

QA_VERSION = "0.3.0"
MAGNITUDE_LABELS = ("<=1e-9", "<=1e-6", "<=1e-3", "<=1", "<=1e3", ">1e3")
EXPECTED_VERSIONS = {
    "feature": [LEGACY_FEATURE_VERSION, FEATURE_VERSION],
    "local": [LEGACY_SIGNAL_VERSION, SIGNAL_VERSION],
    "reference": [LEGACY_REFERENCE_VERSION, REFERENCE_VERSION],
}
COMMON_FEATURE_FIELDS = sorted(set(FEATURE_SCHEMA_V01) & set(FEATURE_SCHEMA_V02))
LOCAL_NUMERIC_FIELDS = sorted(NUMERIC_SIGNALS_V02)
REFERENCE_NUMERIC_FIELDS = sorted(REFERENCE_NUMERIC_SIGNALS)


def _changed(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is not right
    if isinstance(left, bool) or isinstance(right, bool):
        return left != right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        lf, rf = float(left), float(right)
        if not (math.isfinite(lf) and math.isfinite(rf)):
            return not (math.isnan(lf) and math.isnan(rf)) and lf != rf
        return not math.isclose(lf, rf, rel_tol=1e-12, abs_tol=1e-12)
    return left != right


def _magnitude_bin(value: float) -> int:
    if value <= 1e-9:
        return 0
    if value <= 1e-6:
        return 1
    if value <= 1e-3:
        return 2
    if value <= 1.0:
        return 3
    if value <= 1e3:
        return 4
    return 5


def _represented_le(scale: float, coefficient: float, limit: float) -> bool:
    """Compare ``scale * coefficient`` with a finite limit without overflow."""

    if scale == 0.0 or coefficient == 0.0:
        return True
    common_scale = max(scale, limit)
    return coefficient * (scale / common_scale) <= limit / common_scale


def _represented_value(scale: float, coefficient: float) -> tuple[float | None, bool]:
    """Materialise a non-negative scaled value when binary64 can represent it."""

    if scale == 0.0 or coefficient == 0.0:
        return 0.0, False
    if coefficient > sys.float_info.max / scale:
        return None, True
    return scale * coefficient, False


def _finite_abs_delta(left: float, right: float) -> tuple[float, float]:
    """Return an overflow-safe ``(scale, coefficient)`` for ``abs(right-left)``."""

    direct = abs(right - left)
    if math.isfinite(direct):
        # Preserve the original binary64 subtraction and magnitude-bin
        # boundary semantics for every ordinary finite delta.  Normalising
        # before subtraction introduces a second rounding and can move an
        # exact 1e3 delta into the >1e3 bin when the operands are very large.
        return direct, 1.0 if direct else 0.0
    scale = max(abs(left), abs(right))
    if scale == 0.0:
        return 0.0, 0.0
    return scale, abs(right / scale - left / scale)


def _add_scaled_positive(stats: dict[str, Any], scale: float, coefficient: float) -> None:
    """Accumulate a represented positive value without overflowing its sum."""

    if not all(math.isfinite(value) and value >= 0.0 for value in (scale, coefficient)):
        raise ValueError("scaled delta components must be finite and non-negative")
    if scale == 0.0 or coefficient == 0.0:
        return
    old_scale = float(stats["abs_delta_sum_scale"])
    old_coefficient = float(stats["abs_delta_sum_scaled"])
    target_scale = max(old_scale, scale)
    stats["abs_delta_sum_scale"] = target_scale
    stats["abs_delta_sum_scaled"] = (
        old_coefficient * (old_scale / target_scale)
        + coefficient * (scale / target_scale)
    )
    value, overflow = _represented_value(
        float(stats["abs_delta_sum_scale"]),
        float(stats["abs_delta_sum_scaled"]),
    )
    stats["abs_delta_sum"] = value
    stats["abs_delta_sum_overflow"] = overflow


def _update_scaled_max(stats: dict[str, Any], scale: float, coefficient: float) -> None:
    old_scale = float(stats["abs_delta_max_scale"])
    old_coefficient = float(stats["abs_delta_max_scaled"])
    common_scale = max(old_scale, scale)
    old_normalized = old_coefficient * (old_scale / common_scale) if common_scale else 0.0
    new_normalized = coefficient * (scale / common_scale) if common_scale else 0.0
    if new_normalized > old_normalized:
        stats["abs_delta_max_scale"] = scale
        stats["abs_delta_max_scaled"] = coefficient
    value, overflow = _represented_value(
        float(stats["abs_delta_max_scale"]),
        float(stats["abs_delta_max_scaled"]),
    )
    stats["abs_delta_max"] = value
    stats["abs_delta_max_overflow"] = overflow


def _empty_field_delta() -> dict[str, Any]:
    return {
        "changed": 0,
        "missing_introduced": 0,
        "missing_resolved": 0,
        "nonfinite_old": 0,
        "nonfinite_new": 0,
        "nonfinite_introduced": 0,
        "nonfinite_resolved": 0,
        "abs_delta_sum": 0.0,
        "abs_delta_sum_scale": 0.0,
        "abs_delta_sum_scaled": 0.0,
        "abs_delta_sum_overflow": False,
        "abs_delta_max": 0.0,
        "abs_delta_max_scale": 0.0,
        "abs_delta_max_scaled": 0.0,
        "abs_delta_max_overflow": False,
        "magnitude_bins": [0] * len(MAGNITUDE_LABELS),
    }


def _field_delta(old_values: Iterable[Any], new_values: Iterable[Any]) -> dict[str, dict[str, Any]]:
    # The caller supplies one field at a time via singleton-key rows; keeping
    # this helper generic makes aggregation logic identical across layers.
    result: dict[str, dict[str, Any]] = {}
    for old_row, new_row in zip(old_values, new_values):
        keys = set(old_row) | set(new_row)
        for field in keys:
            old = old_row.get(field)
            new = new_row.get(field)
            stats = result.setdefault(field, _empty_field_delta())
            old_nonfinite = isinstance(old, float) and not math.isfinite(old)
            new_nonfinite = isinstance(new, float) and not math.isfinite(new)
            if old_nonfinite:
                stats["nonfinite_old"] += 1
            if new_nonfinite:
                stats["nonfinite_new"] += 1
            if old_nonfinite and not new_nonfinite:
                stats["nonfinite_resolved"] += 1
            elif not old_nonfinite and new_nonfinite:
                stats["nonfinite_introduced"] += 1
            if old is not None and new is None:
                stats["missing_introduced"] += 1
            elif old is None and new is not None:
                stats["missing_resolved"] += 1
            if not _changed(old, new):
                continue
            stats["changed"] += 1
            if isinstance(old, (int, float)) and not isinstance(old, bool) and isinstance(new, (int, float)) and not isinstance(new, bool):
                old_f, new_f = float(old), float(new)
                if math.isfinite(old_f) and math.isfinite(new_f):
                    scale, coefficient = _finite_abs_delta(old_f, new_f)
                    _add_scaled_positive(stats, scale, coefficient)
                    _update_scaled_max(stats, scale, coefficient)
                    for index, limit in enumerate((1e-9, 1e-6, 1e-3, 1.0, 1e3)):
                        if _represented_le(scale, coefficient, limit):
                            stats["magnitude_bins"][index] += 1
                            break
                    else:
                        stats["magnitude_bins"][5] += 1
    return {
        field: stats
        for field, stats in result.items()
        if any(
            (
                stats["changed"],
                stats["missing_introduced"],
                stats["missing_resolved"],
                stats["nonfinite_old"],
                stats["nonfinite_new"],
                stats["nonfinite_introduced"],
                stats["nonfinite_resolved"],
            )
        )
    }


def _selected_rows(rows: list[dict], fields: Iterable[str]) -> list[dict]:
    selected = tuple(fields)
    return [{field: row.get(field) for field in selected} for row in rows]


def _blocked_count(rows: list[dict], key: str) -> int:
    prefixes = ("path_blocked:", "slider_spans_exceeded:")
    exact = {"slider_tick_count_exceeded"}
    total = 0
    for row in rows:
        provenance = row.get(key) or ()
        if any(flag in exact or any(str(flag).startswith(prefix) for prefix in prefixes) for flag in provenance):
            total += 1
    return total


def _process(record: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(record["root"])
    path = root / record["relative_path"]
    beatmap = parse_osu_file(path)
    nmap = normalize(beatmap)

    t0 = time.perf_counter()
    feature_old = FeatureExtractor(LEGACY_FEATURE_VERSION).extract(nmap)
    feature_new = FeatureExtractor(FEATURE_VERSION).extract(nmap)
    feature_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    local_old = LocalSignalExtractor(LEGACY_SIGNAL_VERSION).extract(beatmap)
    local_old_ms = (time.perf_counter() - t0) * 1000.0
    t0 = time.perf_counter()
    local_new = LocalSignalExtractor(SIGNAL_VERSION).extract(beatmap)
    local_new_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    reference_old = ReferenceSignalExtractor(LEGACY_REFERENCE_VERSION).extract(beatmap)
    reference_old_ms = (time.perf_counter() - t0) * 1000.0
    t0 = time.perf_counter()
    reference_new = ReferenceSignalExtractor(REFERENCE_VERSION).extract(beatmap)
    reference_new_ms = (time.perf_counter() - t0) * 1000.0

    object_count = len(beatmap.hit_objects)
    counts = {
        len(local_old["objects"]), len(local_new["objects"]),
        len(reference_old["objects"]), len(reference_new["objects"]),
    }
    if counts != {object_count}:
        raise ValueError(f"object alignment mismatch: parsed={object_count} derived={sorted(counts)}")

    common_feature_fields = sorted(set(FEATURE_SCHEMA_V01) & set(FEATURE_SCHEMA_V02))
    feature_delta = _field_delta(
        [{field: feature_old.get(field) for field in common_feature_fields}],
        [{field: feature_new.get(field) for field in common_feature_fields}],
    )
    local_delta = _field_delta(
        _selected_rows(local_old["objects"], NUMERIC_SIGNALS_V02),
        _selected_rows(local_new["objects"], NUMERIC_SIGNALS_V02),
    )
    reference_delta = _field_delta(
        _selected_rows(reference_old["objects"], REFERENCE_NUMERIC_SIGNALS),
        _selected_rows(reference_new["objects"], REFERENCE_NUMERIC_SIGNALS),
    )

    local_changed_indices = []
    reference_changed_indices = []
    reading_only_indices = []
    for index in range(object_count):
        local_changed = {
            field for field in NUMERIC_SIGNALS_V02
            if _changed(local_old["objects"][index].get(field), local_new["objects"][index].get(field))
        }
        ref_changed = {
            field for field in REFERENCE_NUMERIC_SIGNALS
            if _changed(reference_old["objects"][index].get(field), reference_new["objects"][index].get(field))
        }
        if local_changed:
            local_changed_indices.append(index)
        if ref_changed:
            reference_changed_indices.append(index)
        if ref_changed == {"ref.ppy.reading"}:
            reading_only_indices.append(index)

    repeat_slider_count = sum(
        1 for obj in beatmap.hit_objects
        if obj.object_type == "slider" and max(1, int(obj.slider_slides or 1)) > 1
    )
    slider_count = sum(obj.object_type == "slider" for obj in beatmap.hit_objects)
    return {
        "sample_id": record["sample_id"],
        "checksum": record.get("checksum"),
        "status": "PASS",
        "qa_version": QA_VERSION,
        "versions": EXPECTED_VERSIONS,
        "object_count": object_count,
        "slider_count": slider_count,
        "repeat_slider_count": repeat_slider_count,
        "feature_delta": feature_delta,
        "local_delta": local_delta,
        "reference_delta": reference_delta,
        "feature_changed_field_count": len(feature_delta),
        "local_changed_object_count": len(local_changed_indices),
        "reference_changed_object_count": len(reference_changed_indices),
        "reference_reading_only_object_count": len(reading_only_indices),
        "local_geometry_blocked_old": _blocked_count(local_old["objects"], "ls.provenance"),
        "local_geometry_blocked_new": _blocked_count(local_new["objects"], "ls.provenance"),
        "reference_geometry_blocked_old": _blocked_count(reference_old["objects"], "ref.provenance"),
        "reference_geometry_blocked_new": _blocked_count(reference_new["objects"], "ref.provenance"),
        "timing_ms": {
            "feature_both": feature_ms,
            "local_old": local_old_ms,
            "local_new": local_new_ms,
            "reference_old": reference_old_ms,
            "reference_new": reference_new_ms,
            "total": (time.perf_counter() - started) * 1000.0,
        },
    }


def _error_record(record: dict[str, Any], error: BaseException) -> dict[str, Any]:
    return {
        "sample_id": record.get("sample_id"),
        "checksum": record.get("checksum"),
        "status": "FAIL",
        "qa_version": QA_VERSION,
        "versions": EXPECTED_VERSIONS,
        "error_type": type(error).__name__,
        "error": str(error),
    }


def _safe_process(record: dict[str, Any]) -> dict[str, Any]:
    try:
        return _process(record)
    except Exception as error:  # noqa: BLE001 - evidence must retain per-map failure
        return _error_record(record, error)


def _load_selection(path: Path, root: Path, limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    sample_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(
                    line,
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError(f"non-standard JSON constant: {value}")
                    ),
                )
            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(f"invalid selection JSON at line {line_number}: {error}") from error
            sample_id = record.get("sample_id")
            relative_path = record.get("relative_path")
            if not isinstance(sample_id, str) or not sample_id:
                raise ValueError(f"selection line {line_number} has no valid sample_id")
            if sample_id in sample_ids:
                raise ValueError(f"duplicate selection sample_id at line {line_number}: {sample_id}")
            if not isinstance(relative_path, str) or not relative_path:
                raise ValueError(f"selection line {line_number} has no valid relative_path")
            sample_ids.add(sample_id)
            record["root"] = str(root)
            records.append(record)
            if len(records) >= limit:
                break
    return records


def _delta_stats_complete(stats: Any) -> bool:
    if not isinstance(stats, dict):
        return False
    for key in (
        "changed",
        "missing_introduced",
        "missing_resolved",
        "nonfinite_old",
        "nonfinite_new",
        "nonfinite_introduced",
        "nonfinite_resolved",
    ):
        value = stats.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return False
    for key in ("abs_delta_sum_scale", "abs_delta_sum_scaled", "abs_delta_max_scale", "abs_delta_max_scaled"):
        value = stats.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or value < 0:
            return False
    for prefix in ("abs_delta_sum", "abs_delta_max"):
        overflow = stats.get(f"{prefix}_overflow")
        value = stats.get(prefix)
        if not isinstance(overflow, bool):
            return False
        if overflow:
            if value is not None:
                return False
        elif not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or value < 0:
            return False
    bins = stats.get("magnitude_bins")
    return (
        isinstance(bins, list)
        and len(bins) == len(MAGNITUDE_LABELS)
        and all(isinstance(count, int) and not isinstance(count, bool) and count >= 0 for count in bins)
    )


def _resume_record_complete(row: dict[str, Any]) -> bool:
    if row.get("status") != "PASS" or row.get("qa_version") != QA_VERSION or row.get("versions") != EXPECTED_VERSIONS:
        return False
    for key in (
        "object_count", "slider_count", "repeat_slider_count",
        "feature_changed_field_count", "local_changed_object_count",
        "reference_changed_object_count", "reference_reading_only_object_count",
        "local_geometry_blocked_old", "local_geometry_blocked_new",
        "reference_geometry_blocked_old", "reference_geometry_blocked_new",
    ):
        value = row.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return False
    object_count = row.get("object_count")
    slider_count = row.get("slider_count")
    repeat_slider_count = row.get("repeat_slider_count")
    local_changed = row.get("local_changed_object_count")
    reference_changed = row.get("reference_changed_object_count")
    reading_only = row.get("reference_reading_only_object_count")
    if not (
        0 <= slider_count <= object_count
        and 0 <= repeat_slider_count <= slider_count
        and 0 <= local_changed <= object_count
        and 0 <= reference_changed <= object_count
        and 0 <= reading_only <= reference_changed
    ):
        return False
    for key, expected_fields in (
        ("feature_delta", COMMON_FEATURE_FIELDS),
        ("local_delta", LOCAL_NUMERIC_FIELDS),
        ("reference_delta", REFERENCE_NUMERIC_FIELDS),
    ):
        layer = row.get(key)
        if not isinstance(layer, dict) or not all(_delta_stats_complete(stats) for stats in layer.values()):
            return False
        if not set(layer).issubset(set(expected_fields)):
            return False
    if row.get("feature_changed_field_count") != len(row.get("feature_delta") or {}):
        return False
    timing = row.get("timing_ms")
    if not isinstance(timing, dict) or set(timing) != {
        "feature_both", "local_old", "local_new", "reference_old", "reference_new", "total",
    }:
        return False
    return all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value >= 0
        for value in timing.values()
    )


def _strict_json_loads(raw: str) -> Any:
    return json.loads(
        raw,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant: {value}")
        ),
    )


def _prepare_resume_rows(
    out_path: Path,
    resume: bool,
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Atomically retain only unique, current, schema-complete PASS rows."""

    if not resume or not out_path.exists():
        return {}
    expected = {record["sample_id"]: record.get("checksum") for record in records}
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    observed_valid_ids: list[str] = []
    clean = True
    with out_path.open("r", encoding="utf-8") as source:
        for raw_line in source:
            if not raw_line.strip():
                clean = False
                continue
            try:
                row = _strict_json_loads(raw_line)
            except (json.JSONDecodeError, ValueError):
                clean = False
                continue
            sample_id = row.get("sample_id") if isinstance(row, dict) else None
            if (
                not isinstance(sample_id, str)
                or sample_id not in expected
                or row.get("checksum") != expected[sample_id]
                or not _resume_record_complete(row)
            ):
                clean = False
                continue
            candidates[sample_id].append(row)
            observed_valid_ids.append(sample_id)

    done: dict[str, dict[str, Any]] = {}
    for record in records:
        sample_id = record["sample_id"]
        rows = candidates.get(sample_id, [])
        if len(rows) == 1:
            done[sample_id] = rows[0]
        elif rows:
            # Conflicting or repeated evidence is not trusted as completed.
            clean = False

    expected_order = [record["sample_id"] for record in records if record["sample_id"] in done]
    if list(done) != expected_order or observed_valid_ids != expected_order:
        clean = False

    if not clean:
        tmp_path = out_path.with_name(f"{out_path.name}.resume.tmp")
        with tmp_path.open("w", encoding="utf-8", newline="\n") as retained:
            for row in done.values():
                retained.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
            retained.flush()
            os.fsync(retained.fileno())
        os.replace(tmp_path, out_path)
    return done


def _atomic_write_json(path: Path, value: Any) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _merge_field_delta(target: dict[str, dict[str, Any]], source: dict[str, dict[str, Any]]) -> None:
    for field, stats in source.items():
        current = target.setdefault(field, _empty_field_delta())
        for key in (
            "changed",
            "missing_introduced",
            "missing_resolved",
            "nonfinite_old",
            "nonfinite_new",
            "nonfinite_introduced",
            "nonfinite_resolved",
        ):
            current[key] += int(stats[key])
        _add_scaled_positive(
            current,
            float(stats["abs_delta_sum_scale"]),
            float(stats["abs_delta_sum_scaled"]),
        )
        _update_scaled_max(
            current,
            float(stats["abs_delta_max_scale"]),
            float(stats["abs_delta_max_scaled"]),
        )
        for index, count in enumerate(stats["magnitude_bins"]):
            current["magnitude_bins"][index] += int(count)


def _summarize(rows: Iterable[dict[str, Any]], *, selection: Path, workers: int, wall_seconds: float) -> dict[str, Any]:
    rows = list(rows)
    failures = [row for row in rows if row.get("status") != "PASS"]
    passed = [row for row in rows if row.get("status") == "PASS"]
    layer_delta: dict[str, dict[str, dict[str, Any]]] = {"feature": {}, "local": {}, "reference": {}}
    totals = Counter()
    categories = Counter()
    timing: dict[str, list[float]] = defaultdict(list)
    for row in passed:
        _merge_field_delta(layer_delta["feature"], row["feature_delta"])
        _merge_field_delta(layer_delta["local"], row["local_delta"])
        _merge_field_delta(layer_delta["reference"], row["reference_delta"])
        totals["objects"] += row["object_count"]
        totals["sliders"] += row["slider_count"]
        totals["repeat_sliders"] += row["repeat_slider_count"]
        totals["local_changed_objects"] += row["local_changed_object_count"]
        totals["reference_changed_objects"] += row["reference_changed_object_count"]
        totals["reference_reading_only_objects"] += row["reference_reading_only_object_count"]
        for key in ("local_geometry_blocked_old", "local_geometry_blocked_new", "reference_geometry_blocked_old", "reference_geometry_blocked_new"):
            totals[key] += row[key]
        repeat = row["repeat_slider_count"] > 0
        local_changed = row["local_changed_object_count"] > 0
        reference_changed = row["reference_changed_object_count"] > 0
        categories[f"maps_repeat_{str(repeat).lower()}"] += 1
        if local_changed:
            categories[f"local_changed_maps_repeat_{str(repeat).lower()}"] += 1
        if reference_changed:
            categories[f"reference_changed_maps_repeat_{str(repeat).lower()}"] += 1
        for key, value in row["timing_ms"].items():
            timing[key].append(float(value))

    def timing_summary(values: list[float]) -> dict[str, float]:
        if not values:
            return {"mean": 0.0, "max": 0.0}
        return {"mean": sum(values) / len(values), "max": max(values)}

    nonfinite_introduced = sum(
        stats["nonfinite_introduced"]
        for layer in layer_delta.values() for stats in layer.values()
    )
    nonfinite_resolved = sum(
        stats["nonfinite_resolved"]
        for layer in layer_delta.values() for stats in layer.values()
    )
    missing_introduced = sum(
        stats["missing_introduced"]
        for layer in layer_delta.values() for stats in layer.values()
    )
    return {
        "qa_version": QA_VERSION,
        "status": "PASS" if not failures and nonfinite_introduced == 0 and missing_introduced == 0 else "FAIL",
        "versions": EXPECTED_VERSIONS,
        "selection": str(selection.as_posix()),
        "selection_sha256": hashlib.sha256(selection.read_bytes()).hexdigest(),
        "workers": workers,
        "wall_seconds": wall_seconds,
        "maps_requested": len(rows),
        "maps_passed": len(passed),
        "maps_failed": len(failures),
        "failures": failures[:100],
        "totals": dict(sorted(totals.items())),
        "map_categories": dict(sorted(categories.items())),
        "schema_changes": {
            "feature_removed": sorted(set(FEATURE_SCHEMA_V01) - set(FEATURE_SCHEMA_V02)),
            "feature_added": sorted(set(FEATURE_SCHEMA_V02) - set(FEATURE_SCHEMA_V01)),
        },
        "field_delta": layer_delta,
        "magnitude_bin_labels": list(MAGNITUDE_LABELS),
        "new_nonfinite_count": nonfinite_introduced,
        "resolved_nonfinite_count": nonfinite_resolved,
        "new_missing_count": missing_introduced,
        "timing_ms_per_map": {key: timing_summary(values) for key, values in sorted(timing.items())},
        "peak_memory": "NOT_MEASURED_MULTIPROCESSING",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")
    if args.limit <= 0:
        parser.error("--limit must be positive")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    records = _load_selection(args.selection, args.root, args.limit)
    out_jsonl = args.out_dir / f"delta_{len(records)}.jsonl"
    done = _prepare_resume_rows(out_jsonl, args.resume, records)
    todo = [record for record in records if record["sample_id"] not in done]
    print(f"delta-qa maps={len(records)} done={len(done)} todo={len(todo)} workers={args.workers}", flush=True)

    started = time.perf_counter()
    mode = "a" if done else "w"
    with out_jsonl.open(mode, encoding="utf-8", newline="\n") as handle:
        if args.workers == 1:
            iterator = map(_safe_process, todo)
            pool = None
        else:
            pool = multiprocessing.Pool(processes=args.workers, maxtasksperchild=100)
            iterator = pool.imap(_safe_process, todo, chunksize=1)
        try:
            for index, row in enumerate(iterator, 1):
                done[row["sample_id"]] = row
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
                if index % 100 == 0:
                    handle.flush()
                    print(f"delta-qa progress={len(done)}/{len(records)}", flush=True)
        finally:
            if pool is not None:
                pool.close()
                pool.join()

    wall_seconds = time.perf_counter() - started
    ordered_rows = [done[record["sample_id"]] for record in records]
    summary = _summarize(ordered_rows, selection=args.selection, workers=args.workers, wall_seconds=wall_seconds)
    summary_path = args.out_dir / f"delta_{len(records)}_summary.json"
    _atomic_write_json(summary_path, summary)
    print(json.dumps({key: summary[key] for key in ("status", "maps_passed", "maps_failed", "wall_seconds", "new_nonfinite_count", "new_missing_count")}, indent=2, allow_nan=False), flush=True)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    # Windows multiprocessing needs the guarded entry point.
    multiprocessing.freeze_support()
    raise SystemExit(main())
