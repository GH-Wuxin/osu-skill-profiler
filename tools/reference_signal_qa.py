"""Corrected Reference Signal Layer corpus QA (Gates C/D/E + Segment QA).

Phases (gated, deterministic):

  C  5k   stratified real-corpus QA over 5,000 maps (exact object rows)
  D  20k  nested expansion to 20,000 maps (exact object rows)
  E  full all eligible manifest maps, streaming/online statistics

Every map runs:

  parse -> normalise -> corrected Feature contract
                     -> corrected Local Signal contract
                     -> corrected Reference Signal contract
                     -> object alignment
                     -> fixed-time 5s reference segment summaries

The tool also performs the Segment Signal QA analyses on the exact 5k phase:
segment information preservation, reference/local correlations, upper-tail
overlap, and neutral REFERENCE-DISAGREEMENT CANDIDATES.  No skill labels,
no taxonomy, no final segment difficulty scalar, no model training.
"""

from __future__ import annotations

import argparse
import bisect
import functools
import heapq
import json
import math
import multiprocessing
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
from osu_skill_profiler.reference.ppy.contract import (  # noqa: E402
    REFERENCE_NUMERIC_SIGNALS,
    REFERENCE_SCHEMA,
    REFERENCE_VERSION,
)
from osu_skill_profiler.reference.ppy.extractor import ReferenceSignalExtractor, segment_reference_signals  # noqa: E402
from osu_skill_profiler.signals.contract import (  # noqa: E402
    NUMERIC_SIGNALS as LS_NUMERIC_SIGNALS,
    SIGNAL_VERSION,
)
from osu_skill_profiler.signals.extractor import LocalSignalExtractor  # noqa: E402

EXPECTED_FEATURE_COUNT = len(FEATURE_SCHEMA)
DEFAULT_SEED = 20260810
WINDOW_MS = 5000.0
EXTREME_FINITE_ABS = 1e12
PER_MAP_RESERVOIR = 256
MAX_EXACT_RECORDS_FULL = 20000
EXACT_PHASES = ("5k", "20k")
PROXY_KEYS = ("duration_ms", "object_count", "bpm_max", "format_version", "slider_ratio", "timing_count", "green_count", "ar", "od", "cs")
ANALYSIS_OBJECT_CAP_PER_MAP = 128
OBJECT_ANALYSIS_RESERVOIR = 300_000
CANDIDATE_TOP_PER_TYPE = 50
TAIL_QUANTILES = (0.95, 0.99)
EXTREME_TAIL_PROB = 0.995
ORDINARY_LO_PROB = 0.05
ORDINARY_HI_PROB = 0.95
LS_ANALYSIS_SIGNALS = (
    "ls.jump_distance_cs_normalised",
    "ls.lazy_jump_distance_cs_normalised",
    "ls.minimum_jump_distance_cs_normalised",
    "ls.travel_distance_cs_normalised",
    "ls.travel_time_ms",
    "ls.delta_time_ms",
    "ls.adjusted_delta_time_ms",
    "ls.minimum_jump_time_ms",
    "ls.preempt_ms",
    "ls.radius_px",
    "ls.slider_aware_angle_rad",
    "ls.double_tap_feasibility",
    "ls.slider_nested_object_count",
)


def _finite_number(value: Any) -> bool:
    """True for finite real numbers (bools are never numeric here)."""

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _blocked_provenance_flags(provenance) -> list[str]:
    if not isinstance(provenance, (tuple, list)):
        return []
    return [
        flag
        for flag in provenance
        if flag.startswith("path_blocked:")
        or flag.startswith("slider_spans_exceeded:")
        or flag == "slider_tick_count_exceeded"
    ]


class _RefAccumulator(_StreamAccumulator):
    """Stream accumulator that merges bounded per-map reference summaries."""

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


def _map_ref_summaries(rows: list[dict], seed: int) -> dict[str, dict]:
    summaries: dict[str, dict] = {}
    for sig in REFERENCE_NUMERIC_SIGNALS:
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


def _validate_rows(ref_rows: list[dict], ls_rows: list[dict]) -> dict:
    schema_keys = set(REFERENCE_SCHEMA)
    unknown_key_count = 0
    missing_schema_key_count = 0
    nonfinite_count = 0
    original_ok = True
    time_sorted_ok = True
    alignment_ok = True
    extreme_finite: list[dict] = []
    geometry_blocked: list[dict] = []
    unavailable_rows = 0
    ranks: list[int] = []
    if len(ref_rows) != len(ls_rows):
        alignment_ok = False
    for index, row in enumerate(ref_rows):
        unknown = set(row) - schema_keys
        unknown_key_count += len(unknown)
        missing_schema = schema_keys - set(row)
        missing_schema_key_count += len(missing_schema)
        if row.get("ref.original_index") != index:
            original_ok = False
        rank = row.get("ref.time_sorted_index")
        if isinstance(rank, int):
            ranks.append(rank)
        else:
            time_sorted_ok = False
        if index < len(ls_rows):
            ls_row = ls_rows[index]
            if (
                ls_row.get("ls.original_index") != row.get("ref.original_index")
                or abs(float(ls_row.get("ls.start_time_ms") or 0.0) - float(row.get("ref.start_time_ms") or 0.0)) > 1e-9
                or ls_row.get("ls.time_sorted_index") != row.get("ref.time_sorted_index")
            ):
                alignment_ok = False
        provenance = row.get("ref.provenance")
        if isinstance(provenance, (tuple, list)):
            if any(flag.startswith("ref_unavailable:") for flag in provenance):
                unavailable_rows += 1
            for flag in _blocked_provenance_flags(provenance):
                geometry_blocked.append({"object_index": index, "flag": flag})
        for signal in REFERENCE_NUMERIC_SIGNALS:
            value = row.get(signal)
            if isinstance(value, float) and not math.isfinite(value):
                nonfinite_count += 1
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                v = float(value)
                if math.isfinite(v) and abs(v) >= EXTREME_FINITE_ABS:
                    extreme_finite.append(
                        {
                            "signal": signal,
                            "value": v,
                            "object_index": index,
                            "provenance": list(provenance) if isinstance(provenance, (tuple, list)) else [],
                        }
                    )
    if len(ranks) == len(ref_rows) and sorted(ranks) != list(range(len(ref_rows))):
        time_sorted_ok = False
    extreme_finite.sort(key=lambda e: (-abs(e["value"]), e["signal"], e["object_index"]))
    return {
        "unknown_key_count": unknown_key_count,
        "missing_schema_key_count": missing_schema_key_count,
        "nonfinite_count": nonfinite_count,
        "original_order_ok": original_ok,
        "time_sorted_ok": time_sorted_ok,
        "alignment_ok": alignment_ok,
        "unavailable_rows": unavailable_rows,
        "extreme_finite_count": len(extreme_finite),
        "extreme_finite_samples": extreme_finite[:10],
        "geometry_blocked_count": len(geometry_blocked),
        "geometry_blocked_samples": geometry_blocked[:50],
    }


