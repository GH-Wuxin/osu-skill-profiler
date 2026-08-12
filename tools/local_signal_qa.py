"""Corrected Local Signal Layer corpus QA (Gates C/D/E).

Phases (gated, deterministic):

  C  5k   stratified real-corpus QA over 5,000 maps
  D  20k  nested expansion to 20,000 maps (only after C has no blocker)
  E  full all eligible manifest maps, streaming/online statistics

Every map runs the full chain:

  parse -> normalize -> corrected Feature contract
                      -> corrected per-object Local Signal contract
                      -> fixed-time 5s segment summaries

No skill labels are produced and no taxonomy is touched. Per-object rows are
stored for the 5k/20k phases (exact object-level
statistics).  The full phase keeps bounded per-map signal summaries plus a
deterministic per-signal reservoir, so no map's object table is retained in
memory.  Anomalies are written with full provenance and are never silently
clipped or imputed.
"""

from __future__ import annotations

import argparse
import functools
import heapq
import json
import math
import os
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
SRC = TOOLS.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Reuse the deterministic manifest selection and online-stat infrastructure
# from the Feature QA pipeline.
from feature_qa import (  # noqa: E402
    MOMENT_SCHEMA_VERSION,
    RESERVOIR_SIZE,
    UNIQUE_CAP,
    build_selection,
    _dist_summary,
    _pearson,
    _percentile,
    _prepare_resume_records,
    _ScaledMoments,
    _StreamAccumulator,
)
from osu_skill_profiler.features.extractor import FeatureExtractor  # noqa: E402
from osu_skill_profiler.features.schema import FEATURE_SCHEMA, FEATURE_VERSION  # noqa: E402
from osu_skill_profiler.parser.normalized import normalize  # noqa: E402
from osu_skill_profiler.parser.osu_parser import parse_osu_file  # noqa: E402
from osu_skill_profiler.signals.contract import NUMERIC_SIGNALS, SIGNAL_SCHEMA, SIGNAL_VERSION  # noqa: E402
from osu_skill_profiler.signals.extractor import LocalSignalExtractor  # noqa: E402

EXPECTED_FEATURE_COUNT = len(FEATURE_SCHEMA)
DEFAULT_SEED = 20260810
WINDOW_MS = 5000.0
EXTREME_FINITE_ABS = 1e12
PER_MAP_RESERVOIR = 256
MAX_EXACT_RECORDS_FULL = 20000
EXACT_PHASES = ("5k", "20k")
PROXY_KEYS = ("duration_ms", "object_count", "bpm_max", "format_version", "slider_ratio", "timing_count", "green_count", "ar", "od", "cs")
BLOCKED_SLIDER_SIGNALS = (
    "ls.slider_duration_ms",
    "ls.slider_velocity_px_per_ms",
    "ls.slider_path_distance_px",
    "ls.slider_span_count",
    "ls.slider_tick_count",
    "ls.slider_nested_object_count",
    "ls.travel_distance_cs_normalised",
    "ls.travel_time_ms",
    "ls.lazy_travel_time_ms",
    "ls.lazy_travel_distance_cs_normalised",
    "ls.lazy_end_position_x_px",
    "ls.lazy_end_position_y_px",
)


def _blocked_provenance_flags(provenance) -> list[str]:
    """Return slider-geometry guard flags found in a row's provenance list."""

    if not isinstance(provenance, (tuple, list)):
        return []
    return [
        flag
        for flag in provenance
        if flag.startswith("path_blocked:")
        or flag.startswith("slider_spans_exceeded:")
        or flag == "slider_tick_count_exceeded"
    ]


class _LocalSignalAccumulator(_StreamAccumulator):
    """Stream accumulator that can merge bounded per-map summaries exactly.

    Welford moments (count/min/max/mean/std/zero) are merged exactly from the
    per-map summary.  Percentiles/near-constant/unique are estimated from a
    deterministic map-weighted reservoir of object values (documented in the
    report; exact object-level statistics are produced by the 5k/20k phases).
    """

    def __init__(self, exact: bool, rng: random.Random) -> None:
        super().__init__(exact, rng)
        self._reservoir_feed = 0

    def merge_map_summary(self, summary: dict) -> None:
        count = int(summary["count"])
        missing = int(summary["missing"])
        nonfinite = int(summary["nonfinite"])
        zero = int(summary["zero"])
        self.total += count + missing + nonfinite
        self.missing += missing
        self.nonfinite += nonfinite
        self.zero += zero
        min_value = summary.get("min")
        max_value = summary.get("max")
        if min_value is not None and (self.min is None or min_value < self.min):
            self.min = min_value
        if max_value is not None and (self.max is None or max_value > self.max):
            self.max = max_value
        if count:
            if summary.get("moments_version") != MOMENT_SCHEMA_VERSION:
                raise ValueError("unsupported per-map moment summary")
            self.moments.merge(
                count,
                float(summary["scale"]),
                float(summary["mean_scaled"]),
                float(summary["m2_scaled"]),
            )
        if not self.exact:
            for value in summary.get("reservoir") or []:
                self._reservoir_feed += 1
                if len(self.reservoir) < RESERVOIR_SIZE:
                    self.reservoir.append(value)
                else:
                    j = self.rng.randrange(self._reservoir_feed)
                    if j < RESERVOIR_SIZE:
                        self.reservoir[j] = value
                if len(self.unique) < UNIQUE_CAP:
                    self.unique.add(value)
                elif value not in self.unique:
                    self.unique_capped = True


# ---------------------------------------------------------------------------
# per-map worker
# ---------------------------------------------------------------------------


