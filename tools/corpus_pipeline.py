"""Corpus tooling for osu-skill-profiler.

Commands:

  scan      lenient full-corpus scan (cheap regex/line counts, resumable)
  select    build an adversarial + stratified sample for parser QA
  qa        strict parser QA through the full profiler pipeline
  manifest  generate the full standard-mode manifest with SHA-256 + strict parse

No skill labels are ever produced by these tools. The manifest is a data
contract for future dataset work, not a profiling result.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from osu_skill_profiler import SCHEMA_VERSION
from osu_skill_profiler.features.extractor import FeatureExtractor
from osu_skill_profiler.models.baseline import DeterministicBaselineProfiler
from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import OsuParseError, parse_osu, parse_osu_file

MANIFEST_SCHEMA_VERSION = "0.1.0"
PARSER_VERSION = "0.1.0"
FEATURE_VERSION = FeatureExtractor.feature_version

META_TEXT_KEYS = ("Artist", "Title", "Creator", "Version")
META_INT_KEYS = ("BeatmapID", "BeatmapSetID")
DIFF_KEYS = ("HPDrainRate", "CircleSize", "OverallDifficulty", "ApproachRate", "SliderMultiplier", "SliderTickRate")


def load_path_list(path: str | Path) -> list[str]:
    """Read a path list that may be UTF-16 (PowerShell redirect) or UTF-8."""

    raw = Path(path).read_bytes()
    if b"\x00" in raw[:4096]:
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8", errors="replace")
    return [line.strip().lstrip("\ufeff").replace("\x00", "") for line in text.splitlines() if line.strip()]


def scan_one(path: str, root: str) -> dict:
    """Lenient scan of a single .osu: counts and key fields, no strict parse."""

    rec: dict[str, Any] = {"path": path}
    try:
        st = os.stat(path)
        rec["size"] = st.st_size
        rec["mtime"] = st.st_mtime
    except OSError as exc:
        rec["error"] = f"stat:{exc}"
        return rec
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        rec["error"] = f"read:{exc}"
        return rec
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16")
    else:
        text = data.decode("utf-8-sig", errors="replace")
    rec["rel_path"] = os.path.relpath(path, root).replace("\\", "/")
    rec["folder"] = os.path.dirname(rec["rel_path"])

    section: str | None = None
    format_version: int | None = None
    mode: int | None = None
    metadata: dict[str, Any] = {}
    difficulty: dict[str, float] = {}
    timing_count = 0
    green_count = 0
    bpm_values: list[float] = []
    object_count = 0
    slider_count = 0
    repeats_sum = 0
    repeats_max = 0
    pixel_length_max = 0.0
    first_time: float | None = None
    last_time: float | None = None

    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("osu file format v"):
            try:
                format_version = int(s.rsplit("v", 1)[1].strip())
            except ValueError:
                format_version = None
            continue
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1]
            continue
        if section == "General":
            if s.startswith("Mode:"):
                try:
                    mode = int(s.split(":", 1)[1].strip() or "0")
                except ValueError:
                    mode = None
        elif section == "Metadata":
            key, _, value = s.partition(":")
            if key in META_TEXT_KEYS:
                metadata[key] = value.strip()
            elif key in META_INT_KEYS:
                raw_value = value.strip()
                try:
                    metadata[key] = int(raw_value) if raw_value else 0
                except ValueError:
                    metadata[key] = 0
        elif section == "Difficulty":
            key, _, value = s.partition(":")
            if key in DIFF_KEYS:
                try:
                    difficulty[key] = float(value)
                except ValueError:
                    pass
        elif section == "TimingPoints":
            parts = s.split(",")
            if len(parts) < 7:
                continue
            timing_count += 1
            try:
                if parts[6].strip() == "1":
                    beat_length = float(parts[1])
                    if beat_length > 0:
                        bpm_values.append(60000.0 / beat_length)
                else:
                    green_count += 1
            except ValueError:
                pass
        elif section == "HitObjects":
            parts = s.split(",")
            if len(parts) < 5:
                continue
            try:
                obj_time = float(parts[2])
                obj_type = int(parts[3])
            except ValueError:
                continue
            object_count += 1
            if first_time is None or obj_time < first_time:
                first_time = obj_time
            if last_time is None or obj_time > last_time:
                last_time = obj_time
            if obj_type & 2:
                slider_count += 1
                if len(parts) > 6:
                    try:
                        repeats = int(parts[6])
                        repeats_sum += repeats
                        repeats_max = max(repeats_max, repeats)
                    except ValueError:
                        pass
                if len(parts) > 7:
                    try:
                        pixel_length_max = max(pixel_length_max, float(parts[7]))
                    except ValueError:
                        pass

    rec["format_version"] = format_version
    rec["mode"] = mode
    rec["metadata"] = metadata
    rec["difficulty"] = difficulty
    rec["timing_count"] = timing_count
    rec["green_count"] = green_count
    rec["bpm_min"] = min(bpm_values) if bpm_values else None
    rec["bpm_max"] = max(bpm_values) if bpm_values else None
    rec["object_count"] = object_count
    rec["slider_count"] = slider_count
    rec["repeats_sum"] = repeats_sum
    rec["repeats_max"] = repeats_max
    rec["pixel_length_max"] = pixel_length_max
    rec["first_time_ms"] = first_time
    rec["last_time_ms"] = last_time
    rec["duration_ms"] = (last_time - first_time) if (first_time is not None and last_time is not None) else None
    return rec


def scan_chunk(chunk: list[str], root: str) -> list[dict]:
    return [scan_one(path, root) for path in chunk]


def cmd_scan(args: argparse.Namespace) -> int:
    paths = load_path_list(args.list)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["path"])
                except (json.JSONDecodeError, KeyError):
                    pass
    todo = [p for p in paths if p not in done]
    print(f"total={len(paths)} done={len(done)} todo={len(todo)}", flush=True)
    if not todo:
        return 0

    import multiprocessing

    workers = min(args.workers, len(todo))
    chunk_size = max(1, len(todo) // (workers * 8))
    chunks = [todo[i : i + chunk_size] for i in range(0, len(todo), chunk_size)]
    start = time.time()
    processed = 0
    with multiprocessing.Pool(processes=workers) as pool:
        with out_path.open("a", encoding="utf-8") as fh:
            for records in pool.imap_unordered(
                functools.partial(scan_chunk, root=args.root), chunks, chunksize=1
            ):
                for rec in records:
                    fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
                processed += len(records)
                if processed % 20000 < len(records):
                    print(
                        f"progress {processed}/{len(todo)} elapsed={time.time()-start:.1f}s",
                        flush=True,
                    )
    print(f"scan done in {time.time()-start:.1f}s, wrote {len(todo)} records", flush=True)
    return 0


def _standard(rec: dict) -> bool:
    mode = rec.get("mode")
    return mode in (0, None) and not rec.get("error")


def _top(records: list[dict], key: str, n: int, reverse: bool = True, predicate=None) -> list[dict]:
    pool = [r for r in records if (predicate(r) if predicate else True) and r.get(key) is not None]
    pool.sort(key=lambda r: r[key], reverse=reverse)
    return pool[:n]


def _top_by(records: list[dict], keyfunc, n: int, reverse: bool = True) -> list[dict]:
    scored = [(keyfunc(r), r) for r in records if keyfunc(r) is not None]
    scored.sort(key=lambda pair: pair[0], reverse=reverse)
    return [r for _, r in scored[:n]]


def cmd_select(args: argparse.Namespace) -> int:
    records = [json.loads(line) for line in Path(args.scan).read_text(encoding="utf-8").splitlines() if line.strip()]
    std = [r for r in records if _standard(r)]
    nonstd = [r for r in records if not _standard(r)]
    print(f"scan_records={len(records)} standard={len(std)} non_standard={len(nonstd)}", flush=True)

    selected: list[dict] = []
    seen: set[str] = set()

    def add(items: list[dict]) -> None:
        for rec in items:
            if rec["path"] not in seen:
                seen.add(rec["path"])
                selected.append(rec)

    # 1. All no-Mode old standard files (historical compatibility set).
    no_mode = [r for r in std if r.get("mode") is None]
    add(no_mode)
    print(f"stratum no_mode={len(no_mode)} selected={len(selected)}", flush=True)

    # 2. Timing / SV extremes.
    add(_top(std, "timing_count", 100))
    add(_top(std, "green_count", 100))
    print(f"stratum timing/sv: selected={len(selected)}", flush=True)

    # 3. Slider extremes.
    add(_top(std, "slider_count", 80))
    add(_top(std, "repeats_max", 60, predicate=lambda r: (r.get("repeats_max") or 0) > 0))
    add(_top(std, "pixel_length_max", 60, predicate=lambda r: (r.get("pixel_length_max") or 0) > 0))
    print(f"stratum sliders: selected={len(selected)}", flush=True)

    # 4. Object count extremes.
    add(_top(std, "object_count", 60))
    add(_top(std, "object_count", 40, reverse=False, predicate=lambda r: (r.get("object_count") or 0) >= 1))
    print(f"stratum objects: selected={len(selected)}", flush=True)

    # 5. Duration extremes.
    add(_top(std, "duration_ms", 60))
    add(_top(std, "duration_ms", 60, reverse=False, predicate=lambda r: (r.get("duration_ms") or 0) > 0))
    print(f"stratum duration: selected={len(selected)}", flush=True)

    # 6. Difficulty / BPM extremes.
    for key in ("ApproachRate", "OverallDifficulty", "CircleSize", "HPDrainRate"):
        add(_top_by(std, lambda r, k=key: (r.get("difficulty") or {}).get(k), 20))
        add(_top_by(std, lambda r, k=key: (r.get("difficulty") or {}).get(k), 20, reverse=False))
    add(_top(std, "bpm_max", 40, predicate=lambda r: (r.get("bpm_max") or 0) > 0))
    add(_top(std, "bpm_min", 40, reverse=False, predicate=lambda r: (r.get("bpm_min") or 0) > 0))
    print(f"stratum difficulty/bpm: selected={len(selected)}", flush=True)

    # 7. Old format versions and old-era files (2007-2010-ish), limited.
    old_format = [r for r in std if isinstance(r.get("format_version"), int) and r["format_version"] <= 5]
    add(old_format[:300])
    add(
        _top(
            [r for r in std if isinstance(r.get("format_version"), int) and 6 <= r["format_version"] <= 9],
            "mtime",
            150,
        )
    )
    add(
        _top(
            [r for r in std if _year(r) is not None and _year(r) <= 2010],
            "mtime",
            150,
        )
    )
    print(f"stratum old sets: selected={len(selected)}", flush=True)

    if len(selected) > args.max_total:
        selected = selected[: args.max_total]
        seen = {r["path"] for r in selected}
        print(f"hard cap applied: selected={len(selected)}", flush=True)

    # 8. Cross-era random fill.
    remaining = [r for r in std if r["path"] not in seen]
    rng = random.Random(args.seed)
    rng.shuffle(remaining)
    quota = max(0, args.max_total - len(selected))
    add(remaining[:quota])
    print(f"stratum random: selected={len(selected)}", flush=True)

    # 9. Era top-up so every format-version era is represented in the random part.
    by_version: dict[int, list[dict]] = {}
    for r in remaining:
        fv = r.get("format_version")
        if isinstance(fv, int):
            by_version.setdefault(fv, []).append(r)
    for fv in sorted(by_version):
        bucket = [r for r in by_version[fv] if r["path"] not in seen]
        if bucket and args.max_total - len(selected) > 0:
            add(bucket[:10])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(r["path"] for r in selected) + "\n", encoding="utf-8")
    print(f"total_selected={len(selected)}", flush=True)
    print(f"sample_paths={out}", flush=True)
    return 0


def _year(rec: dict) -> int | None:
    mtime = rec.get("mtime")
    if not mtime:
        return None
    import datetime

    return datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).year


def _percentiles(values: list[float], points=(50, 90, 95, 99, 100)) -> dict:
    if not values:
        return {}
    values = sorted(values)
    out = {}
    for p in points:
        idx = min(len(values) - 1, int(round(p / 100.0 * (len(values) - 1))))
        out[f"p{p}"] = values[idx]
    return out


def _sanity_flags(nmap, features: dict) -> dict:
    flags: dict[str, Any] = {}
    non_finite = 0
    large = 0
    max_abs = 0.0
    for value in features.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value != value or value in (float("inf"), float("-inf")):
                non_finite += 1
            else:
                max_abs = max(max_abs, abs(float(value)))
                if abs(float(value)) > 1e9:
                    large += 1
    flags["non_finite_count"] = non_finite
    flags["large_value_count"] = large
    flags["max_abs_value"] = max_abs
    flags["negative_delta_count"] = sum(
        1 for o in nmap.objects if o.delta_time_ms is not None and o.delta_time_ms < 0
    )
    flags["negative_slider_duration_count"] = sum(
        1 for o in nmap.objects if o.slider_duration_ms is not None and o.slider_duration_ms < 0
    )
    flags["nonpositive_bpm_count"] = sum(1 for o in nmap.objects if o.local_bpm <= 0)
    flags["nonpositive_sv_count"] = sum(1 for o in nmap.objects if o.local_sv <= 0)
    return flags


def cmd_qa(args: argparse.Namespace) -> int:
    paths = [line.strip() for line in Path(args.paths).read_text(encoding="utf-8").splitlines() if line.strip()]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    start = time.time()
    for idx, path in enumerate(paths, 1):
        rec: dict[str, Any] = {
            "path": path,
            "ok": False,
            "stage": None,
            "error_type": None,
            "error": None,
            "parse_latency_ms": None,
            "total_latency_ms": None,
        }
        t0 = time.perf_counter()
        try:
            beatmap = parse_osu_file(path)
            rec["parse_latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
            rec["stage"] = "parse"
            nmap = normalize(beatmap)
            rec["stage"] = "normalize"
            features = FeatureExtractor().extract(nmap)
            rec["stage"] = "extract"
            profile = DeterministicBaselineProfiler(run_weak_labels=True).analyze_map(
                beatmap, source_label=path
            )
            rec["stage"] = "segment/serialize"
            json.dumps(profile, ensure_ascii=False, allow_nan=False)
            rec["ok"] = True
            rec["object_count"] = len(nmap.objects)
            rec["timing_count"] = len(nmap.beatmap.timing_points)
            rec["slider_count"] = sum(1 for o in nmap.objects if o.raw.object_type == "slider")
            rec["feature_count"] = len(features)
            rec["segment_count"] = len(profile["segments"])
            rec["sanity"] = _sanity_flags(nmap, features)
        except Exception as exc:  # noqa: BLE001 - record any failure for triage
            rec["ok"] = False
            rec["error_type"] = type(exc).__name__
            rec["error"] = str(exc)[:300]
            if rec["stage"] is None:
                rec["stage"] = "parse"
        rec["total_latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        results.append(rec)
        if idx % 500 == 0:
            print(f"qa progress {idx}/{len(paths)} elapsed={time.time()-start:.1f}s", flush=True)

    with out.open("w", encoding="utf-8") as fh:
        for rec in results:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    failures = [r for r in results if not r["ok"]]
    failure_types = Counter((r["stage"], r["error_type"]) for r in failures)
    sane_ok = sum(1 for r in results if r["ok"] and not _has_sanity_issues(r["sanity"]))
    print("QA_SUMMARY")
    print(f"total={len(results)} ok={len(results)-len(failures)} failed={len(failures)}")
    print(f"failure_types={dict(failure_types)}")
    print(f"files_without_sanity_issues={sane_ok}")
    print(f"with_non_finite={sum(1 for r in results if r.get('sanity', {}).get('non_finite_count', 0) > 0)}")
    print(f"with_negative_delta={sum(1 for r in results if r.get('sanity', {}).get('negative_delta_count', 0) > 0)}")
    print(
        "with_negative_slider_duration="
        f"{sum(1 for r in results if r.get('sanity', {}).get('negative_slider_duration_count', 0) > 0)}"
    )
    print(
        "with_nonpositive_bpm="
        f"{sum(1 for r in results if r.get('sanity', {}).get('nonpositive_bpm_count', 0) > 0)}"
    )
    print(
        "with_nonpositive_sv="
        f"{sum(1 for r in results if r.get('sanity', {}).get('nonpositive_sv_count', 0) > 0)}"
    )
    print(f"with_large_values={sum(1 for r in results if r.get('sanity', {}).get('large_value_count', 0) > 0)}")
    parse_lat = [r["parse_latency_ms"] for r in results if r["parse_latency_ms"] is not None]
    total_lat = [r["total_latency_ms"] for r in results]
    print(f"parse_latency_ms={_percentiles(parse_lat)}")
    print(f"total_latency_ms={_percentiles(total_lat)}")
    print(f"qa_output={out}")
    return 0


def _has_sanity_issues(sanity: dict) -> bool:
    return bool(
        sanity.get("non_finite_count")
        or sanity.get("negative_delta_count")
        or sanity.get("negative_slider_duration_count")
    )


def cmd_manifest(args: argparse.Namespace) -> int:
    scan = [json.loads(line) for line in Path(args.scan).read_text(encoding="utf-8").splitlines() if line.strip()]
    scan_by_path = {r["path"]: r for r in scan}
    std_paths = [r["path"] for r in scan if _standard(r)]
    print(f"standard_files={len(std_paths)}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    failures_path = Path(args.failures) if args.failures else out.with_suffix(".failures.jsonl")
    stats_path = Path(args.stats) if args.stats else out.with_suffix(".stats.json")

    failures: list[dict] = []
    success = 0
    stats: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "total_standard": len(std_paths),
        "success": 0,
        "failures": 0,
        "format_version": Counter(),
        "mtime_year": Counter(),
        "object_count": [],
        "timing_count": [],
        "green_count": [],
        "slider_count": [],
        "slider_ratio": [],
        "duration_ms": [],
        "ar": [],
        "od": [],
        "cs": [],
        "hp": [],
        "bpm_max": [],
    }

    start = time.time()
    with out.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "schema_version": MANIFEST_SCHEMA_VERSION,
                    "parser_version": PARSER_VERSION,
                    "feature_version": FEATURE_VERSION,
                    "samples": [],
                },
                ensure_ascii=False,
            )[:-2]
            + "\n"
        )
        first = True
        for idx, path in enumerate(std_paths, 1):
            scan_rec = scan_by_path.get(path, {})
            try:
                with open(path, "rb") as fh_raw:
                    data = fh_raw.read()
                digest = "sha256:" + hashlib.sha256(data).hexdigest()
                beatmap = parse_osu_file(path)
                if beatmap.mode != 0:
                    raise OsuParseError(
                        f"only osu!standard (mode 0) is supported, got mode {beatmap.mode}"
                    )
                rel_path = scan_rec.get("rel_path") or os.path.relpath(path, args.root).replace("\\", "/")
                folder = scan_rec.get("folder") or os.path.dirname(rel_path)
                metadata = beatmap.metadata
                difficulty = beatmap.difficulty
                objects = beatmap.hit_objects
                slider_count = sum(1 for o in objects if o.object_type == "slider")
                bpm_values = [
                    tp.bpm for tp in beatmap.timing_points if tp.uninherited and tp.bpm is not None and tp.bpm > 0
                ]
                beatmap_id = metadata.get("BeatmapID")
                beatmapset_id = metadata.get("BeatmapSetID")
                beatmap_id = beatmap_id if isinstance(beatmap_id, int) and beatmap_id > 0 else None
                beatmapset_id = beatmapset_id if isinstance(beatmapset_id, int) and beatmapset_id > 0 else None
                sample_id = rel_path[:-4] if rel_path.endswith(".osu") else rel_path
                record = {
                    "sample_id": sample_id,
                    "source": "local_osu_songs",
                    "relative_path": rel_path,
                    "reference": rel_path,
                    "sha256": digest,
                    "checksum": digest,
                    "beatmap_id": beatmap_id,
                    "beatmapset_id": beatmapset_id,
                    "beatmapset_id_source": "metadata" if beatmapset_id is not None else "none",
                    "local_set_group": folder,
                    "artist": metadata.get("Artist", ""),
                    "title": metadata.get("Title", ""),
                    "creator": metadata.get("Creator", ""),
                    "mapper": metadata.get("Creator", ""),
                    "version": metadata.get("Version", ""),
                    "mode": 0,
                    "format_version": beatmap.format_version,
                    "parser_version": PARSER_VERSION,
                    "feature_version": FEATURE_VERSION,
                    "metadata": {
                        "difficulty": {
                            "AR": difficulty.get("ApproachRate"),
                            "OD": difficulty.get("OverallDifficulty"),
                            "CS": difficulty.get("CircleSize"),
                            "HP": difficulty.get("HPDrainRate"),
                            "SliderMultiplier": difficulty.get("SliderMultiplier"),
                            "SliderTickRate": difficulty.get("SliderTickRate"),
                        },
                        "counts": {
                            "objects": len(objects),
                            "timing_points": len(beatmap.timing_points),
                            "sliders": slider_count,
                        },
                        "duration_ms": (
                            max(o.end_time_ms() for o in objects) - objects[0].time_ms if objects else None
                        ),
                        "bpm_min": min(bpm_values) if bpm_values else None,
                        "bpm_max": max(bpm_values) if bpm_values else None,
                        "repeats_max": max((o.slider_slides or 0) for o in objects if o.object_type == "slider")
                        if any(o.object_type == "slider" for o in objects)
                        else 0,
                    },
                }
                if not first:
                    fh.write(",\n")
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                first = False
                success += 1
                stats["format_version"][beatmap.format_version] += 1
                year = _year(scan_rec)
                if year is not None:
                    stats["mtime_year"][year] += 1
                stats["object_count"].append(len(objects))
                stats["timing_count"].append(len(beatmap.timing_points))
                stats["green_count"].append(
                    sum(1 for tp in beatmap.timing_points if not tp.uninherited)
                )
                stats["slider_count"].append(slider_count)
                stats["slider_ratio"].append(slider_count / len(objects) if objects else 0.0)
                stats["duration_ms"].append(
                    max(o.end_time_ms() for o in objects) - objects[0].time_ms if objects else 0.0
                )
                for key, bucket in (
                    ("ar", "ApproachRate"),
                    ("od", "OverallDifficulty"),
                    ("cs", "CircleSize"),
                    ("hp", "HPDrainRate"),
                ):
                    value = difficulty.get(bucket)
                    if isinstance(value, (int, float)):
                        stats[key].append(float(value))
                if bpm_values:
                    stats["bpm_max"].append(max(bpm_values))
            except Exception as exc:  # noqa: BLE001 - triage then fix
                failures.append(
                    {
                        "path": path,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    }
                )
            if idx % 20000 == 0:
                print(f"manifest progress {idx}/{len(std_paths)} elapsed={time.time()-start:.1f}s", flush=True)
        fh.write("\n]}\n")

    stats["success"] = success
    stats["failures"] = len(failures)
    for key in (
        "object_count",
        "timing_count",
        "green_count",
        "slider_count",
        "slider_ratio",
        "duration_ms",
        "ar",
        "od",
        "cs",
        "hp",
        "bpm_max",
    ):
        values = sorted(stats[key])
        if values:
            stats[key] = {
                "min": values[0],
                "max": values[-1],
                **_percentiles(values),
            }
        else:
            stats[key] = {}
    stats["format_version"] = dict(sorted(stats["format_version"].items()))
    stats["mtime_year"] = {str(k): v for k, v in sorted(stats["mtime_year"].items())}
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    failures_path.write_text(
        "\n".join(json.dumps(f, ensure_ascii=False, sort_keys=True) for f in failures)
        + ("\n" if failures else ""),
        encoding="utf-8",
    )
    print("MANIFEST_SUMMARY")
    print(f"standard_files={len(std_paths)} success={success} failures={len(failures)}")
    print(f"manifest={out} size_mb={out.stat().st_size / 1e6:.1f}")
    print(f"failures={failures_path} stats={stats_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="corpus_pipeline", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="lenient full-corpus scan")
    scan.add_argument("--list", required=True, help="path list file (UTF-16 or UTF-8)")
    scan.add_argument("--root", required=True, help="Songs root")
    scan.add_argument("--out", required=True, help="output JSONL")
    scan.add_argument("--workers", type=int, default=8)

    select = sub.add_parser("select", help="build adversarial sample")
    select.add_argument("--scan", required=True)
    select.add_argument("--out", required=True)
    select.add_argument("--seed", type=int, default=42)
    select.add_argument("--max-total", type=int, default=3000)

    qa = sub.add_parser("qa", help="strict parser QA")
    qa.add_argument("--paths", required=True)
    qa.add_argument("--out", required=True)

    manifest = sub.add_parser("manifest", help="full standard manifest")
    manifest.add_argument("--scan", required=True)
    manifest.add_argument("--root", required=True)
    manifest.add_argument("--out", required=True)
    manifest.add_argument("--failures")
    manifest.add_argument("--stats")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "select":
        return cmd_select(args)
    if args.command == "qa":
        return cmd_qa(args)
    if args.command == "manifest":
        return cmd_manifest(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