def _validate_segments(ref_rows: list[dict], segments: list[dict]) -> dict:
    n = len(ref_rows)
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
            for field in ("mean", "median", "p90", "p95", "max"):
                value = agg.get(field)
                if isinstance(value, float) and not math.isfinite(value):
                    nonfinite_aggregates += 1
            if all(isinstance(agg.get(f), (int, float)) for f in ("p90", "p95", "max")):
                scale = max(1.0, abs(agg["max"]), abs(agg["p95"]), abs(agg["p90"]))
                eps = 1e-12 * scale
                if not (agg["max"] + eps >= agg["p95"] and agg["p95"] + eps >= agg["p90"]):
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
        "ls_latency_ms": None,
        "ref_latency_ms": None,
        "feature_count": None,
        "feature_serializable": None,
        "object_count": rec["object_count"],
        "duration_ms": rec["duration_ms"],
        "bpm_max": rec["bpm_max"],
        "ar": rec["ar"],
        "od": rec["od"],
        "cs": rec["cs"],
        "slider_ratio": rec["slider_ratio"],
        "timing_count": rec["timing_count"],
        "green_count": rec["green_count"],
        "reference_version": REFERENCE_VERSION,
        "local_signal_version": SIGNAL_VERSION,
        "feature_version": FEATURE_VERSION,
        "objects": None,
        "ls_objects": None,
        "ref_summaries": None,
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

        t2 = time.perf_counter()
        ls_out = LocalSignalExtractor().extract(beatmap)
        ls_rows = ls_out["objects"]
        out["ls_latency_ms"] = round((time.perf_counter() - t2) * 1000, 3)

        t3 = time.perf_counter()
        ref_out = ReferenceSignalExtractor().extract(beatmap)
        ref_rows = ref_out["objects"]
        ref_segments = ref_out["segments"]
        out["ref_latency_ms"] = round((time.perf_counter() - t3) * 1000, 3)

        validation = _validate_rows(ref_rows, ls_rows)
        validation.update(_validate_segments(ref_rows, ref_segments))
        out["validation"] = validation

        seg_counts = [int(seg.get("object_count") or 0) for seg in ref_segments]
        seg_durations = [max(0.0, float(seg.get("end_ms") or 0.0) - float(seg.get("start_ms") or 0.0)) for seg in ref_segments]
        out["segment_count"] = len(ref_segments)
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
            out["objects"] = ref_rows
            out["ls_objects"] = ls_rows
            out["ls_means"] = _mean_of_rows(ls_rows, list(LS_NUMERIC_SIGNALS))
        else:
            out["ref_summaries"] = _map_ref_summaries(ref_rows, seed)
        out["slider_count"] = sum(1 for row in ref_rows if row.get("ref.object_type") == "slider")
        nested_values = [row.get("ls.slider_nested_object_count") for row in ls_rows]
        out["nested_count"] = (
            sum(int(v) for v in nested_values if isinstance(v, (int, float)))
            if any(isinstance(v, (int, float)) for v in nested_values)
            else None
        )
        try:
            json.dumps(ref_out, ensure_ascii=False, allow_nan=False)
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
        payload_ok = isinstance(rec.get("objects"), list) and isinstance(rec.get("ls_objects"), list)
    else:
        summaries = rec.get("ref_summaries")
        payload_ok = isinstance(summaries, dict) and all(
            isinstance(summary, dict) and summary.get("moments_version") == MOMENT_SCHEMA_VERSION
            for summary in summaries.values()
        )
    return (
        rec.get("ok") is True
        and rec.get("feature_version") == FEATURE_VERSION
        and rec.get("local_signal_version") == SIGNAL_VERSION
        and rec.get("reference_version") == REFERENCE_VERSION
        and rec.get("feature_count") == EXPECTED_FEATURE_COUNT
        and rec.get("feature_serializable") is True
        and rec.get("serializable") is True
        and isinstance(validation, dict)
        and validation.get("unknown_key_count") == 0
        and validation.get("missing_schema_key_count") == 0
        and validation.get("nonfinite_count") == 0
        and validation.get("original_order_ok") is True
        and validation.get("time_sorted_ok") is True
        and validation.get("alignment_ok") is True
        and validation.get("coverage_consistent") is True
        and validation.get("segment_consistent") is True
        and validation.get("aggregate_nonfinite_count") == 0
        and validation.get("aggregate_consistency_failures") == 0
        and payload_ok
    )