def _map_signal_summaries(rows: list[dict], seed: int) -> dict[str, dict]:
    """Exact moments plus a deterministic bounded reservoir per signal."""

    summaries: dict[str, dict] = {}
    for sig in NUMERIC_SIGNALS:
        count = 0
        missing = 0
        nonfinite = 0
        zero = 0
        min_value: float | None = None
        max_value: float | None = None
        moments = _ScaledMoments()
        reservoir: list[float] = []
        rng = random.Random(f"{seed}:{sig}")
        for row in rows:
            value = row.get(sig)
            if value is None:
                missing += 1
                continue
            if isinstance(value, float) and not math.isfinite(value):
                nonfinite += 1
                continue
            value = float(value)
            count += 1
            if value == 0.0:
                zero += 1
            if min_value is None or value < min_value:
                min_value = value
            if max_value is None or value > max_value:
                max_value = value
            moments.update(value)
            if len(reservoir) < PER_MAP_RESERVOIR:
                reservoir.append(value)
            else:
                slot = rng.randrange(count)
                if slot < PER_MAP_RESERVOIR:
                    reservoir[slot] = value
        summaries[sig] = {
            **moments.snapshot(),
            "missing": missing,
            "nonfinite": nonfinite,
            "min": min_value,
            "max": max_value,
            "zero": zero,
            "reservoir": reservoir,
        }
    return summaries


def _validate_rows(rows: list[dict]) -> dict:
    schema_keys = set(SIGNAL_SCHEMA)
    unknown_key_count = 0
    missing_schema_key_count = 0
    nonfinite_count = 0
    original_ok = True
    time_sorted_ok = True
    provenance_ok = True
    extreme_finite: list[dict] = []
    blocked: list[dict] = []
    ranks: list[int] = []
    for index, row in enumerate(rows):
        unknown = set(row) - schema_keys
        unknown_key_count += len(unknown)
        missing_schema = schema_keys - set(row)
        missing_schema_key_count += len(missing_schema)
        if row.get("ls.original_index") != index:
            original_ok = False
        rank = row.get("ls.time_sorted_index")
        if isinstance(rank, int):
            ranks.append(rank)
        else:
            time_sorted_ok = False
        provenance = row.get("ls.provenance")
        if not isinstance(provenance, (tuple, list)) or not all(isinstance(p, str) for p in provenance):
            provenance_ok = False
        for flag in _blocked_provenance_flags(provenance):
            blocked.append(
                {
                    "object_index": index,
                    "flag": flag,
                    "affected_signals": list(BLOCKED_SLIDER_SIGNALS),
                }
            )
        for key, value in row.items():
            if isinstance(value, float) and not math.isfinite(value):
                nonfinite_count += 1
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                v = float(value)
                if math.isfinite(v) and abs(v) >= EXTREME_FINITE_ABS:
                    extreme_finite.append(
                        {
                            "signal": key,
                            "value": v,
                            "object_index": index,
                            "provenance": list(provenance) if isinstance(provenance, (tuple, list)) else [],
                        }
                    )
    if len(ranks) == len(rows) and sorted(ranks) != list(range(len(rows))):
        time_sorted_ok = False
    extreme_finite.sort(key=lambda e: (-abs(e["value"]), e["signal"], e["object_index"]))
    return {
        "unknown_key_count": unknown_key_count,
        "missing_schema_key_count": missing_schema_key_count,
        "nonfinite_count": nonfinite_count,
        "original_order_ok": original_ok,
        "time_sorted_ok": time_sorted_ok,
        "provenance_ok": provenance_ok,
        "extreme_finite_count": len(extreme_finite),
        "extreme_finite_samples": extreme_finite[:10],
        "geometry_blocked_count": len(blocked),
        "geometry_blocked_samples": blocked[:50],
    }


def _validate_segments(rows: list[dict], segments: list[dict]) -> dict:
    n = len(rows)
    total_objects = sum(int(seg.get("object_count") or 0) for seg in segments)
    covered = total_objects == n
    consistent = True
    nonfinite_aggregates = 0
    aggregate_consistency_failures = 0
    prev_end = None
    for seg in segments:
        start_idx = int(seg.get("start_idx") or 0)
        end_idx = int(seg.get("end_idx") or 0)
        if not (0 <= start_idx < end_idx <= n):
            consistent = False
        if prev_end is not None and start_idx != prev_end:
            consistent = False
        prev_end = end_idx
        aggregates = seg.get("aggregates") or {}
        for key, agg in aggregates.items():
            for field in ("mean", "p90", "max"):
                value = agg.get(field)
                if isinstance(value, float) and not math.isfinite(value):
                    nonfinite_aggregates += 1
            if "max" in agg and "p90" in agg:
                mx = agg.get("max")
                p90 = agg.get("p90")
                if isinstance(mx, (int, float)) and isinstance(p90, (int, float)):
                    scale = max(1.0, abs(float(mx)), abs(float(p90)))
                    if float(mx) + 1e-12 * scale < float(p90):
                        consistent = False
                        aggregate_consistency_failures += 1
    return {
        "segment_consistent": consistent and covered,
        "coverage_consistent": covered,
        "aggregate_nonfinite_count": nonfinite_aggregates,
        "aggregate_consistency_failures": aggregate_consistency_failures,
    }


