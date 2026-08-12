"""Feature QA pipeline for the local osu!standard corpus.

Phases (gated, deterministic):

  5k   stratified feature QA over 5,000 maps
  20k  nested expansion to 20,000 maps (only after 5k has no blocker)
  full all eligible manifest maps, with streaming/online univariate stats

Every map runs the full chain:

  parse -> normalize -> corrected Feature contract -> segment (fixed 5s windows) -> aggregate

No skill labels are produced. No taxonomy is touched. Anomalies are written
to disk with full provenance (sample_id/path/checksum/feature/value), never
silently corrected.
"""

from __future__ import annotations

import argparse
import bisect
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
from typing import Any, Callable

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from osu_skill_profiler import SCHEMA_VERSION
from osu_skill_profiler.features.extractor import FeatureExtractor
from osu_skill_profiler.features.schema import FEATURE_SCHEMA, FEATURE_VERSION
from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import OsuParseError, parse_osu_file
from osu_skill_profiler.segments.aggregator import aggregate_features
from osu_skill_profiler.segments.fixed_time import FixedTimeWindowStrategy

EXPECTED_FEATURE_COUNT = len(FEATURE_SCHEMA)
DEFAULT_SEED = 20260810
WINDOW_MS = 5000.0
RESERVOIR_SIZE = 20000
UNIQUE_CAP = 8192
MOMENT_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------