def _mean_of_rows(rows: list[dict], signals: list[str]) -> dict[str, float | None]:
    means: dict[str, float | None] = {}
    for sig in signals:
        values = [
            float(row[sig])
            for row in rows
            if row.get(sig) is not None and isinstance(row[sig], (int, float)) and math.isfinite(float(row[sig]))
        ]
        means[sig] = statistics.fmean(values) if values else None
    return means


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
                        print(f"extract progress {idx}/{len(todo)} ok={ok_count} fail={fail_count} elapsed={time.time()-start:.1f}s", flush=True)
                return {"ok": ok_count, "fail": fail_count, "elapsed_s": time.time() - start}
        for idx, rec in enumerate(iterator, 1):
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            if rec["ok"]:
                ok_count += 1
            else:
                fail_count += 1
            if idx % 2000 == 0:
                print(f"extract progress {idx}/{len(todo)} ok={ok_count} fail={fail_count} elapsed={time.time()-start:.1f}s", flush=True)
    return {"ok": ok_count, "fail": fail_count, "elapsed_s": time.time() - start}


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


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 30:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    rx = ranks(xs)
    ry = ranks(ys)
    return _pearson(rx, ry)


def _stats_pass(jsonl: Path, phase: str, exact: bool, seed: int) -> dict:
    rng = random.Random(seed)
    acc: dict[str, _RefAccumulator] = {sig: _RefAccumulator(exact, rng) for sig in REFERENCE_NUMERIC_SIGNALS}
    core_acc: dict[str, _RefAccumulator] = {sig: _RefAccumulator(exact, rng) for sig in REFERENCE_NUMERIC_SIGNALS}
    proxy_acc: dict[str, _StreamAccumulator] = {key: _StreamAccumulator(exact, rng) for key in PROXY_KEYS}
    feature_counts: Counter = Counter()
    segment_counts: list[float] = []
    total_empty = 0
    total_short_lt100 = 0
    total_short_lt1000 = 0
    total_segments = 0
    total_objects = 0
    consistency_fail = 0
    ordering_fail = 0
    alignment_fail = 0
    serialize_fail = 0
    latency: list[float] = []
    parse_latency: list[float] = []
    ref_latency: list[float] = []
    ls_latency: list[float] = []
    slow_heap: list[tuple[float, int, dict]] = []
    failures: list[dict] = []
    records = 0
    ok_records = 0
    core_records = 0
    geometry_blocked_maps = 0
    geometry_blocked_objects = 0
    unavailable_rows = 0
    extreme_finite_total = 0
    aggregate_nonfinite = 0
    aggregate_consistency_failures = 0
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
            ls_latency.append(float(rec["ls_latency_ms"] or 0.0))
            ref_latency.append(float(rec["ref_latency_ms"] or 0.0))
            heap_item = (float(rec["latency_ms"]), rec["sample_id"], rec)
            if len(slow_heap) < 50:
                heapq.heappush(slow_heap, heap_item)
            elif heap_item[0] > slow_heap[0][0]:
                heapq.heapreplace(slow_heap, heap_item)
            segment_counts.append(float(rec["segment_count"] or 0))
            total_empty += int(rec.get("empty_segments") or 0)
            total_short_lt100 += int(rec.get("short_lt100") or 0)
            total_short_lt1000 += int(rec.get("short_lt1000") or 0)
            total_segments += int(rec.get("segment_count") or 0)
            total_objects += int(rec.get("object_count") or 0)
            validation = rec.get("validation") or {}
            if not validation.get("coverage_consistent"):
                consistency_fail += 1
            if not validation.get("original_order_ok") or not validation.get("time_sorted_ok"):
                ordering_fail += 1
            if not validation.get("alignment_ok"):
                alignment_fail += 1
            if not rec.get("serializable") or not rec.get("feature_serializable"):
                serialize_fail += 1
            unavailable_rows += int(validation.get("unavailable_rows") or 0)
            extreme_finite_total += int(validation.get("extreme_finite_count") or 0)
            aggregate_nonfinite += int(validation.get("aggregate_nonfinite_count") or 0)
            aggregate_consistency_failures += int(validation.get("aggregate_consistency_failures") or 0)
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
            if objects is not None:
                for row in objects:
                    for sig in REFERENCE_NUMERIC_SIGNALS:
                        acc[sig].update(row.get(sig))
                        if not rec.get("flags"):
                            core_acc[sig].update(row.get(sig))
            elif rec.get("ref_summaries") is not None:
                for sig, summary in rec["ref_summaries"].items():
                    acc[sig].merge_map_summary(summary)
                    if not rec.get("flags"):
                        core_acc[sig].merge_map_summary(summary)
            if exact and objects is not None:
                exact_records.append(
                    {
                        "signal_means": _mean_of_rows(objects, list(REFERENCE_NUMERIC_SIGNALS)),
                        "ls_means": rec.get("ls_means"),
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
    correlation = _correlate_ref_ls(exact_records) if exact else {
        "map_level": [],
        "note": "correlations computed on the deterministic 5k/20k exact phases",
    }
    slow_maps = [heapq.heappop(slow_heap)[2] for _ in range(len(slow_heap))]
    slow_maps.sort(key=lambda r: -float(r["latency_ms"]))
    scaling: dict[str, dict | None] = {}
    for key, xs in scaling_x.items():
        scaling[key] = _log_log_slope(xs, scaling_y)
    return {
        "phase": phase,
        "feature_version": FEATURE_VERSION,
        "local_signal_version": SIGNAL_VERSION,
        "reference_version": REFERENCE_VERSION,
        "records": records,
        "ok": ok_records,
        "failures": len(failures),
        "failure_detail": failures,
        "feature_count_distribution": dict(feature_counts),
        "reference_stats": signal_stats,
        "reference_stats_core": core_stats,
        "core_records": core_records,
        "proxy_stats": proxy_stats,
        "correlation": correlation,
        "extreme_finite_total": extreme_finite_total,
        "geometry_blocked_maps": geometry_blocked_maps,
        "geometry_blocked_objects": geometry_blocked_objects,
        "unavailable_rows": unavailable_rows,
        "segment": {
            "segments_per_map": _dist_summary(segment_counts),
            "total_segments": total_segments,
            "total_objects": total_objects,
            "global_mean_objects_per_segment": round(total_objects / total_segments, 4) if total_segments else None,
            "empty_segments": total_empty,
            "short_segments_lt100ms": total_short_lt100,
            "short_segments_lt1000ms": total_short_lt1000,
            "coverage_consistency_failures": consistency_fail,
            "ordering_failures": ordering_fail,
            "alignment_failures": alignment_fail,
            "serialize_failures": serialize_fail,
            "aggregate_nonfinite_count": aggregate_nonfinite,
            "aggregate_consistency_failures": aggregate_consistency_failures,
        },
        "performance": {
            "latency_ms": _dist_summary(latency),
            "parse_latency_ms": _dist_summary(parse_latency),
            "ls_latency_ms": _dist_summary(ls_latency),
            "ref_latency_ms": _dist_summary(ref_latency),
            "total_latency_sum_ms": round(sum(latency), 3),
            "maps_per_second": round(len(latency) / max(sum(latency) / 1000.0, 1e-9), 4),
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


def _correlate_ref_ls(records: list[dict]) -> dict:
    ref_keys = list(REFERENCE_NUMERIC_SIGNALS)
    ls_keys = list(LS_NUMERIC_SIGNALS)
    rows: list[dict] = []
    for rec in records:
        rm = rec.get("signal_means") or {}
        lm = rec.get("ls_means") or {}
        if not rm or not lm:
            continue
        rows.append((rm, lm))
    pairs: list[dict] = []
    for ref_sig in ref_keys:
        for ls_sig in ls_keys:
            xs: list[float] = []
            ys: list[float] = []
            for rm, lm in rows:
                vx = rm.get(ref_sig)
                vy = lm.get(ls_sig)
                if vx is not None and vy is not None and math.isfinite(vx) and math.isfinite(vy):
                    xs.append(float(vx))
                    ys.append(float(vy))
            pearson = _pearson(xs, ys)
            spearman = _spearman(xs, ys)
            if pearson is not None and abs(pearson) > 0.5:
                pairs.append(
                    {
                        "reference_signal": ref_sig,
                        "local_signal": ls_sig,
                        "pearson": round(pearson, 6),
                        "spearman": round(spearman, 6) if spearman is not None else None,
                        "n": len(xs),
                    }
                )
    pairs.sort(key=lambda p: -abs(p["pearson"]))
    return {"map_level": pairs}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="std_manifest.json")
    parser.add_argument("--scan", type=Path, required=True, help="corpus_scan.jsonl")
    parser.add_argument("--failures", type=Path, default=None, help="std_manifest.failures.jsonl")
    parser.add_argument("--root", type=str, default="", help="corpus root prepended to relative paths")
    parser.add_argument("--out-dir", type=Path, default=Path("training/datasets/reference_signal_qa_v02"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--phase", choices=["5k", "20k", "full", "all"], default="all")
    args = parser.parse_args(argv)

    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")
    failures_path = args.failures or args.manifest.with_name("std_manifest.failures.jsonl")
    ordered_full, ordered_sample, selection_meta = build_selection(args.manifest, args.scan, failures_path, args.seed)
    if args.root:
        for rec in ordered_full:
            rec["root"] = args.root
        for rec in ordered_sample:
            rec["root"] = args.root
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stats_all: dict[str, Any] = {
        "feature_version": FEATURE_VERSION,
        "local_signal_version": SIGNAL_VERSION,
        "reference_version": REFERENCE_VERSION,
        "selection": selection_meta,
        "phases": {},
    }

    def run_phase(name: str, count: int, exact: bool, use_full: bool = False) -> bool:
        records = ordered_full if use_full else ordered_sample[:count]
        jsonl = args.out_dir / f"reference_qa_{name}.jsonl"
        result = _run_extraction(records, jsonl, args.workers, args.resume, exact, args.seed)
        stats = _stats_pass(jsonl, name, exact, args.seed)
        stats["extraction"] = result
        stats_all["phases"][name] = stats
        nonfinite_maps = sum(
            1
            for r in _iter_jsonl(jsonl)
            if r.get("ok") and int((r.get("validation") or {}).get("nonfinite_count") or 0) > 0
        )
        stats_all["phases"][name]["nonfinite_maps"] = nonfinite_maps
        ok = (
            result["fail"] == 0
            and stats["records"] >= count
            and stats["ok"] >= count
            and stats["segment"]["coverage_consistency_failures"] == 0
            and stats["segment"]["ordering_failures"] == 0
            and stats["segment"]["alignment_failures"] == 0
            and stats["segment"]["serialize_failures"] == 0
            and stats["segment"]["aggregate_nonfinite_count"] == 0
            and stats["segment"]["aggregate_consistency_failures"] == 0
            and nonfinite_maps == 0
        )
        print(f"[{name}] extraction={result} ok={ok} nonfinite_maps={nonfinite_maps}", flush=True)
        return ok

    if args.phase in ("5k", "all"):
        if not run_phase("5k", 5000, True):
            print("Gate C (5k) BLOCKED", flush=True)
            stats_all["verdict"] = "BLOCKED@5k"
            _write_stats(args, stats_all)
            return 1
    if args.phase in ("20k", "all"):
        if not run_phase("20k", 20000, True):
            print("Gate D (20k) BLOCKED", flush=True)
            stats_all["verdict"] = "BLOCKED@20k"
            _write_stats(args, stats_all)
            return 1
    if args.phase in ("full", "all"):
        if not run_phase("full", len(ordered_full), False, use_full=True):
            print("Gate E (full) BLOCKED", flush=True)
            stats_all["verdict"] = "BLOCKED@full"
            _write_stats(args, stats_all)
            return 1

    if args.phase in ("5k", "all"):
        analysis = _segment_analysis(args.out_dir / "reference_qa_5k.jsonl", args.seed)
        stats_all["segment_qa"] = analysis
        _write_segment_artifacts(args, analysis)
    stats_all["verdict"] = "PASS"
    _write_stats(args, stats_all)
    _write_report(args, stats_all)
    return 0


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _write_stats(args, stats_all: dict) -> None:
    with (args.out_dir / "reference_qa_stats.json").open("w", encoding="utf-8") as fh:
        json.dump(stats_all, fh, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)


def _segment_analysis(jsonl: Path, seed: int) -> dict:
    """Segment QA on the exact 5k phase (information preservation, tails,
    disagreement candidates)."""

    rng = random.Random(seed)
    per_signal_ratios: dict[str, list[float]] = {sig: [] for sig in REFERENCE_NUMERIC_SIGNALS}
    spike_preserved: Counter = Counter()
    tail_capture: dict[str, list[int]] = {sig: [0, 0] for sig in REFERENCE_NUMERIC_SIGNALS}
    seg_p95_ge_obj_p95: dict[str, list[int]] = {sig: [0, 0] for sig in REFERENCE_NUMERIC_SIGNALS}
    boundary_peak_objects = 0
    boundary_peak_total = 0
    sparse_segments = 0
    total_segments = 0
    sustained_maps = 0
    maps_with_segments = 0
    maps_analyzed = 0
    sampled_rows: list[tuple[dict, int, dict, dict | None, dict | None]] = []
    reservoir_seen = 0

    for rec in _iter_jsonl(jsonl):
        if not rec["ok"] or rec.get("objects") is None:
            continue
        rows = rec["objects"]
        ls_rows = rec.get("ls_objects") or []
        if len(rows) != len(ls_rows):
            continue
        segments = segment_reference_signals(rows, window_ms=WINDOW_MS)
        n = len(rows)
        if n == 0:
            continue
        if segments:
            maps_with_segments += 1
        maps_analyzed += 1
        seg_max: dict[str, list[float]] = {sig: [] for sig in REFERENCE_NUMERIC_SIGNALS}
        seg_p95: dict[str, list[float]] = {sig: [] for sig in REFERENCE_NUMERIC_SIGNALS}
        seg_by_time_index: dict[int, dict] = {}
        for seg in segments:
            total_segments += 1
            if int(seg.get("object_count") or 0) <= 2:
                sparse_segments += 1
            agg = seg.get("aggregates") or {}
            for pos in range(int(seg.get("start_idx") or 0), int(seg.get("end_idx") or 0)):
                seg_by_time_index[pos] = seg
            for sig in REFERENCE_NUMERIC_SIGNALS:
                mx = (agg.get(sig) or {}).get("max")
                if isinstance(mx, (int, float)):
                    seg_max[sig].append(float(mx))
                p95 = (agg.get(sig) or {}).get("p95")
                if isinstance(p95, (int, float)):
                    seg_p95[sig].append(float(p95))
        obj_values: dict[str, list[float]] = {sig: [] for sig in REFERENCE_NUMERIC_SIGNALS}
        for row in rows:
            for sig in REFERENCE_NUMERIC_SIGNALS:
                value = row.get(sig)
                if _finite_number(value):
                    obj_values[sig].append(float(value))
        boundaries: set[float] = set()
        for seg in segments:
            boundaries.add(float(seg["start_ms"]))
            boundaries.add(float(seg["end_ms"]))
        sustained = False
        for sig in REFERENCE_NUMERIC_SIGNALS:
            values = sorted(obj_values[sig])
            if not values:
                continue
            obj_max = values[-1]
            obj_p90 = _percentile(values, 0.90)
            obj_p95 = _percentile(values, 0.95)
            smax = max(seg_max[sig]) if seg_max[sig] else None
            if smax is not None and obj_max > 0:
                per_signal_ratios[sig].append(smax / obj_max)
                if abs(smax - obj_max) <= max(1e-9, abs(obj_max) * 1e-9):
                    spike_preserved[sig] += 1
            captured = 0
            total_tail = 0
            for row in rows:
                value = row.get(sig)
                if not _finite_number(value):
                    continue
                v = float(value)
                if v >= obj_p95:
                    total_tail += 1
                    seg = seg_by_time_index.get(int(row["ref.time_sorted_index"]))
                    seg_mx = None
                    if seg is not None:
                        seg_mx = ((seg.get("aggregates") or {}).get(sig) or {}).get("max")
                    if isinstance(seg_mx, (int, float)) and float(seg_mx) >= obj_p95:
                        captured += 1
                if v >= obj_p90:
                    boundary_peak_total += 1
                    start = float(row["ref.start_time_ms"])
                    near_boundary = any(abs(start - b) <= 250.0 for b in boundaries)
                    if near_boundary:
                        boundary_peak_objects += 1
            tail_capture[sig][0] += captured
            tail_capture[sig][1] += total_tail
            if seg_p95[sig]:
                seg_p95_ge_obj_p95[sig][0] += sum(1 for p in seg_p95[sig] if p >= obj_p95)
                seg_p95_ge_obj_p95[sig][1] += len(seg_p95[sig])
            tail_segments = [m for m in seg_max[sig] if m is not None and m >= obj_p95]
            if len(tail_segments) >= 2:
                sustained = True
        if sustained:
            sustained_maps += 1

        # deterministic bounded object sample for correlation/tail/disagreement
        stride = max(1, n // ANALYSIS_OBJECT_CAP_PER_MAP)
        for idx in range(0, n, stride):
            ref_row = rows[idx]
            ls_row = ls_rows[idx] if idx < len(ls_rows) else None
            seg = seg_by_time_index.get(int(ref_row["ref.time_sorted_index"]))
            if reservoir_seen < OBJECT_ANALYSIS_RESERVOIR:
                sampled_rows.append((rec, idx, ref_row, ls_row, seg))
            else:
                slot = rng.randrange(reservoir_seen)
                if slot < OBJECT_ANALYSIS_RESERVOIR:
                    sampled_rows[slot] = (rec, idx, ref_row, ls_row, seg)
            reservoir_seen += 1

    tail_overlap = _tail_overlap(sampled_rows, seed)
    disagreement = _disagreement_candidates(sampled_rows, seed)
    boundary_rate = boundary_peak_objects / boundary_peak_total if boundary_peak_total else None
    return {
        "seed": seed,
        "maps_analyzed": maps_analyzed,
        "maps_with_segments": maps_with_segments,
        "total_segments": total_segments,
        "sparse_segments": sparse_segments,
        "sparse_segment_rate": round(sparse_segments / total_segments, 6) if total_segments else None,
        "boundary_peak_rate": round(boundary_rate, 6) if boundary_rate is not None else None,
        "boundary_peak_objects": boundary_peak_objects,
        "boundary_peak_total": boundary_peak_total,
        "sustained_peak_maps": sustained_maps,
        "sampled_object_rows": len(sampled_rows),
        "sampled_object_rows_seen": reservoir_seen,
        "segment_max_to_object_max_ratio": {
            sig: _dist_summary(vals) if vals else {"count": 0}
            for sig, vals in per_signal_ratios.items()
        },
        "spike_preserved_maps": dict(spike_preserved),
        "upper_tail_segment_capture": {
            sig: {
                "captured": tail_capture[sig][0],
                "tail_objects": tail_capture[sig][1],
                "capture_rate": round(tail_capture[sig][0] / tail_capture[sig][1], 6)
                if tail_capture[sig][1]
                else None,
            }
            for sig in REFERENCE_NUMERIC_SIGNALS
        },
        "segment_p95_ge_object_p95": {
            sig: {
                "segments": seg_p95_ge_obj_p95[sig][1],
                "retained": seg_p95_ge_obj_p95[sig][0],
                "retention_rate": round(seg_p95_ge_obj_p95[sig][0] / seg_p95_ge_obj_p95[sig][1], 6)
                if seg_p95_ge_obj_p95[sig][1]
                else None,
            }
            for sig in REFERENCE_NUMERIC_SIGNALS
        },
        "tail_overlap": tail_overlap,
        "disagreement": disagreement["summary"],
        "disagreement_candidates": disagreement["candidates"],
        "candidate_count": {
            "type_a": len(disagreement["candidates"].get("A", [])),
            "type_b": len(disagreement["candidates"].get("B", [])),
        },
    }


def _tail_overlap(
    sampled_rows: list[tuple[dict, int, dict, dict | None, dict | None]],
    seed: int,
) -> dict:
    """Upper-tail overlap between each ref signal and its natural ls partner."""

    partners = {
        "ref.ppy.snap_include_sliders": "ls.lazy_jump_distance_cs_normalised",
        "ref.ppy.snap_exclude_sliders": "ls.jump_distance_cs_normalised",
        "ref.ppy.agility": "ls.lazy_jump_distance_cs_normalised",
        "ref.ppy.flow_include_sliders": "ls.lazy_jump_distance_cs_normalised",
        "ref.ppy.flow_exclude_sliders": "ls.jump_distance_cs_normalised",
        "ref.ppy.speed": "ls.adjusted_delta_time_ms",
        "ref.ppy.rhythm": "ls.delta_time_ms",
        "ref.ppy.speed_with_rhythm": "ls.adjusted_delta_time_ms",
        "ref.ppy.reading": "ls.preempt_ms",
    }
    data: dict[str, list[tuple[float, float]]] = {ref_sig: [] for ref_sig in partners}
    for _rec, _idx, ref_row, ls_row, _seg in sampled_rows:
        if ls_row is None:
            continue
        for ref_sig, ls_sig in partners.items():
            rv = ref_row.get(ref_sig)
            lv = ls_row.get(ls_sig)
            if _finite_number(rv) and _finite_number(lv):
                data[ref_sig].append((float(rv), float(lv)))
    out: dict[str, dict] = {}
    for ref_sig, pairs in data.items():
        if not pairs:
            continue
        ls_sig = partners[ref_sig]
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        entry: dict[str, Any] = {
            "local_signal": ls_sig,
            "n": len(pairs),
            "pearson": _pearson(xs, ys),
            "spearman": _spearman(xs, ys),
        }
        sorted_x = sorted(xs)
        sorted_y = sorted(ys)
        for q in TAIL_QUANTILES:
            tx = _percentile(sorted_x, q)
            ty = _percentile(sorted_y, q)
            ref_tail = sum(1 for v in xs if v > tx)
            ls_tail = sum(1 for v in ys if v > ty)
            both = sum(1 for vx, vy in pairs if vx > tx and vy > ty)
            entry[f"ref_tail_{q}"] = ref_tail
            entry[f"ls_tail_{q}"] = ls_tail
            entry[f"both_tail_{q}"] = both
            entry[f"both_given_ref_tail_{q}"] = round(both / ref_tail, 6) if ref_tail else None
            entry[f"both_given_ls_tail_{q}"] = round(both / ls_tail, 6) if ls_tail else None
        out[ref_sig] = entry
    return {
        "method": (
            "object-aligned natural-partner pairs over a deterministic bounded sample "
            "(reservoir); thresholds are each signal's own empirical quantile; "
            "overlap is descriptive only, not semantic equivalence"
        ),
        "seed": seed,
        "partners": out,
    }


def _disagreement_candidates(
    sampled_rows: list[tuple[dict, int, dict, dict | None, dict | None]],
    seed: int,
) -> dict:
    """Neutral REFERENCE-DISAGREEMENT CANDIDATE scan (EXPLORATORY, NON-CONTRACT)."""

    ref_sigs = list(REFERENCE_NUMERIC_SIGNALS)
    ls_sigs = list(LS_ANALYSIS_SIGNALS)
    pool_ref: dict[str, list[float]] = {sig: [] for sig in ref_sigs}
    pool_ls: dict[str, list[float]] = {sig: [] for sig in ls_sigs}
    for _rec, _idx, ref_row, ls_row, _seg in sampled_rows:
        for sig in ref_sigs:
            value = ref_row.get(sig)
            if _finite_number(value):
                pool_ref[sig].append(float(value))
        if ls_row is not None:
            for sig in ls_sigs:
                value = ls_row.get(sig)
                if _finite_number(value):
                    pool_ls[sig].append(float(value))

    def _thresholds(pool: dict[str, list[float]]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for sig, values in pool.items():
            values.sort()
            out[sig] = {
                "n": len(values),
                "p0_5": _percentile(values, 0.005),
                "p5": _percentile(values, ORDINARY_LO_PROB),
                "p95": _percentile(values, ORDINARY_HI_PROB),
                "p99_5": _percentile(values, EXTREME_TAIL_PROB),
            }
        return out

    thresholds_ref = _thresholds(pool_ref)
    thresholds_ls = _thresholds(pool_ls)
    sorted_ref = {sig: sorted(pool_ref[sig]) for sig in ref_sigs}
    sorted_ls = {sig: sorted(pool_ls[sig]) for sig in ls_sigs}

    def _status(value: float, sorted_values: list[float], n: int) -> str:
        """Tie-robust empirical tail status."""

        if n == 0:
            return "none"
        lo = bisect.bisect_left(sorted_values, value) / n
        hi = bisect.bisect_right(sorted_values, value) / n
        if lo >= EXTREME_TAIL_PROB:
            return "high"
        if hi <= 1.0 - EXTREME_TAIL_PROB:
            return "low"
        if lo >= ORDINARY_LO_PROB and hi <= ORDINARY_HI_PROB:
            return "mid"
        return "none"

    def _is_extreme(status: str) -> bool:
        return status in ("low", "high")

    def _is_ordinary(status: str) -> bool:
        return status == "mid"

    candidates: dict[str, list[dict]] = {"A": [], "B": []}
    total_counts = {"A": 0, "B": 0}
    for rec, idx, ref_row, ls_row, seg in sampled_rows:
        ref_extreme: list[str] = []
        ref_finite: list[str] = []
        ref_ordinary: list[str] = []
        for sig in ref_sigs:
            value = ref_row.get(sig)
            if not _finite_number(value):
                continue
            v = float(value)
            ref_finite.append(sig)
            status = _status(v, sorted_ref[sig], len(sorted_ref[sig]))
            if _is_extreme(status):
                ref_extreme.append(sig)
            elif _is_ordinary(status):
                ref_ordinary.append(sig)
        ls_extreme: list[str] = []
        ls_finite: list[str] = []
        ls_ordinary: list[str] = []
        if ls_row is not None:
            for sig in ls_sigs:
                value = ls_row.get(sig)
                if not _finite_number(value):
                    continue
                v = float(value)
                ls_finite.append(sig)
                status = _status(v, sorted_ls[sig], len(sorted_ls[sig]))
                if _is_extreme(status):
                    ls_extreme.append(sig)
                elif _is_ordinary(status):
                    ls_ordinary.append(sig)
        # A: official reference extreme while observable primitives stay ordinary.
        if ref_extreme and len(ls_finite) >= 2 and len(ls_extreme) == 0 and len(ls_ordinary) == len(ls_finite):
            total_counts["A"] += 1
            candidates["A"].append(
                _candidate_entry(
                    rec, idx, ref_row, ls_row, seg, "A",
                    ref_extreme, ls_extreme, thresholds_ref, thresholds_ls,
                )
            )
        # B: observable extreme combination while official references stay ordinary.
        if ls_extreme and len(ref_finite) >= 2 and len(ref_extreme) == 0 and len(ref_ordinary) == len(ref_finite):
            total_counts["B"] += 1
            candidates["B"].append(
                _candidate_entry(
                    rec, idx, ref_row, ls_row, seg, "B",
                    ref_extreme, ls_extreme, thresholds_ref, thresholds_ls,
                )
            )

    def _sort_key(entry: dict) -> tuple:
        return (-int(entry["score"]), str(entry["sample_id"]), int(entry["object_index"]))

    for kind in ("A", "B"):
        candidates[kind].sort(key=_sort_key)
        candidates[kind] = candidates[kind][:CANDIDATE_TOP_PER_TYPE]

    summary = {
        "classification": "REFERENCE-DISAGREEMENT CANDIDATES",
        "status": "EXPLORATORY NON-CONTRACT NON-SKILL",
        "seed": seed,
        "method": (
            "empirical per-signal thresholds from the deterministic bounded object sample; "
            "type A = at least one ref.ppy.* value outside its 0.5%/99.5% tail while all finite "
            "ls.* analysis values stay inside their 5%-95% band; type B = the mirror case. "
            "These are candidates for human inspection, not labels and not official blind spots."
        ),
        "sampled_object_rows": len(sampled_rows),
        "total_candidates_before_cap": total_counts,
        "kept_candidates": {kind: len(candidates[kind]) for kind in ("A", "B")},
        "kept_maps": {
            kind: len({c["sample_id"] for c in candidates[kind]}) for kind in ("A", "B")
        },
        "ref_thresholds": thresholds_ref,
        "ls_thresholds": thresholds_ls,
    }
    return {"summary": summary, "candidates": candidates}


def _candidate_entry(
    rec: dict,
    idx: int,
    ref_row: dict,
    ls_row: dict | None,
    seg: dict | None,
    kind: str,
    ref_extreme: list[str],
    ls_extreme: list[str],
    thresholds_ref: dict,
    thresholds_ls: dict,
) -> dict:
    ref_values = {sig: ref_row.get(sig) for sig in REFERENCE_NUMERIC_SIGNALS}
    ls_values = {}
    if ls_row is not None:
        for sig in LS_ANALYSIS_SIGNALS:
            if _finite_number(ls_row.get(sig)):
                ls_values[sig] = float(ls_row[sig])
    score = len(ref_extreme) if kind == "A" else len(ls_extreme)
    return {
        "classification": "REFERENCE-DISAGREEMENT CANDIDATE",
        "status": "EXPLORATORY NON-CONTRACT NON-SKILL",
        "candidate_type": "A" if kind == "A" else "B",
        "reason": (
            "official reference extreme while all selected observable primitives are ordinary"
            if kind == "A"
            else "observable extreme combination while all official reference values are ordinary"
        ),
        "score": score,
        "sample_id": rec["sample_id"],
        "checksum": rec["checksum"],
        "path": rec["path"],
        "flags": rec.get("flags") or [],
        "object_index": idx,
        "time_sorted_index": ref_row.get("ref.time_sorted_index"),
        "start_time_ms": ref_row.get("ref.start_time_ms"),
        "segment_start_ms": seg.get("start_ms") if seg is not None else None,
        "segment_end_ms": seg.get("end_ms") if seg is not None else None,
        "ref_extreme_signals": ref_extreme,
        "ls_extreme_signals": ls_extreme,
        "ref_values": ref_values,
        "ls_values": ls_values,
        "ref_thresholds": {sig: thresholds_ref[sig] for sig in ref_extreme},
        "ls_thresholds": {sig: thresholds_ls[sig] for sig in ls_extreme},
        "provenance": list(ref_row.get("ref.provenance") or []),
    }


def _write_segment_artifacts(args, analysis: dict) -> None:
    with (args.out_dir / "segment_stats.json").open("w", encoding="utf-8") as fh:
        json.dump(analysis, fh, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    candidates = analysis.get("disagreement_candidates")
    if not candidates:
        return
    with (args.out_dir / "reference_disagreement_candidates.jsonl").open("w", encoding="utf-8") as fh:
        for kind in ("A", "B"):
            for entry in candidates.get(kind, []):
                fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def _write_report(args, stats_all: dict) -> None:
    lines = ["# Reference Signal QA Report", ""]
    lines.append(f"- verdict: {stats_all.get('verdict')}")
    lines.append(f"- feature_version: {FEATURE_VERSION}")
    lines.append(f"- local_signal_version: {SIGNAL_VERSION}")
    lines.append(f"- reference_version: {REFERENCE_VERSION}")
    for phase, stats in stats_all.get("phases", {}).items():
        lines.append(f"## Phase {phase}")
        lines.append(f"- records={stats['records']} ok={stats['ok']} failures={stats['failures']}")
        lines.append(f"- nonfinite maps={stats.get('nonfinite_maps')}")
        lines.append(f"- geometry blocked maps={stats['geometry_blocked_maps']} objects={stats['geometry_blocked_objects']}")
        lines.append(f"- unavailable rows={stats['unavailable_rows']}")
        lines.append(f"- segment alignment failures={stats['segment']['alignment_failures']}")
        perf = stats["performance"]
        lines.append(f"- latency p50={perf['latency_ms'].get('p50')} p95={perf['latency_ms'].get('p95')} p99={perf['latency_ms'].get('p99')} max={perf['latency_ms'].get('max')}")
        lines.append(f"- maps/sec={perf['maps_per_second']}")
        lines.append("")
    if stats_all.get("segment_qa"):
        seg = stats_all["segment_qa"]
        lines.append("## Segment QA (5k)")
        lines.append(f"- sparse segment rate={seg['sparse_segment_rate']}")
        lines.append(f"- boundary peak rate={seg['boundary_peak_rate']}")
        lines.append(f"- sustained peak maps={seg['sustained_peak_maps']}")
        lines.append(f"- spike preserved maps={seg['spike_preserved_maps']}")
        counts = seg.get("candidate_count") or {}
        lines.append(f"- disagreement candidates kept: A={counts.get('type_a')} B={counts.get('type_b')}")
        lines.append("")
    text = "\n".join(lines)
    (args.out_dir / "REFERENCE_QA_REPORT.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