def _process_map(rec: dict, store_objects: bool, seed: int) -> dict:
    abs_path = os.path.join(rec.get("root") or "", rec["path"])
    out: dict[str, Any] = {
        "sample_id": rec["sample_id"],
        "path": rec["path"],
        "path_abs": abs_path,
        "checksum": rec["checksum"],
        "format_version": rec["format_version"],
        "local_set_group": rec["local_set_group"],
        "flags": rec["flags"],
        "ok": False,
        "error_type": None,
        "error": None,
        "latency_ms": None,
        "parse_latency_ms": None,
        "feature_latency_ms": None,
        "signal_latency_ms": None,
        "feature_count": None,
        "feature_serializable": None,
        "feature_nonfinite_count": None,
        "object_count": rec["object_count"],
        "duration_ms": rec["duration_ms"],
        "bpm_max": rec["bpm_max"],
        "ar": rec["ar"],
        "od": rec["od"],
        "cs": rec["cs"],
        "slider_ratio": rec["slider_ratio"],
        "timing_count": rec["timing_count"],
        "green_count": rec["green_count"],
        "signal_version": SIGNAL_VERSION,
        "feature_version": FEATURE_VERSION,
        "objects": None,
        "signal_summaries": None,
        "slider_count": None,
        "nested_count": None,
        "segment_count": None,
        "objects_per_segment": None,
        "duration_per_segment": None,
        "empty_segments": None,
        "short_lt100": None,
        "short_lt1000": None,
        "validation": None,
        "serializable": None,
    }
    t0 = time.perf_counter()
    try:
        beatmap = parse_osu_file(abs_path)
        out["parse_latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)

        t1 = time.perf_counter()
        nmap = normalize(beatmap)
        features = FeatureExtractor().extract(nmap)
        out["feature_latency_ms"] = round((time.perf_counter() - t1) * 1000, 3)
        out["feature_count"] = len(features)
        if len(features) != EXPECTED_FEATURE_COUNT:
            out["error_type"] = "FeatureCountMismatch"
            out["error"] = f"expected {EXPECTED_FEATURE_COUNT} Feature {FEATURE_VERSION} fields, got {len(features)}"
            out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
            return out
        try:
            json.dumps(features, ensure_ascii=False, allow_nan=False)
            out["feature_serializable"] = True
        except (TypeError, ValueError):
            out["feature_serializable"] = False
        out["feature_nonfinite_count"] = sum(
            1 for value in features.values() if isinstance(value, float) and not math.isfinite(value)
        )

        t2 = time.perf_counter()
        extractor = LocalSignalExtractor()
        local = extractor.extract(beatmap)
        rows = local["objects"]
        segments = local["segments"]
        validation = _validate_rows(rows)
        segment_validation = _validate_segments(rows, segments)
        validation.update(segment_validation)
        out["signal_latency_ms"] = round((time.perf_counter() - t2) * 1000, 3)
        out["validation"] = validation

        seg_counts = [int(seg.get("object_count") or 0) for seg in segments]
        seg_durations = [max(0.0, float(seg.get("end_ms") or 0.0) - float(seg.get("start_ms") or 0.0)) for seg in segments]
        out["segment_count"] = len(segments)
        out["objects_per_segment"] = {
            "min": min(seg_counts) if seg_counts else None,
            "max": max(seg_counts) if seg_counts else None,
            "mean": round(statistics.fmean(seg_counts), 4) if seg_counts else None,
        }
        out["duration_per_segment"] = {
            "min": min(seg_durations) if seg_durations else None,
            "max": max(seg_durations) if seg_durations else None,
            "mean": round(statistics.fmean(seg_durations), 4) if seg_durations else None,
        }
        out["empty_segments"] = sum(1 for c in seg_counts if c == 0)
        out["short_lt100"] = sum(1 for d in seg_durations if d < 100.0)
        out["short_lt1000"] = sum(1 for d in seg_durations if d < 1000.0)

        if store_objects:
            out["objects"] = rows
        else:
            out["signal_summaries"] = _map_signal_summaries(rows, seed)
        out["slider_count"] = sum(1 for row in rows if row.get("ls.object_type") == "slider")
        nested_values = [row.get("ls.slider_nested_object_count") for row in rows]
        out["nested_count"] = (
            sum(int(v) for v in nested_values if isinstance(v, (int, float)))
            if any(isinstance(v, (int, float)) for v in nested_values)
            else None
        )
        try:
            json.dumps(local, ensure_ascii=False, allow_nan=False)
            out["serializable"] = True
        except (TypeError, ValueError):
            out["serializable"] = False
        out["ok"] = True
    except Exception as exc:  # noqa: BLE001 - triage then fix
        out["error_type"] = type(exc).__name__
        out["error"] = str(exc)[:300]
    out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    return out


def _resume_record_complete(rec: dict, store_objects: bool) -> bool:
    validation = rec.get("validation")
    if store_objects:
        payload_ok = isinstance(rec.get("objects"), list)
    else:
        summaries = rec.get("signal_summaries")
        payload_ok = isinstance(summaries, dict) and all(
            isinstance(summary, dict) and summary.get("moments_version") == MOMENT_SCHEMA_VERSION
            for summary in summaries.values()
        )
    return (
        rec.get("ok") is True
        and rec.get("feature_version") == FEATURE_VERSION
        and rec.get("signal_version") == SIGNAL_VERSION
        and rec.get("feature_count") == EXPECTED_FEATURE_COUNT
        and rec.get("feature_serializable") is True
        and rec.get("feature_nonfinite_count") == 0
        and rec.get("serializable") is True
        and isinstance(validation, dict)
        and validation.get("unknown_key_count") == 0
        and validation.get("missing_schema_key_count") == 0
        and validation.get("nonfinite_count") == 0
        and validation.get("original_order_ok") is True
        and validation.get("time_sorted_ok") is True
        and validation.get("coverage_consistent") is True
        and validation.get("segment_consistent") is True
        and validation.get("aggregate_nonfinite_count") == 0
        and validation.get("aggregate_consistency_failures") == 0
        and payload_ok
    )


def _run_extraction(records: list[dict], out_path: Path, workers: int, resume: bool, store_objects: bool, seed: int) -> dict:
    done = _prepare_resume_records(
        out_path,
        resume,
        lambda rec: _resume_record_complete(rec, store_objects),
    )
    todo = [r for r in records if r["sample_id"] not in done]
    print(f"extract total={len(records)} done={len(done)} todo={len(todo)} workers={workers}", flush=True)
    if not todo:
        return {"ok": 0, "fail": 0, "elapsed_s": 0.0}
    start = time.time()
    ok_count = 0
    fail_count = 0
    mode = "a" if resume and done else "w"
    worker = functools.partial(_process_map, store_objects=store_objects, seed=seed)
    with out_path.open(mode, encoding="utf-8") as fh:
        import multiprocessing

        if workers <= 1:
            iterator = (worker(r) for r in todo)
        else:
            with multiprocessing.Pool(processes=workers, maxtasksperchild=200) as pool:
                iterator = pool.imap(worker, todo, chunksize=8)
                for idx, rec in enumerate(iterator, 1):
                    fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
                    if rec["ok"]:
                        ok_count += 1
                    else:
                        fail_count += 1
                    if idx % 2000 == 0:
                        print(
                            f"extract progress {idx}/{len(todo)} ok={ok_count} fail={fail_count} "
                            f"elapsed={time.time()-start:.1f}s",
                            flush=True,
                        )
                return {"ok": ok_count, "fail": fail_count, "elapsed_s": time.time() - start}
        for idx, rec in enumerate(iterator, 1):
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            if rec["ok"]:
                ok_count += 1
            else:
                fail_count += 1
            if idx % 2000 == 0:
                print(
                    f"extract progress {idx}/{len(todo)} ok={ok_count} fail={fail_count} "
                    f"elapsed={time.time()-start:.1f}s",
                    flush=True,
                )
    return {"ok": ok_count, "fail": fail_count, "elapsed_s": time.time() - start}


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def _log_log_slope(xs: list[float], ys: list[float]) -> dict | None:
    pairs = [
        (math.log(float(x)), math.log(float(y)))
        for x, y in zip(xs, ys)
        if x is not None and y is not None and float(x) > 0 and float(y) > 0 and math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    if len(pairs) < 100:
        return None
    lx = [p[0] for p in pairs]
    ly = [p[1] for p in pairs]
    n = len(lx)
    mx = sum(lx) / n
    my = sum(ly) / n
    num = 0.0
    den = 0.0
    for x, y in zip(lx, ly):
        ax = x - mx
        num += ax * (y - my)
        den += ax * ax
    slope = num / den if den else None
    r = _pearson(lx, ly)
    return {"slope": round(slope, 4) if slope is not None else None, "pearson": round(r, 4) if r is not None else None, "n": len(pairs)}


def _stats_pass(jsonl: Path, phase: str, exact: bool, seed: int) -> dict:
    rng = random.Random(seed)
    acc: dict[str, _LocalSignalAccumulator] = {sig: _LocalSignalAccumulator(exact, rng) for sig in NUMERIC_SIGNALS}
    core_acc: dict[str, _LocalSignalAccumulator] = {sig: _LocalSignalAccumulator(exact, rng) for sig in NUMERIC_SIGNALS}
    proxy_acc: dict[str, _StreamAccumulator] = {key: _StreamAccumulator(exact, rng) for key in PROXY_KEYS}
    feature_counts: Counter = Counter()
    segment_counts: list[float] = []
    seg_obj_means: list[float] = []
    seg_obj_max: list[float] = []
    seg_dur_means: list[float] = []
    seg_dur_max: list[float] = []
    total_empty = 0
    total_short_lt100 = 0
    total_short_lt1000 = 0
    total_segments = 0
    total_objects = 0
    coverage_fail = 0
    segment_consistency_fail = 0
    ordering_fail = 0
    segment_nonfinite_maps = 0
    serialize_fail = 0
    latency: list[float] = []
    parse_latency: list[float] = []
    signal_latency: list[float] = []
    slow_heap: list[tuple[float, int, dict]] = []
    failures: list[dict] = []
    records = 0
    ok_records = 0
    core_records = 0
    extreme_finite_total = 0
    geometry_blocked_maps = 0
    geometry_blocked_objects = 0
    exact_records: list[dict] = []
    scaling_x: dict[str, list[float]] = {key: [] for key in ("object_count", "slider_count", "nested_count", "segment_count")}
    scaling_y: list[float] = []

    with jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            records += 1
            if not rec["ok"]:
                failures.append(
                    {
                        "sample_id": rec["sample_id"],
                        "path": rec["path"],
                        "checksum": rec["checksum"],
                        "error_type": rec["error_type"],
                        "error": rec["error"],
                        "latency_ms": rec["latency_ms"],
                    }
                )
                continue
            ok_records += 1
            feature_counts[rec["feature_count"]] += 1
            latency.append(float(rec["latency_ms"]))
            parse_latency.append(float(rec["parse_latency_ms"] or 0.0))
            signal_latency.append(float(rec["signal_latency_ms"] or 0.0))
            heap_item = (float(rec["latency_ms"]), rec["sample_id"], rec)
            if len(slow_heap) < 50:
                heapq.heappush(slow_heap, heap_item)
            elif heap_item[0] > slow_heap[0][0]:
                heapq.heapreplace(slow_heap, heap_item)
            segment_counts.append(float(rec["segment_count"] or 0))
            ops = rec.get("objects_per_segment") or {}
            dps = rec.get("duration_per_segment") or {}
            if ops.get("mean") is not None:
                seg_obj_means.append(float(ops["mean"]))
            if ops.get("max") is not None:
                seg_obj_max.append(float(ops["max"]))
            if dps.get("mean") is not None:
                seg_dur_means.append(float(dps["mean"]))
            if dps.get("max") is not None:
                seg_dur_max.append(float(dps["max"]))
            total_empty += int(rec.get("empty_segments") or 0)
            total_short_lt100 += int(rec.get("short_lt100") or 0)
            total_short_lt1000 += int(rec.get("short_lt1000") or 0)
            total_segments += int(rec.get("segment_count") or 0)
            total_objects += int(rec.get("object_count") or 0)
            validation = rec.get("validation") or {}
            if not validation.get("coverage_consistent"):
                coverage_fail += 1
            if not validation.get("segment_consistent") or int(validation.get("aggregate_consistency_failures") or 0) > 0:
                segment_consistency_fail += 1
            if not validation.get("original_order_ok") or not validation.get("time_sorted_ok"):
                ordering_fail += 1
            if int(validation.get("aggregate_nonfinite_count") or 0) > 0:
                segment_nonfinite_maps += 1
            if not rec.get("serializable") or not rec.get("feature_serializable"):
                serialize_fail += 1
            extreme_finite_total += int(validation.get("extreme_finite_count") or 0)
            blocked_count = int(validation.get("geometry_blocked_count") or 0)
            if blocked_count > 0:
                geometry_blocked_maps += 1
            geometry_blocked_objects += blocked_count
            if not rec.get("flags"):
                core_records += 1
            for key in PROXY_KEYS:
                value = rec.get(key)
                if value is not None:
                    proxy_acc[key].update(float(value))
            objects = rec.get("objects")
            if blocked_count == 0 and objects is not None:
                # Older artifact runs stored the guard flags only on the
                # per-object rows, not in validation; fall back to row
                # provenance so exact counts are reported for every phase.
                for row in objects:
                    if _blocked_provenance_flags(row.get("ls.provenance")):
                        blocked_count += 1
                if blocked_count > 0:
                    geometry_blocked_maps += 1
                geometry_blocked_objects += blocked_count
            signal_summaries = rec.get("signal_summaries")
            if objects is not None:
                for row in objects:
                    for sig in NUMERIC_SIGNALS:
                        value = row.get(sig)
                        acc[sig].update(value)
                        if not rec.get("flags"):
                            core_acc[sig].update(value)
            elif signal_summaries is not None:
                for sig, summary in signal_summaries.items():
                    acc[sig].merge_map_summary(summary)
                    if not rec.get("flags"):
                        core_acc[sig].merge_map_summary(summary)
            if exact and objects is not None:
                means = {sig: _mean_of_rows(objects, sig) for sig in NUMERIC_SIGNALS}
                exact_records.append(
                    {
                        "signal_means": means,
                        **{key: rec.get(key) for key in PROXY_KEYS},
                    }
                )
            scaling_y.append(float(rec["latency_ms"]))
            for key in scaling_x:
                value = rec.get(key)
                if value is None:
                    if key == "object_count":
                        value = rec.get("object_count")
                    elif key == "segment_count":
                        value = rec.get("segment_count")
                scaling_x[key].append(value)

    signal_stats = {sig: acc[sig].finish() for sig in sorted(acc)}
    core_stats = {sig: core_acc[sig].finish() for sig in sorted(core_acc)}
    proxy_stats = {key: proxy_acc[key].finish() for key in sorted(proxy_acc)}
    correlations = _correlate(exact_records) if exact else {
        "signal_pairs": [],
        "proxy": [],
        "note": "correlations computed exactly on the deterministic 5k/20k object-level phases",
    }
    slow_maps = [heapq.heappop(slow_heap)[2] for _ in range(len(slow_heap))]
    slow_maps.sort(key=lambda r: -float(r["latency_ms"]))
    scaling: dict[str, dict | None] = {}
    for key, xs in scaling_x.items():
        scaling[key] = _log_log_slope(xs, scaling_y)
    return {
        "phase": phase,
        "feature_version": FEATURE_VERSION,
        "signal_version": SIGNAL_VERSION,
        "records": records,
        "ok": ok_records,
        "failures": len(failures),
        "failure_detail": failures,
        "feature_count_distribution": dict(feature_counts),
        "signal_stats": signal_stats,
        "signal_stats_core": core_stats,
        "core_records": core_records,
        "proxy_stats": proxy_stats,
        "correlation": correlations,
        "extreme_finite_total": extreme_finite_total,
        "geometry_blocked_maps": geometry_blocked_maps,
        "geometry_blocked_objects": geometry_blocked_objects,
        "segment": {
            "segments_per_map": _dist_summary(segment_counts),
            "objects_per_segment_mean": _dist_summary(seg_obj_means),
            "objects_per_segment_max": _dist_summary(seg_obj_max),
            "duration_per_segment_mean_ms": _dist_summary(seg_dur_means),
            "duration_per_segment_max_ms": _dist_summary(seg_dur_max),
            "total_segments": total_segments,
            "total_objects": total_objects,
            "global_mean_objects_per_segment": round(total_objects / total_segments, 4) if total_segments else None,
            "empty_segments": total_empty,
            "short_segments_lt100ms": total_short_lt100,
            "short_segments_lt1000ms": total_short_lt1000,
            "coverage_consistency_failures": coverage_fail,
            "segment_consistency_failures": segment_consistency_fail,
            "ordering_failures": ordering_fail,
            "segment_aggregate_nonfinite_maps": segment_nonfinite_maps,
            "serialize_failures": serialize_fail,
        },
        "performance": {
            "latency_ms": _dist_summary(latency),
            "parse_latency_ms": _dist_summary(parse_latency),
            "signal_latency_ms": _dist_summary(signal_latency),
            "total_latency_sum_ms": round(sum(latency), 3),
            "scaling_log_log_slope": scaling,
            "slowest_50": [
                {
                    "sample_id": r["sample_id"],
                    "path": r["path"],
                    "checksum": r["checksum"],
                    "latency_ms": r["latency_ms"],
                    "object_count": r["object_count"],
                    "segment_count": r["segment_count"],
                    "flags": r["flags"],
                }
                for r in slow_maps
            ],
        },
    }


def _mean_of_rows(rows: list[dict], sig: str) -> float | None:
    values = [
        float(row[sig])
        for row in rows
        if row.get(sig) is not None and isinstance(row[sig], (int, float)) and math.isfinite(float(row[sig]))
    ]
    return statistics.fmean(values) if values else None


def _correlate(records: list[dict]) -> dict:
    keys = sorted(NUMERIC_SIGNALS)
    pairs: list[dict] = []
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            xs: list[float] = []
            ys: list[float] = []
            for rec in records:
                va = rec["signal_means"].get(a)
                vb = rec["signal_means"].get(b)
                if va is not None and vb is not None and math.isfinite(va) and math.isfinite(vb):
                    xs.append(va)
                    ys.append(vb)
            r = _pearson(xs, ys)
            if r is not None and abs(r) > 0.9:
                pairs.append({"signal_a": a, "signal_b": b, "pearson": round(r, 6), "n": len(xs)})
    proxies: list[dict] = []
    for sig in keys:
        for proxy in PROXY_KEYS:
            xs: list[float] = []
            ys: list[float] = []
            for rec in records:
                vs = rec["signal_means"].get(sig)
                vp = rec.get(proxy)
                if vs is not None and vp is not None and math.isfinite(vs) and vp is not None:
                    try:
                        vp = float(vp)
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(vp):
                        xs.append(vs)
                        ys.append(vp)
            r = _pearson(xs, ys)
            if r is not None and abs(r) > 0.9:
                proxies.append({"signal": sig, "proxy": proxy, "pearson": round(r, 6), "n": len(xs)})
    pairs.sort(key=lambda p: -abs(p["pearson"]))
    proxies.sort(key=lambda p: -abs(p["pearson"]))
    return {"signal_pairs": pairs, "proxy": proxies}


# ---------------------------------------------------------------------------
# outlier pass
# ---------------------------------------------------------------------------


def _outlier_pass(jsonl: Path, stats: dict, out_path: Path, store_objects: bool) -> dict:
    signal_stats = stats["signal_stats"]
    thresholds: dict[str, tuple[float | None, float | None]] = {}
    if store_objects:
        for key, st in signal_stats.items():
            lo = st.get("p0_1")
            hi = st.get("p99_9")
            mean = st.get("mean")
            std = st.get("std")
            limits = [lo, hi]
            if isinstance(mean, (int, float)) and isinstance(std, (int, float)) and std and std > 0:
                limits.append(mean - 12 * std)
                limits.append(mean + 12 * std)
            thresholds[key] = (
                min([v for v in limits if isinstance(v, (int, float))], default=None),
                max([v for v in limits if isinstance(v, (int, float))], default=None),
            )
    total = 0
    threshold_total = 0
    extreme_total = 0
    geometry_blocked_maps = 0
    geometry_blocked_objects = 0
    geometry_blocked_sample_lines = 0
    per_signal: Counter = Counter()
    per_extreme_signal: Counter = Counter()
    per_blocked_flag: Counter = Counter()
    with out_path.open("w", encoding="utf-8") as fh:
        with jsonl.open(encoding="utf-8") as src:
            for line in src:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if not rec["ok"]:
                    continue
                if store_objects:
                    rows = rec.get("objects") or []
                    for obj_index, row in enumerate(rows):
                        for key, value in row.items():
                            if key not in thresholds:
                                continue
                            if value is None or (isinstance(value, float) and not math.isfinite(value)):
                                continue
                            value = float(value)
                            lo, hi = thresholds.get(key, (None, None))
                            if (lo is not None and value < lo) or (hi is not None and value > hi):
                                fh.write(
                                    json.dumps(
                                        {
                                            "sample_id": rec["sample_id"],
                                            "path": rec["path"],
                                            "checksum": rec["checksum"],
                                            "signal": key,
                                            "value": value,
                                            "object_index": obj_index,
                                            "provenance": row.get("ls.provenance"),
                                            "flags": rec["flags"],
                                            "kind": "threshold",
                                        },
                                        ensure_ascii=False,
                                        sort_keys=True,
                                        allow_nan=False,
                                    )
                                    + "\n"
                                )
                                total += 1
                                threshold_total += 1
                                per_signal[key] += 1
                validation = rec.get("validation") or {}
                for sample in validation.get("extreme_finite_samples") or []:
                    fh.write(
                        json.dumps(
                            {
                                "sample_id": rec["sample_id"],
                                "path": rec["path"],
                                "checksum": rec["checksum"],
                                "signal": sample["signal"],
                                "value": sample["value"],
                                "object_index": sample["object_index"],
                                "provenance": sample["provenance"],
                                "flags": rec["flags"],
                                "kind": "extreme_finite",
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            allow_nan=False,
                        )
                        + "\n"
                    )
                    total += 1
                    extreme_total += 1
                    per_extreme_signal[sample["signal"]] += 1
                blocked_count = int(validation.get("geometry_blocked_count") or 0)
                blocked_samples = validation.get("geometry_blocked_samples") or []
                if store_objects and blocked_count == 0:
                    # Older artifact runs have no blocked sample list in
                    # validation; derive both the exact count and a bounded
                    # sample list (50 per map, matching the standard policy)
                    # from per-object provenance.
                    per_map: list[dict] = []
                    rows = rec.get("objects") or []
                    for obj_index, row in enumerate(rows):
                        blocked_flags = _blocked_provenance_flags(row.get("ls.provenance"))
                        if blocked_flags:
                            blocked_count += 1
                            per_map.append(
                                {
                                    "object_index": obj_index,
                                    "flag": blocked_flags[0],
                                    "affected_signals": list(BLOCKED_SLIDER_SIGNALS),
                                }
                            )
                    blocked_samples = per_map[:50]
                if blocked_count > 0:
                    geometry_blocked_maps += 1
                geometry_blocked_objects += blocked_count
                for sample in blocked_samples:
                    fh.write(
                        json.dumps(
                            {
                                "sample_id": rec["sample_id"],
                                "path": rec["path"],
                                "checksum": rec["checksum"],
                                "signal": sample["affected_signals"],
                                "value": None,
                                "object_index": sample["object_index"],
                                "provenance": [sample["flag"]],
                                "flags": rec["flags"],
                                "kind": "geometry_blocked",
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            allow_nan=False,
                        )
                        + "\n"
                    )
                    total += 1
                    geometry_blocked_sample_lines += 1
                    per_blocked_flag[sample["flag"]] += 1
    return {
        "outlier_records": total,
        "threshold_records": threshold_total,
        "extreme_finite_records": extreme_total,
        "geometry_blocked_records": geometry_blocked_objects,
        "geometry_blocked_maps": geometry_blocked_maps,
        "geometry_blocked_sample_lines": geometry_blocked_sample_lines,
        "by_signal_top": per_signal.most_common(20),
        "by_extreme_signal_top": per_extreme_signal.most_common(20),
        "by_blocked_flag": per_blocked_flag.most_common(20),
        "mode": "objects" if store_objects else "per-map-summaries-only",
    }


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _fmt(x: Any) -> str:
    if x is None:
        return "null"
    if isinstance(x, float):
        return f"{x:g}"
    return str(x)


def _verdict(result: dict) -> tuple[str, str]:
    reasons: list[str] = []
    if result["failures"] > 0:
        reasons.append(f"{result['failures']} extraction failures")
    if result["feature_count_distribution"] and any(int(k) != EXPECTED_FEATURE_COUNT for k in result["feature_count_distribution"]):
        reasons.append(f"Feature {FEATURE_VERSION} count != {EXPECTED_FEATURE_COUNT}")
    nonfinite = [k for k, st in result["signal_stats"].items() if st["nonfinite"] > 0]
    if nonfinite:
        reasons.append(f"output NaN/Inf in {len(nonfinite)} signals")
    seg = result["segment"]
    if seg["coverage_consistency_failures"]:
        reasons.append(f"{seg['coverage_consistency_failures']} segment coverage failures")
    if seg["segment_consistency_failures"]:
        reasons.append(f"{seg['segment_consistency_failures']} segment aggregate consistency failures")
    if seg["ordering_failures"]:
        reasons.append(f"{seg['ordering_failures']} ordering failures")
    if seg["segment_aggregate_nonfinite_maps"]:
        reasons.append("non-finite segment aggregates")
    if seg["serialize_failures"]:
        reasons.append("serialization failures")
    if result["failures"] and result["failures"] / max(1, result["records"]) > 0.001:
        reasons.append("failure rate > 0.1%")
    if reasons:
        return "BLOCKED", "; ".join(reasons)
    return "PASS", "no NaN/Inf, no serialization/ordering/coverage failures, corrected version provenance recorded, signal stats stable"


def _write_report(out_dir: Path, selection_meta: dict, phase_results: dict[str, dict], outlier_summaries: dict[str, dict]) -> None:
    lines: list[str] = []
    lines.append(f"# Local Signal Layer {SIGNAL_VERSION} QA Report")
    lines.append("")
    lines.append(f"- generated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}")
    lines.append(f"- signal_version: {SIGNAL_VERSION}")
    lines.append(f"- feature_version: {FEATURE_VERSION}")
    lines.append(f"- seed: {selection_meta.get('seed')}")
    lines.append(f"- manifest_total: {selection_meta.get('manifest_total')}")
    lines.append(f"- eligible: {selection_meta.get('eligible')} (known-broken excluded: {selection_meta.get('known_broken_excluded')})")
    lines.append(f"- pathological flagged: {selection_meta.get('pathological_count')}, aspire-like: {selection_meta.get('aspire_like_count')}")
    lines.append("")
    lines.append("> `mtime_year` is NOT treated as map creation year; `format_version` is only a format-generation proxy.")
    lines.append("> Full-phase percentiles/near-constant/unique are estimated from a deterministic per-signal reservoir;")
    lines.append("> count/missing/nonfinite/min/max/mean/std/zero_rate are exact in every phase. 5k/20k statistics are exact object-level.")
    lines.append("")
    for phase in ("5k", "20k", "full"):
        result = phase_results.get(phase)
        if not result:
            continue
        lines.append(f"## Phase {phase}")
        lines.append("")
        lines.append(f"- records: {result['records']}, ok: {result['ok']}, failures: {result['failures']}")
        lines.append(f"- Feature {FEATURE_VERSION} count distribution: {result['feature_count_distribution']}")
        lines.append(f"- core (non-pathological/non-aspire) records: {result.get('core_records')}")
        core_nonfinite = [k for k, st in result.get("signal_stats_core", {}).items() if st["nonfinite"] > 0]
        lines.append(f"- core signals with output NaN/Inf: {len(core_nonfinite)} {core_nonfinite[:5]}")
        nonfinite_signals = [k for k, st in result["signal_stats"].items() if st["nonfinite"] > 0]
        lines.append(f"- signals with output NaN/Inf: {len(nonfinite_signals)} {nonfinite_signals[:10]}")
        missing_high = sorted(
            ((k, st["missing_rate"]) for k, st in result["signal_stats"].items() if st["missing_rate"] > 0.5),
            key=lambda item: -item[1],
        )[:10]
        lines.append(f"- signals with missing_rate>0.5: {missing_high}")
        near_const = sorted(
            ((k, st["near_constant_rate"]) for k, st in result["signal_stats"].items() if st["near_constant_rate"] >= 0.999),
            key=lambda item: -item[1],
        )[:10]
        lines.append(f"- near-constant signals (>=0.999): {near_const}")
        lines.append(f"- extreme finite object values (|v|>=1e12): {result.get('extreme_finite_total')} (provenance-tagged, not clipped)")
        lines.append(
            f"- geometry-blocked sliders (path/spans/tick guards): {result.get('geometry_blocked_maps')} maps, "
            f"{result.get('geometry_blocked_objects')} objects (missing semantics + provenance, never fabricated)"
        )
        pairs = result["correlation"]["signal_pairs"]
        strong = [p for p in pairs if abs(p["pearson"]) > 0.98]
        lines.append(f"- signal-mean pairs |r|>0.98: {len(strong)}")
        for p in strong[:15]:
            lines.append(f"  - {p['signal_a']} ~ {p['signal_b']}: r={p['pearson']} n={p['n']}")
        proxy_strong = [p for p in result["correlation"]["proxy"] if abs(p["pearson"]) > 0.95]
        lines.append(f"- signal-mean ~ proxy correlations |r|>0.95: {len(proxy_strong)}")
        for p in proxy_strong[:15]:
            lines.append(f"  - {p['signal']} ~ {p['proxy']}: r={p['pearson']} n={p['n']}")
        if result["failures"]:
            lines.append("- failures:")
            for f in result["failure_detail"][:25]:
                lines.append(f"  - {f['sample_id']} | {f['error_type']}: {f['error']}")
        seg = result["segment"]
        lines.append(f"- segments: {json.dumps(seg, ensure_ascii=False)}")
        perf = result["performance"]
        lines.append(f"- latency_ms: {json.dumps(perf['latency_ms'], ensure_ascii=False)}")
        lines.append(f"- log-log latency scaling slope: {json.dumps(perf.get('scaling_log_log_slope'), ensure_ascii=False)}")
        if perf.get("maps_per_sec") is not None:
            lines.append(
                f"- extraction: elapsed_s={perf.get('extract_elapsed_s')}, maps_per_sec={perf.get('maps_per_sec')}"
            )
        lines.append(f"- slowest: {json.dumps(perf['slowest_50'][:3], ensure_ascii=False)}")
        if phase in outlier_summaries:
            lines.append(f"- outliers: {json.dumps(outlier_summaries[phase], ensure_ascii=False)}")
        lines.append("")
        verdict = _verdict(result)
        lines.append(f"**Verdict: {verdict[0]}** - {verdict[1]}")
        lines.append("")
    Path(out_dir / "LOCAL_SIGNAL_QA_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_phase_outputs(out_dir: Path, phase: str, result: dict, outlier: dict) -> None:
    suffix = phase if phase != "full" else ""
    (out_dir / f"local_signal_stats_{phase}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    corr_path = out_dir / ("local_signal_correlations.json" if phase == "full" else f"local_signal_correlations_{phase}.json")
    corr_path.write_text(json.dumps(result["correlation"], ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (out_dir / ("local_signal_segment_stats.json" if phase == "full" else f"local_signal_segment_stats_{phase}.json")).write_text(
        json.dumps(result["segment"], ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    slow_path = out_dir / ("local_signal_slow_maps.jsonl" if phase == "full" else f"local_signal_slow_maps_{phase}.jsonl")
    with slow_path.open("w", encoding="utf-8") as fh:
        for rec in result["performance"]["slowest_50"]:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    (out_dir / f"outlier_summary_{phase}.json").write_text(
        json.dumps(outlier, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def run_phase(
    phase: str,
    manifest_path: Path,
    scan_path: Path,
    failures_path: Path,
    root: str,
    out_dir: Path,
    seed: int,
    workers: int,
    resume: bool,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ordered_full, ordered_sample, selection_meta = build_selection(manifest_path, scan_path, failures_path, seed)
    records = ordered_full if phase == "full" else ordered_sample[: {"5k": 5000, "20k": 20000}[phase]]
    for rec in records:
        rec["root"] = root
    print(
        f"selection phase={phase} size={len(records)} pathological={sum(1 for r in records if r['pathological'])} "
        f"aspire={sum(1 for r in records if 'aspire_like' in r['flags'])} sets={len({r['local_set_group'] for r in records})}",
        flush=True,
    )
    (out_dir / f"selection_{phase}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True, allow_nan=False) for r in records) + "\n",
        encoding="utf-8",
    )
    store_objects = phase in EXACT_PHASES
    jsonl = out_dir / f"local_signal_qa_{phase}.jsonl"
    extract_summary = _run_extraction(records, jsonl, workers, resume, store_objects, seed)
    print(f"extraction summary: {extract_summary}", flush=True)
    result = _stats_pass(jsonl, phase, phase in EXACT_PHASES, seed)
    if phase == "full":
        corr_20k = out_dir / "local_signal_correlations_20k.json"
        if corr_20k.exists():
            result["correlation"] = json.loads(corr_20k.read_text(encoding="utf-8"))
            result["correlation"]["note"] = "computed exactly on the deterministic 20k nested subset (Phase D)"
    result["performance"]["extract_elapsed_s"] = round(extract_summary["elapsed_s"], 3)
    result["performance"]["maps_per_sec"] = (
        round(result["ok"] / extract_summary["elapsed_s"], 3) if extract_summary["elapsed_s"] else None
    )
    outlier_path = out_dir / ("local_signal_outliers.jsonl" if phase == "full" else f"local_signal_outliers_{phase}.jsonl")
    outlier_summary = _outlier_pass(jsonl, result, outlier_path, store_objects)
    _write_phase_outputs(out_dir, phase, result, outlier_summary)
    phase_results: dict[str, dict] = {}
    for other in ("5k", "20k", "full"):
        stats_path = out_dir / f"local_signal_stats_{other}.json"
        if stats_path.exists():
            phase_results[other] = json.loads(stats_path.read_text(encoding="utf-8"))
    if phase == "full":
        phase_results["full"] = result
    outlier_summaries: dict[str, dict] = {}
    for other in ("5k", "20k", "full"):
        summary_path = out_dir / f"outlier_summary_{other}.json"
        if summary_path.exists():
            outlier_summaries[other] = json.loads(summary_path.read_text(encoding="utf-8"))
    _write_report(out_dir, selection_meta, phase_results, outlier_summaries)
    verdict = _verdict(result)
    print(f"PHASE_{phase.upper()}_VERDICT={verdict[0]}: {verdict[1]}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local_signal_qa", description=__doc__)
    parser.add_argument("run", choices=["run"])
    parser.add_argument("--phase", choices=["5k", "20k", "full"], required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--scan", required=True)
    parser.add_argument("--failures", default=None)
    parser.add_argument("--root", required=True, help="Songs root directory for relative manifest references")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=min(2, (os.cpu_count() or 2)))
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")
    manifest = Path(args.manifest)
    failures = Path(args.failures) if args.failures else manifest.with_name("std_manifest.failures.jsonl")
    run_phase(
        args.phase,
        manifest,
        Path(args.scan),
        failures,
        args.root,
        Path(args.out_dir),
        args.seed,
        args.workers,
        args.resume,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