def _hash_score(sample_id: str, seed: int) -> float:
    digest = __import__("hashlib").sha256(f"{seed}:{sample_id}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / 2**64


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _pathological_flags(sample: dict, scan: dict) -> list[str]:
    """Deterministic, documented rules for pathological/extreme maps."""

    flags: list[str] = []
    fv = sample.get("format_version")
    if fv == 128:
        flags.append("format_v128")
    meta = sample.get("metadata", {})
    counts = meta.get("counts", {})
    diff = meta.get("difficulty", {})
    duration = _num(meta.get("duration_ms"))
    bpm_max = _num(meta.get("bpm_max"))
    if bpm_max is None:
        flags.append("no_positive_bpm")
    elif bpm_max >= 10000:
        flags.append("bpm_extreme_high")
    elif bpm_max <= 10:
        flags.append("bpm_extreme_low")
    if duration is not None:
        if duration >= 1_000_000:
            flags.append("duration_extreme_long")
        elif duration <= 5_000:
            flags.append("duration_extreme_short")
    object_count = _num(counts.get("objects"))
    if object_count is not None:
        if object_count >= 4000:
            flags.append("object_count_extreme_high")
        elif object_count <= 3:
            flags.append("object_count_extreme_low")
    timing_count = _num(counts.get("timing_points"))
    if timing_count is not None and timing_count >= 1500:
        flags.append("timing_extreme_high")
    green_count = _num(scan.get("green_count"))
    if green_count is not None and green_count >= 1500:
        flags.append("green_extreme_high")
    repeats_max = _num(scan.get("repeats_max"))
    if repeats_max is not None and repeats_max >= 100:
        flags.append("repeats_extreme")
    sliders = _num(counts.get("sliders"))
    if object_count and sliders is not None and object_count > 0:
        ratio = sliders / object_count
        if ratio == 1.0:
            flags.append("all_slider")
    for key in ("AR", "OD", "CS", "HP"):
        value = _num(diff.get(key))
        if value is not None and not (-0.001 <= value <= 10.999):
            flags.append(f"difficulty_extreme_{key}")
            break
    version = str(sample.get("version") or "")
    rel_path = str(sample.get("relative_path") or sample.get("reference") or "")
    if "aspire" in (version + " " + rel_path).lower():
        flags.append("aspire_like")
    return flags


def _quantile_edges(values: list[float]) -> list[float]:
    values = sorted(values)
    n = len(values)
    if n < 5:
        return values[:4]
    return [
        values[min(n - 1, int(round(0.2 * (n - 1))))],
        values[min(n - 1, int(round(0.4 * (n - 1))))],
        values[min(n - 1, int(round(0.6 * (n - 1))))],
        values[min(n - 1, int(round(0.8 * (n - 1))))],
    ]


def _bucket(value: float | None, edges: list[float]) -> str:
    if value is None:
        return "missing"
    idx = bisect.bisect_right(edges, value)
    return f"q{min(idx, 4)}"


def build_selection(
    manifest_path: Path,
    scan_path: Path,
    failures_path: Path,
    seed: int,
) -> tuple[list[dict], list[dict], dict]:
    """Deterministic ordered selection; first N records are the N-map phase."""

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    samples = manifest["samples"]
    scan_by_path: dict[str, dict] = {}
    scan_by_rel: dict[str, dict] = {}
    with Path(scan_path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                scan_by_path[rec["path"]] = rec
                if rec.get("rel_path"):
                    scan_by_rel[rec["rel_path"]] = rec
    known_broken: set[str] = set()
    known_broken_rel: set[str] = set()
    if failures_path.exists():
        with Path(failures_path).open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    broken_path = json.loads(line)["path"]
                    known_broken.add(broken_path)
                    scan_rec = scan_by_path.get(broken_path)
                    if scan_rec and scan_rec.get("rel_path"):
                        known_broken_rel.add(scan_rec["rel_path"])

    enriched: list[dict] = []
    for sample in samples:
        path = sample["reference"]
        if not path:
            path = sample.get("relative_path")
        scan = scan_by_rel.get(sample.get("relative_path") or path) or scan_by_path.get(path) or {}
        sliders = _num(sample.get("metadata", {}).get("counts", {}).get("sliders"))
        object_count = _num(sample.get("metadata", {}).get("counts", {}).get("objects"))
        rec = {
            "sample_id": sample["sample_id"],
            "path": path,
            "checksum": sample["checksum"],
            "format_version": sample.get("format_version"),
            "local_set_group": sample.get("local_set_group") or scan.get("folder"),
            "version": sample.get("version") or "",
            "relative_path": sample.get("relative_path") or path,
            "known_broken": (
                path in known_broken
                or (sample.get("relative_path") or path) in known_broken_rel
                or sample.get("sample_id") in known_broken
            ),
            "object_count": object_count,
            "duration_ms": _num(sample.get("metadata", {}).get("duration_ms")),
            "bpm_max": _num(sample.get("metadata", {}).get("bpm_max")),
            "timing_count": _num(sample.get("metadata", {}).get("counts", {}).get("timing_points")),
            "green_count": _num(scan.get("green_count")),
            "slider_ratio": sliders / object_count if (sliders is not None and object_count) else None,
            "ar": _num(sample.get("metadata", {}).get("difficulty", {}).get("AR")),
            "od": _num(sample.get("metadata", {}).get("difficulty", {}).get("OD")),
            "cs": _num(sample.get("metadata", {}).get("difficulty", {}).get("CS")),
            "repeats_max": _num(scan.get("repeats_max")),
            "score": _hash_score(sample["sample_id"], seed),
        }
        rec["flags"] = _pathological_flags(sample, scan)
        rec["pathological"] = bool([f for f in rec["flags"] if f != "aspire_like"]) or "aspire_like" in rec["flags"]
        enriched.append(rec)

    eligible = [r for r in enriched if not r["known_broken"]]
    dims = {
        "object_count": ("object_count", 5),
        "duration_ms": ("duration_ms", 5),
        "bpm_max": ("bpm_max", 5),
        "timing_count": ("timing_count", 5),
        "green_count": ("green_count", 5),
        "slider_ratio": ("slider_ratio", 5),
        "ar": ("ar", 5),
        "od": ("od", 5),
        "cs": ("cs", 5),
    }
    edges: dict[str, list[float]] = {}
    for dim, (key, _buckets) in dims.items():
        values = [r[key] for r in eligible if r[key] is not None]
        edges[dim] = _quantile_edges(values)
        for rec in eligible:
            rec[f"{dim}_bucket"] = _bucket(rec[key], edges[dim])

    tier: dict[str, int] = {}
    for rec in eligible:
        fv = rec["format_version"]
        if fv in (3, 4, 128):
            tier[rec["sample_id"]] = 0
        elif rec["pathological"]:
            tier[rec["sample_id"]] = 1
        else:
            tier[rec["sample_id"]] = 3

    # Stratified quotas for every dimension/bucket.
    quota_records: dict[str, dict] = {}
    for dim, (key, _buckets) in dims.items():
        for bucket_id in [f"q{i}" for i in range(5)] + ["missing"]:
            candidates = [r for r in eligible if r[f"{dim}_bucket"] == bucket_id and tier[r["sample_id"]] == 3]
            candidates.sort(key=lambda r: r["score"])
            for rec in candidates[:35]:
                quota_records[rec["sample_id"]] = rec
    for sample_id, rec in quota_records.items():
        if tier[sample_id] == 3:
            tier[sample_id] = 2

    def order_key(rec: dict) -> tuple[int, float, str]:
        return (tier[rec["sample_id"]], rec["score"], rec["sample_id"])

    eligible.sort(key=order_key)

    # Spread across local set groups for tier 2/3 (tier 0/1 keep all).
    ordered_full = list(eligible)
    ordered_sample: list[dict] = []
    set_counts: Counter = Counter()
    for rec in eligible:
        t = tier[rec["sample_id"]]
        group = rec["local_set_group"] or rec["sample_id"]
        if t in (0, 1) or set_counts[group] < 4:
            ordered_sample.append(rec)
            if t in (2, 3):
                set_counts[group] += 1

    meta = {
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "manifest_total": len(samples),
        "eligible": len(eligible),
        "known_broken_excluded": len(enriched) - len(eligible),
        "format_version_counts": dict(Counter(str(r["format_version"]) for r in eligible)),
        "pathological_count": sum(1 for r in eligible if r["pathological"]),
        "aspire_like_count": sum(1 for r in eligible if "aspire_like" in r["flags"]),
        "local_set_group_count": len({r["local_set_group"] for r in eligible}),
    }
    return ordered_full, ordered_sample, meta


# ---------------------------------------------------------------------------
# extraction worker
# ---------------------------------------------------------------------------


def _finite_count(values) -> tuple[int, int]:
    nonfinite = 0
    present = 0
    for value in values.values():
        if isinstance(value, float) and not math.isfinite(value):
            nonfinite += 1
        if value is not None:
            present += 1
    return present, nonfinite


def _process_map(rec: dict) -> dict:
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
        "feature_count": None,
        "features": None,
        "segment_count": None,
        "objects_per_segment": None,
        "duration_per_segment": None,
        "empty_segments": None,
        "short_lt100": None,
        "short_lt1000": None,
        "index_span_consistent": None,
        "segment_nonfinite_count": None,
        "agg_nonfinite_count": None,
        "agg_serializable": None,
        "object_count": rec["object_count"],
        "duration_ms": rec["duration_ms"],
        "bpm_max": rec["bpm_max"],
        "ar": rec["ar"],
        "od": rec["od"],
        "cs": rec["cs"],
        "slider_ratio": rec["slider_ratio"],
        "timing_count": rec["timing_count"],
        "green_count": rec["green_count"],
        "feature_version": FEATURE_VERSION,
    }
    t0 = time.perf_counter()
    try:
        beatmap = parse_osu_file(abs_path)
        out["parse_latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        nmap = normalize(beatmap)
        extractor = FeatureExtractor()
        features = extractor.extract(nmap)
        out["feature_count"] = len(features)
        if len(features) != EXPECTED_FEATURE_COUNT:
            out["error_type"] = "FeatureCountMismatch"
            out["error"] = f"expected {EXPECTED_FEATURE_COUNT}, got {len(features)}"
            out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
            return out
        json.dumps(features, ensure_ascii=False, allow_nan=False)
        segments = FixedTimeWindowStrategy(window_ms=WINDOW_MS).segment(nmap, extractor)
        seg_counts = [seg.end_idx - seg.start_idx for seg in segments]
        seg_durations = [max(0.0, seg.end_ms - seg.start_ms) for seg in segments]
        seg_nonfinite = 0
        for seg in segments:
            _present, nonfinite = _finite_count(seg.features)
            seg_nonfinite += nonfinite
        aggregated = aggregate_features(segments)
        _agg_present, agg_nonfinite = _finite_count(aggregated)
        try:
            json.dumps(aggregated, ensure_ascii=False, allow_nan=False)
            agg_serializable = True
        except (TypeError, ValueError):
            agg_serializable = False
        out["features"] = features
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
        out["index_span_consistent"] = sum(seg_counts) == len(nmap.objects)
        out["segment_nonfinite_count"] = seg_nonfinite
        out["agg_nonfinite_count"] = agg_nonfinite
        out["agg_serializable"] = agg_serializable
        out["ok"] = True
    except Exception as exc:  # noqa: BLE001 - triage then fix
        out["error_type"] = type(exc).__name__
        out["error"] = str(exc)[:300]
    out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    return out


def _resume_record_complete(rec: dict) -> bool:
    features = rec.get("features")
    return (
        rec.get("ok") is True
        and rec.get("feature_version") == FEATURE_VERSION
        and rec.get("feature_count") == EXPECTED_FEATURE_COUNT
        and isinstance(features, dict)
        and len(features) == EXPECTED_FEATURE_COUNT
        and isinstance(rec.get("segment_count"), int)
        and rec.get("index_span_consistent") is True
        and rec.get("segment_nonfinite_count") == 0
        and rec.get("agg_nonfinite_count") == 0
        and rec.get("agg_serializable") is True
    )


def _prepare_resume_records(
    out_path: Path,
    resume: bool,
    is_complete: Callable[[dict], bool],
) -> set[str]:
    """Keep only unique, schema-complete successful rows before resuming.

    A failed, partial, stale-version, malformed or duplicate row is not a
    completed map. When any such row exists, rewrite the JSONL atomically from
    the retained raw lines before new work is appended. This makes interrupted
    full-corpus runs retry incomplete work without leaving duplicate IDs.
    """

    if not resume or not out_path.exists():
        return set()
    done: set[str] = set()
    clean = True
    tmp_path = out_path.with_name(f"{out_path.name}.resume.tmp")
    with out_path.open(encoding="utf-8") as source, tmp_path.open("w", encoding="utf-8") as retained:
        for raw_line in source:
            if not raw_line.strip():
                clean = False
                continue
            try:
                rec = json.loads(raw_line)
            except json.JSONDecodeError:
                clean = False
                continue
            sample_id = rec.get("sample_id")
            if (
                not isinstance(sample_id, str)
                or not sample_id
                or sample_id in done
                or not is_complete(rec)
            ):
                clean = False
                continue
            done.add(sample_id)
            retained.write(raw_line if raw_line.endswith("\n") else raw_line + "\n")
            if not raw_line.endswith("\n"):
                clean = False
    if clean:
        tmp_path.unlink()
    else:
        os.replace(tmp_path, out_path)
    return done


def _run_extraction(records: list[dict], out_path: Path, workers: int, resume: bool) -> dict:
    done = _prepare_resume_records(out_path, resume, _resume_record_complete)
    todo = [r for r in records if r["sample_id"] not in done]
    print(f"extract total={len(records)} done={len(done)} todo={len(todo)} workers={workers}", flush=True)
    start = time.time()
    ok_count = 0
    fail_count = 0
    mode = "a" if resume and done else "w"
    with out_path.open(mode, encoding="utf-8") as fh:
        if mode == "w":
            pass
        if not todo:
            return {"ok": 0, "fail": 0, "elapsed_s": 0.0}
        import multiprocessing

        if workers <= 1:
            iterator = (_process_map(r) for r in todo)
        else:
            with multiprocessing.Pool(processes=workers, maxtasksperchild=200) as pool:
                iterator = pool.imap(_process_map, todo, chunksize=8)
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


def _percentile(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_values[lo]
    w = pos - lo
    return sorted_values[lo] * (1.0 - w) + sorted_values[hi] * w


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 30:
        return None
    scale_x = max((abs(value) for value in xs), default=0.0)
    scale_y = max((abs(value) for value in ys), default=0.0)
    if scale_x == 0.0 or scale_y == 0.0:
        return None
    scaled_xs = [value / scale_x for value in xs]
    scaled_ys = [value / scale_y for value in ys]
    mx = statistics.fmean(scaled_xs)
    my = statistics.fmean(scaled_ys)
    num = 0.0
    dx = 0.0
    dy = 0.0
    for x, y in zip(scaled_xs, scaled_ys):
        ax = x - mx
        ay = y - my
        num += ax * ay
        dx += ax * ax
        dy += ay * ay
    den = math.sqrt(dx) * math.sqrt(dy)
    if den == 0:
        return None
    return num / den


class _ScaledMoments:
    """Mergeable Welford moments normalised by the largest absolute value."""

    def __init__(self) -> None:
        self.count = 0
        self.scale = 0.0
        self.mean_scaled = 0.0
        self.m2_scaled = 0.0

    def update(self, value: float) -> None:
        magnitude = abs(value)
        if magnitude > self.scale:
            if self.scale > 0.0:
                factor = self.scale / magnitude
                self.mean_scaled *= factor
                self.m2_scaled *= factor * factor
            self.scale = magnitude
        scaled = value / self.scale if self.scale else 0.0
        self.count += 1
        delta = scaled - self.mean_scaled
        self.mean_scaled += delta / self.count
        self.m2_scaled += delta * (scaled - self.mean_scaled)

    def merge(self, count: int, scale: float, mean_scaled: float, m2_scaled: float) -> None:
        if count <= 0:
            return
        if not all(math.isfinite(value) for value in (scale, mean_scaled, m2_scaled)) or scale < 0.0 or m2_scaled < 0.0:
            raise ValueError("invalid scaled moment summary")
        if self.count == 0:
            self.count = count
            self.scale = scale
            self.mean_scaled = mean_scaled
            self.m2_scaled = m2_scaled
            return
        target_scale = max(self.scale, scale)
        if target_scale == 0.0:
            self.count += count
            return
        left_factor = self.scale / target_scale
        right_factor = scale / target_scale
        left_mean = self.mean_scaled * left_factor
        right_mean = mean_scaled * right_factor
        left_m2 = self.m2_scaled * left_factor * left_factor
        right_m2 = m2_scaled * right_factor * right_factor
        total = self.count + count
        delta = right_mean - left_mean
        self.mean_scaled = left_mean + delta * count / total
        self.m2_scaled = left_m2 + right_m2 + delta * delta * self.count * count / total
        self.count = total
        self.scale = target_scale

    def snapshot(self) -> dict[str, float | int]:
        return {
            "moments_version": MOMENT_SCHEMA_VERSION,
            "count": self.count,
            "scale": self.scale,
            "mean_scaled": self.mean_scaled,
            "m2_scaled": self.m2_scaled,
        }

    def mean(self) -> float | None:
        if self.count == 0:
            return None
        coefficient = min(1.0, max(-1.0, self.mean_scaled))
        return coefficient * self.scale

    def std(self) -> float:
        if self.count <= 1 or self.scale == 0.0:
            return 0.0
        coefficient = min(1.0, math.sqrt(max(0.0, self.m2_scaled / self.count)))
        return coefficient * self.scale


class _StreamAccumulator:
    """Bounded-memory univariate accumulator (Welford + reservoir)."""

    def __init__(self, exact: bool, rng: random.Random) -> None:
        self.exact = exact
        self.rng = rng
        self.total = 0
        self.missing = 0
        self.nonfinite = 0
        self.zero = 0
        self.min: float | None = None
        self.max: float | None = None
        self.moments = _ScaledMoments()
        self.values: list[float] = [] if exact else []
        self.reservoir: list[float] = []
        self.unique: set[float] = set()
        self.unique_capped = False

    def update(self, value: float | None) -> None:
        self.total += 1
        if value is None:
            self.missing += 1
            return
        if isinstance(value, float) and not math.isfinite(value):
            self.nonfinite += 1
            return
        value = float(value)
        if value == 0.0:
            self.zero += 1
        if self.min is None or value < self.min:
            self.min = value
        if self.max is None or value > self.max:
            self.max = value
        self.moments.update(value)
        if self.exact:
            self.values.append(value)
        else:
            if len(self.reservoir) < RESERVOIR_SIZE:
                self.reservoir.append(value)
            else:
                j = self.rng.randrange(self.moments.count)
                if j < RESERVOIR_SIZE:
                    self.reservoir[j] = value
        if len(self.unique) < UNIQUE_CAP:
            self.unique.add(value)
        elif value not in self.unique:
            self.unique_capped = True

    def finish(self, near_constant: bool = True) -> dict:
        present = self.total - self.missing - self.nonfinite
        sorted_values = sorted(self.values if self.exact else self.reservoir)
        median = _percentile(sorted_values, 0.5) if sorted_values else None
        if near_constant and sorted_values:
            tol = 1e-9 * max(1.0, abs(median))
            near_const = sum(1 for v in sorted_values if abs(v - median) <= tol) / len(sorted_values)
        else:
            near_const = 0.0
        out = {
            "count": present,
            "missing": self.missing,
            "missing_rate": round(self.missing / self.total, 6) if self.total else 0.0,
            "nonfinite": self.nonfinite,
            "min": self.min,
            "max": self.max,
            "mean": round(self.moments.mean(), 6) if self.moments.count else None,
            "std": round(self.moments.std(), 6),
            "zero_rate": round(self.zero / present, 6) if present else 0.0,
            "unique_count": len(self.unique) if not self.unique_capped else f">={UNIQUE_CAP}",
            "unique_capped": self.unique_capped,
            "near_constant_rate": round(near_const, 6),
        }
        for p, label in ((0.001, "p0_1"), (0.01, "p1"), (0.05, "p5"), (0.25, "p25"), (0.5, "p50"), (0.75, "p75"), (0.95, "p95"), (0.99, "p99"), (0.999, "p99_9")):
            out[label] = _percentile(sorted_values, p)
        return out


def _dist_summary(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    values = sorted(values)
    return {
        "count": len(values),
        "min": values[0],
        "max": values[-1],
        "mean": round(statistics.fmean(values), 4),
        "p50": _percentile(values, 0.5),
        "p90": _percentile(values, 0.9),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "p100": values[-1],
    }


def _correlate_matrix(records: list[dict], feature_keys: list[str], proxy_keys: list[str]) -> dict:
    """Pearson correlations on aligned values (exact, bounded phase scope)."""

    pairs: list[dict] = []
    for i, a in enumerate(feature_keys):
        for b in feature_keys[i + 1 :]:
            xs: list[float] = []
            ys: list[float] = []
            for rec in records:
                va = rec.get("features", {}).get(a)
                vb = rec.get("features", {}).get(b)
                if va is not None and vb is not None and isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    va = float(va)
                    vb = float(vb)
                    if math.isfinite(va) and math.isfinite(vb):
                        xs.append(va)
                        ys.append(vb)
            r = _pearson(xs, ys)
            if r is not None and abs(r) > 0.9:
                pairs.append({"feature_a": a, "feature_b": b, "pearson": round(r, 6), "n": len(xs)})
    proxies: list[dict] = []
    for feature in feature_keys:
        for proxy in proxy_keys:
            xs: list[float] = []
            ys: list[float] = []
            for rec in records:
                vf = rec.get("features", {}).get(feature)
                vp = rec.get(proxy)
                if vf is not None and vp is not None and isinstance(vf, (int, float)) and isinstance(vp, (int, float)):
                    vf = float(vf)
                    vp = float(vp)
                    if math.isfinite(vf) and math.isfinite(vp):
                        xs.append(vf)
                        ys.append(vp)
            r = _pearson(xs, ys)
            if r is not None and abs(r) > 0.9:
                proxies.append({"feature": feature, "proxy": proxy, "pearson": round(r, 6), "n": len(xs)})
    pairs.sort(key=lambda p: -abs(p["pearson"]))
    proxies.sort(key=lambda p: -abs(p["pearson"]))
    return {"feature_pairs": pairs, "proxy": proxies}


def _stats_pass(jsonl: Path, phase: str, exact: bool, seed: int) -> dict:
    rng = random.Random(seed)
    acc: dict[str, _StreamAccumulator] = {}
    core_acc: dict[str, _StreamAccumulator] = {}
    proxy_acc: dict[str, _StreamAccumulator] = {}
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
    consistency_fail = 0
    seg_nonfinite_maps = 0
    agg_nonfinite_maps = 0
    agg_serialize_fail = 0
    latency: list[float] = []
    parse_latency: list[float] = []
    slow_heap: list[tuple[float, int, dict]] = []
    failures: list[dict] = []
    records = 0
    ok_records = 0
    core_records = 0
    exact_records: list[dict] = []
    proxy_keys = ("duration_ms", "object_count", "bpm_max", "format_version", "slider_ratio", "timing_count", "green_count", "ar", "od", "cs")

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
            if not rec.get("index_span_consistent"):
                consistency_fail += 1
            if int(rec.get("segment_nonfinite_count") or 0) > 0:
                seg_nonfinite_maps += 1
            if int(rec.get("agg_nonfinite_count") or 0) > 0:
                agg_nonfinite_maps += 1
            if not rec.get("agg_serializable"):
                agg_serialize_fail += 1
            features = rec.get("features") or {}
            for key, value in features.items():
                acc.setdefault(key, _StreamAccumulator(exact, rng)).update(value)
            for key in proxy_keys:
                value = rec.get(key)
                if value is not None:
                    proxy_acc.setdefault(key, _StreamAccumulator(exact, rng)).update(float(value))
            if not rec.get("flags"):
                core_records += 1
                for key, value in features.items():
                    core_acc.setdefault(key, _StreamAccumulator(exact, rng)).update(value)
            if exact:
                exact_records.append(
                    {
                        "features": {k: v for k, v in features.items()},
                        **{k: rec.get(k) for k in proxy_keys},
                    }
                )

    feature_stats = {key: acc[key].finish() for key in sorted(acc)}
    feature_stats_core = {key: core_acc[key].finish() for key in sorted(core_acc)}
    proxy_stats = {key: proxy_acc[key].finish() for key in sorted(proxy_acc)}
    correlation = _correlate_matrix(exact_records, sorted(feature_stats), list(proxy_keys)) if exact else {
        "feature_pairs": [],
        "proxy": [],
        "note": "full phase correlations computed on the deterministic 20k nested subset",
    }
    slow_maps = [heapq.heappop(slow_heap)[2] for _ in range(len(slow_heap))]
    slow_maps.sort(key=lambda r: -float(r["latency_ms"]))
    return {
        "phase": phase,
        "feature_version": FEATURE_VERSION,
        "records": records,
        "ok": ok_records,
        "failures": len(failures),
        "failure_detail": failures,
        "feature_count_distribution": dict(feature_counts),
        "feature_stats": feature_stats,
        "feature_stats_core": feature_stats_core,
        "core_records": core_records,
        "proxy_stats": proxy_stats,
        "correlation": correlation,
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
            "index_span_consistency_failures": consistency_fail,
            "segment_nonfinite_maps": seg_nonfinite_maps,
            "aggregate_nonfinite_maps": agg_nonfinite_maps,
            "aggregate_serialize_failures": agg_serialize_fail,
        },
        "performance": {
            "latency_ms": _dist_summary(latency),
            "parse_latency_ms": _dist_summary(parse_latency),
            "total_latency_sum_ms": round(sum(latency), 3),
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


def _outlier_pass(jsonl: Path, stats: dict, out_path: Path) -> dict:
    feature_stats = stats["feature_stats"]
    thresholds: dict[str, tuple[float | None, float | None]] = {}
    for key, st in feature_stats.items():
        lo = st.get("p0_1")
        hi = st.get("p99_9")
        mean = st.get("mean")
        std = st.get("std")
        limits = [lo, hi]
        if isinstance(mean, (int, float)) and isinstance(std, (int, float)) and std and std > 0:
            limits.append(mean - 12 * std)
            limits.append(mean + 12 * std)
        thresholds[key] = (min([v for v in limits if isinstance(v, (int, float))], default=None),
                           max([v for v in limits if isinstance(v, (int, float))], default=None))
    total = 0
    per_feature: Counter = Counter()
    with out_path.open("w", encoding="utf-8") as fh:
        with jsonl.open(encoding="utf-8") as src:
            for line in src:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if not rec["ok"]:
                    continue
                features = rec.get("features") or {}
                for key, value in features.items():
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
                                    "feature": key,
                                    "value": value,
                                    "flags": rec["flags"],
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                                allow_nan=False,
                            )
                            + "\n"
                        )
                        total += 1
                        per_feature[key] += 1
    return {"outlier_records": total, "by_feature_top": per_feature.most_common(20)}


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _fmt(x: Any) -> str:
    if x is None:
        return "null"
    if isinstance(x, float):
        return f"{x:g}"
    return str(x)


def _write_report(out_dir: Path, selection_meta: dict, phase_results: dict[str, dict], outlier_summaries: dict[str, dict]) -> None:
    lines: list[str] = []
    lines.append("# Feature QA Report")
    lines.append("")
    lines.append(f"- generated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}")
    lines.append(f"- schema_version: {selection_meta.get('schema_version')}")
    lines.append(f"- feature_version: {FEATURE_VERSION}")
    lines.append(f"- seed: {selection_meta.get('seed')}")
    lines.append(f"- manifest_total: {selection_meta.get('manifest_total')}")
    lines.append(f"- eligible: {selection_meta.get('eligible')} (known-broken excluded: {selection_meta.get('known_broken_excluded')})")
    lines.append(f"- pathological flagged: {selection_meta.get('pathological_count')}, aspire-like: {selection_meta.get('aspire_like_count')}")
    lines.append(f"- local_set_group count: {selection_meta.get('local_set_group_count')}")
    lines.append("")
    lines.append("> `mtime_year` is NOT treated as map creation year; `format_version` is only a format-generation proxy.")
    lines.append("")
    for phase in ("5k", "20k", "full"):
        result = phase_results.get(phase)
        if not result:
            continue
        lines.append(f"## Phase {phase}")
        lines.append("")
        lines.append(f"- records: {result['records']}, ok: {result['ok']}, failures: {result['failures']}")
        lines.append(f"- feature_count_distribution: {result['feature_count_distribution']}")
        lines.append(f"- core (non-pathological/non-aspire) records: {result.get('core_records')}")
        core_nonfinite = [k for k, st in result.get("feature_stats_core", {}).items() if st["nonfinite"] > 0]
        lines.append(f"- core features with output NaN/Inf: {len(core_nonfinite)} {core_nonfinite[:5]}")
        nonfinite_features = [k for k, st in result["feature_stats"].items() if st["nonfinite"] > 0]
        lines.append(f"- features with output NaN/Inf: {len(nonfinite_features)} {nonfinite_features[:10]}")
        missing_high = sorted(
            ((k, st["missing_rate"]) for k, st in result["feature_stats"].items() if st["missing_rate"] > 0.5),
            key=lambda item: -item[1],
        )[:10]
        lines.append(f"- features with missing_rate>0.5: {missing_high}")
        near_const = sorted(
            ((k, st["near_constant_rate"]) for k, st in result["feature_stats"].items() if st["near_constant_rate"] >= 0.999),
            key=lambda item: -item[1],
        )[:10]
        lines.append(f"- near-constant features (>=0.999): {near_const}")
        extreme = sorted(
            ((k, st["max"]) for k, st in result["feature_stats"].items() if isinstance(st["max"], (int, float)) and abs(st["max"]) >= 1e12),
            key=lambda item: -abs(item[1]),
        )[:10]
        lines.append(f"- features with |max|>=1e12: {extreme}")
        pairs = result["correlation"]["feature_pairs"]
        strong = [p for p in pairs if abs(p["pearson"]) > 0.98]
        lines.append(f"- feature pairs |r|>0.98: {len(strong)}")
        for p in strong[:15]:
            lines.append(f"  - {p['feature_a']} ~ {p['feature_b']}: r={p['pearson']} n={p['n']}")
        proxy_strong = [p for p in result["correlation"]["proxy"] if abs(p["pearson"]) > 0.95]
        lines.append(f"- proxy correlations |r|>0.95: {len(proxy_strong)}")
        for p in proxy_strong[:15]:
            lines.append(f"  - {p['feature']} ~ {p['proxy']}: r={p['pearson']} n={p['n']}")
        if result["failures"]:
            lines.append("- failures:")
            for f in result["failure_detail"][:25]:
                lines.append(f"  - {f['sample_id']} | {f['error_type']}: {f['error']}")
        seg = result["segment"]
        lines.append(f"- segments: {json.dumps(seg, ensure_ascii=False)}")
        perf = result["performance"]
        lines.append(f"- latency_ms: {json.dumps(perf['latency_ms'], ensure_ascii=False)}")
        if perf.get("maps_per_sec") is not None:
            lines.append(
                f"- extraction: elapsed_s={perf.get('extract_elapsed_s')}, maps_per_sec={perf.get('maps_per_sec')}"
            )
        lines.append(f"- slowest: {json.dumps(perf['slowest_50'][:3], ensure_ascii=False)}")
        if phase in outlier_summaries:
            lines.append(f"- outliers: {json.dumps(outlier_summaries[phase], ensure_ascii=False)}")
        lines.append("")
        verdict = _verdict(result)
        lines.append(f"**Verdict: {verdict[0]}** — {verdict[1]}")
        lines.append("")
    Path(out_dir / "FEATURE_QA_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verdict(result: dict) -> tuple[str, str]:
    reasons: list[str] = []
    if result["failures"] > 0:
        reasons.append(f"{result['failures']} extraction failures")
    if result["feature_count_distribution"] and any(int(k) != EXPECTED_FEATURE_COUNT for k in result["feature_count_distribution"]):
        reasons.append(f"Feature {FEATURE_VERSION} count != {EXPECTED_FEATURE_COUNT}")
    nonfinite = [k for k, st in result["feature_stats"].items() if st["nonfinite"] > 0]
    if nonfinite:
        reasons.append(f"output NaN/Inf in {len(nonfinite)} features")
    seg = result["segment"]
    if seg["index_span_consistency_failures"]:
        reasons.append(f"{seg['index_span_consistency_failures']} index-span consistency failures")
    if seg["segment_nonfinite_maps"] or seg["aggregate_nonfinite_maps"]:
        reasons.append("non-finite segment/aggregate values")
    if seg["aggregate_serialize_failures"]:
        reasons.append("aggregate serialization failures")
    if result["failures"] and result["failures"] / max(1, result["records"]) > 0.001:
        reasons.append("failure rate > 0.1%")
    if reasons:
        return "BLOCKED", "; ".join(reasons)
    return "PASS", "no NaN/Inf, no serialization failures, no consistency failures, feature count stable"


def _write_phase_outputs(out_dir: Path, phase: str, selection_meta: dict, result: dict, outlier: dict) -> None:
    suffix = phase if phase != "full" else ""
    stats_path = out_dir / f"feature_stats_{phase}.json"
    stats_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    corr_path = out_dir / ("feature_correlations.json" if phase == "full" else f"feature_correlations_{phase}.json")
    corr_path.write_text(json.dumps(result["correlation"], ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    seg_path = out_dir / ("segment_stats.json" if phase == "full" else f"segment_stats_{phase}.json")
    seg_path.write_text(json.dumps(result["segment"], ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    slow_path = out_dir / ("slow_maps.jsonl" if phase == "full" else f"slow_maps_{phase}.jsonl")
    with slow_path.open("w", encoding="utf-8") as fh:
        for rec in result["performance"]["slowest_50"]:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    outlier_path = out_dir / ("feature_outliers.jsonl" if phase == "full" else f"feature_outliers_{phase}.jsonl")
    # outlier file already written by _outlier_pass; keep a phase summary
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
    jsonl = out_dir / f"feature_qa_{phase}.jsonl"
    extract_summary = _run_extraction(records, jsonl, workers, resume)
    print(f"extraction summary: {extract_summary}", flush=True)
    exact = phase in ("5k", "20k")
    result = _stats_pass(jsonl, phase, exact, seed)
    if phase == "full":
        corr_20k = out_dir / "feature_correlations_20k.json"
        if corr_20k.exists():
            result["correlation"] = json.loads(corr_20k.read_text(encoding="utf-8"))
            result["correlation"]["note"] = "computed exactly on the deterministic 20k nested subset (Phase B)"
    result["performance"]["extract_elapsed_s"] = round(extract_summary["elapsed_s"], 3)
    result["performance"]["maps_per_sec"] = (
        round(result["ok"] / extract_summary["elapsed_s"], 3) if extract_summary["elapsed_s"] else None
    )
    outlier_summary = _outlier_pass(jsonl, result, out_dir / ("feature_outliers.jsonl" if phase == "full" else f"feature_outliers_{phase}.jsonl"))
    _write_phase_outputs(out_dir, phase, selection_meta, result, outlier_summary)
    (out_dir / f"outlier_summary_{phase}.json").write_text(
        json.dumps(outlier_summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    phase_results = {}
    for other in ("5k", "20k", "full"):
        stats_path = out_dir / f"feature_stats_{other}.json"
        if stats_path.exists():
            phase_results[other] = json.loads(stats_path.read_text(encoding="utf-8"))
    if phase == "full":
        phase_results["full"] = result
    outlier_summaries = {}
    for other in ("5k", "20k", "full"):
        summary_path = out_dir / f"outlier_summary_{other}.json"
        if summary_path.exists():
            outlier_summaries[other] = json.loads(summary_path.read_text(encoding="utf-8"))
    _write_report(out_dir, selection_meta, phase_results, outlier_summaries)
    verdict = _verdict(result)
    print(f"PHASE_{phase.upper()}_VERDICT={verdict[0]}: {verdict[1]}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="feature_qa", description=__doc__)
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
