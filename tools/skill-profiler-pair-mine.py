#!/usr/bin/env python3
"""Deterministic high-information pair mining for the SKILL_PROFILER label-efficiency audit.

Phases:
  D  formal pair re-audit (recompute from raw .osu and compare against package/construct stats)
  E  candidate classes P1..P10 from the rich segment pool
  F  matching frontier (target separation vs standardised covariate distance)
  G  TOP_25 / TOP_50 / TOP_100 / TOP_200 label queues with why-reasons

The script is intentionally deterministic: fixed sorting, fixed seeds, no
randomised algorithms except seeded numpy RNGs where noted.  It only writes
the requested docs JSON (and optionally a candidate-pool temp file).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

try:
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler
except Exception as _exc:  # pragma: no cover - guarded fallback
    NearestNeighbors = None
    StandardScaler = None
    _SKLEARN_ERROR = _exc
else:
    _SKLEARN_ERROR = None


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REPO = ROOT
DEFAULT_OUT = os.path.join(DEFAULT_REPO, "docs", "SKILL_PROFILER_HIGH_INFORMATION_PAIRS_V01.json")
DEFAULT_POOL_OUT = os.path.join(DEFAULT_REPO, "tmp", "label_audit", "candidate_pool_v01.json")
DEFAULT_TOP_PER_CLASS = 20
DEFAULT_SEED = 20260814


# ---------------------------------------------------------------------------
# helpers

def jload(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def jwrite(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def percentile_sorted(sorted_vals: list[float], q: float) -> float:
    """Nearest-rank percentile used by the existing construct-stat extractor."""
    if not sorted_vals:
        raise ValueError("empty values")
    idx = min(len(sorted_vals) - 1, int(math.ceil(q * len(sorted_vals))) - 1)
    return sorted_vals[idx]


def quantile(a: np.ndarray, q: float) -> float:
    return float(np.quantile(a, q))


def robust_z(x: np.ndarray) -> np.ndarray:
    """Robust standardisation: (x - median) / (IQR / 1.349), std fallback.

    IQR/1.349 is the Gaussian-equivalent robust scale (matches MAD*1.4826),
    so extreme values do not dominate the standardised differences.
    """
    med = np.median(x)
    iqr = np.subtract(*np.percentile(x, [75, 25]))
    if iqr <= 1e-12:
        iqr = float(np.std(x))
    if iqr <= 1e-12:
        iqr = 1.0
    scale = iqr / 1.349
    if scale <= 1e-12:
        scale = 1.0
    return (x - med) / scale


def stable_unique_pairs(pairs: Iterable[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    seen = set()
    out = []
    for pair in pairs:
        key = pair[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(pair)
    return out


def pair_key(a: str, b: str) -> str:
    return "\x00".join(sorted((a, b)))


def sign_of(x: float, eps: float = 1e-9) -> int:
    if x > eps:
        return 1
    if x < -eps:
        return -1
    return 0


# ---------------------------------------------------------------------------
# Phase D: formal re-audit

def nearest_rank_p90(values: list[float]) -> float:
    return percentile_sorted(sorted(values), 0.90)


def formal_reaudit(repo: str, package_rel: str, construct_rel: str, feature_rel: str) -> dict:
    """Recompute the six formal probe sides from raw .osu and compare."""
    sys.path.insert(0, os.path.join(repo, "src"))
    from osu_skill_profiler.parser import parse_osu_file
    from osu_skill_profiler.signals.extractor import LocalSignalExtractor

    package_path = os.path.join(repo, package_rel)
    package = jload(package_path)
    construct = jload(os.path.join(repo, construct_rel)).get("segments", {})

    feat_map: dict[str, dict] = {}
    with open(os.path.join(repo, feature_rel), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            feat_map[rec["checksum"]] = rec

    entries: list[dict] = []

    for probe in package["probes"]:
        probe_id = probe["probe_id"]
        for question_id, question_key in (
            ("PATH", "path"),
            ("TIME", "time"),
        ):
            sides = {}
            for side_name in ("side_a", "side_b"):
                side = probe[side_name]
                csum = side["map_checksum"]
                feat = feat_map.get(csum)
                if feat is None:
                    sides[side_name] = {
                        "status": "MISMATCH",
                        "error": f"feature_qa record missing for {csum}",
                        "map_checksum": csum,
                    }
                    continue
                path = feat["path_abs"]
                if not os.path.exists(path):
                    sides[side_name] = {
                        "status": "MISMATCH",
                        "error": f".osu path missing: {path}",
                        "map_checksum": csum,
                    }
                    continue
                recomputed_checksum = file_sha256(path)
                checksum_ok = recomputed_checksum == csum

                beatmap = parse_osu_file(path)
                rows = LocalSignalExtractor().extract(beatmap)["objects"]
                seg_start = float(side["segment_start_ms"])
                seg_end = float(side["segment_end_ms"])
                sliders = [
                    row for row in rows
                    if row["ls.object_type"] == "slider"
                    and seg_start <= row["ls.start_time_ms"] < seg_end
                ]
                path_vals = sorted(
                    row["ls.lazy_travel_distance_cs_normalised"]
                    for row in sliders
                    if isinstance(row.get("ls.lazy_travel_distance_cs_normalised"), (int, float))
                    and math.isfinite(float(row["ls.lazy_travel_distance_cs_normalised"]))
                )
                time_vals = sorted(
                    row["ls.slider_total_duration_ms"]
                    for row in sliders
                    if isinstance(row.get("ls.slider_total_duration_ms"), (int, float))
                    and math.isfinite(float(row["ls.slider_total_duration_ms"]))
                )
                lazy_time_vals = sorted(
                    row["ls.lazy_travel_time_ms"]
                    for row in sliders
                    if isinstance(row.get("ls.lazy_travel_time_ms"), (int, float))
                    and math.isfinite(float(row["ls.lazy_travel_time_ms"]))
                )

                computed = {
                    "path_p90": nearest_rank_p90(path_vals) if path_vals else None,
                    "path_max": path_vals[-1] if path_vals else None,
                    "path_median": percentile_sorted(path_vals, 0.50) if path_vals else None,
                    "path_total": sum(path_vals) if path_vals else None,
                    "time_p90": nearest_rank_p90(time_vals) if time_vals else None,
                    "time_max": time_vals[-1] if time_vals else None,
                    "time_median": percentile_sorted(time_vals, 0.50) if time_vals else None,
                    "time_total": sum(time_vals) if time_vals else None,
                    "lazy_travel_time_p90": nearest_rank_p90(lazy_time_vals) if lazy_time_vals else None,
                    "lazy_travel_time_max": lazy_time_vals[-1] if lazy_time_vals else None,
                    "n_sliders": len(sliders),
                    "n_path_values": len(path_vals),
                    "n_time_values": len(time_vals),
                    "n_lazy_time_values": len(lazy_time_vals),
                }

                ckey = f"{csum}::{side['segment_index']}"
                construct_side = construct.get(ckey, {})
                references = {
                    "package_slider_only_path_p90": side.get("slider_only_path_p90"),
                    "package_slider_only_path_max": side.get("slider_only_path_max"),
                    "package_path_p90_zero_inclusive": side.get("path_p90"),
                    "package_seg_max": side.get("seg_max"),
                    "package_follow_duration_p90_ms": side.get("follow_duration_p90_ms"),
                    "package_follow_duration_max_ms": side.get("follow_duration_max_ms"),
                    "package_track_time_p90_ms": side.get("track_time_p90_ms"),
                    "construct_path_p90": construct_side.get("path_slider_only", {}).get("p90"),
                    "construct_path_max": construct_side.get("path_slider_only", {}).get("max"),
                    "construct_time_p90": construct_side.get("time_slider_only", {}).get("p90"),
                    "construct_time_max": construct_side.get("time_slider_only", {}).get("max"),
                    "construct_track_time_p90": construct_side.get("track_time_slider_only", {}).get("p90"),
                    "construct_track_time_max": construct_side.get("track_time_slider_only", {}).get("max"),
                }

                def cmp(computed_val: float | None, reference_val: float | None, tol: float = 0.0011) -> str | None:
                    if computed_val is None or reference_val is None:
                        return None
                    if not math.isfinite(float(reference_val)):
                        return None
                    diff = abs(float(computed_val) - float(reference_val))
                    return "OK" if diff <= tol else f"DIFF {diff:.6g}"

                comparisons = {
                    "checksum_sha256": {
                        "recomputed": recomputed_checksum,
                        "package": csum,
                        "status": "OK" if checksum_ok else "MISMATCH",
                    },
                    "path_exists": "OK",
                    "path_p90_vs_construct": cmp(computed["path_p90"], references["construct_path_p90"]),
                    "path_p90_vs_package_slider_only": cmp(computed["path_p90"], references["package_slider_only_path_p90"]),
                    "path_max_vs_construct": cmp(computed["path_max"], references["construct_path_max"]),
                    "path_max_vs_package_seg_max": cmp(computed["path_max"], references["package_seg_max"]),
                    "time_p90_vs_construct": cmp(computed["time_p90"], references["construct_time_p90"]),
                    "time_p90_vs_package": cmp(computed["time_p90"], references["package_follow_duration_p90_ms"]),
                    "time_max_vs_construct": cmp(computed["time_max"], references["construct_time_max"]),
                    "time_max_vs_package": cmp(computed["time_max"], references["package_follow_duration_max_ms"]),
                    "lazy_travel_time_p90_vs_construct": cmp(computed["lazy_travel_time_p90"], references["construct_track_time_p90"]),
                    "lazy_travel_time_p90_vs_package": cmp(computed["lazy_travel_time_p90"], references["package_track_time_p90_ms"]),
                    "lazy_travel_time_max_vs_construct": cmp(computed["lazy_travel_time_max"], references["construct_track_time_max"]),
                }
                bad = [v for v in comparisons.values() if isinstance(v, str) and v.startswith(("MISMATCH", "DIFF"))]
                sides[side_name] = {
                    "status": "REPRODUCED" if checksum_ok and not bad else "MISMATCH",
                    "probe_id": probe_id,
                    "side": side_name,
                    "map_checksum": csum,
                    "path_abs": path,
                    "segment_index": side["segment_index"],
                    "segment_start_ms": side["segment_start_ms"],
                    "segment_end_ms": side["segment_end_ms"],
                    "n_sliders": computed["n_sliders"],
                    "computed": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in computed.items()},
                    "references": references,
                    "comparisons": comparisons,
                    "checksum_ok": checksum_ok,
                }

            side_a = sides["side_a"]
            side_b = sides["side_b"]
            statuses = {s.get("status") for s in (side_a, side_b)}
            overall = "REPRODUCED" if statuses == {"REPRODUCED"} else "MISMATCH"
            entries.append({
                "probe_id": probe_id,
                "question": f"Q-V02-SLIDER-{question_key.upper()}",
                "status": overall,
                "side_a": side_a,
                "side_b": side_b,
                "drift_report": {
                    "drift_detected": overall != "REPRODUCED",
                    "notes": [
                        f"{side_name}: {s.get('status')} (n_sliders={s.get('n_sliders')})"
                        for side_name, s in (("side_a", side_a), ("side_b", side_b))
                    ],
                },
            })

    return {
        "audit_version": "SKILL_PROFILER_LABEL_EFFICIENCY_AUDIT_V01",
        "phase": "D",
        "package_path": package_rel,
        "construct_stats_path": construct_rel,
        "feature_qa_path": feature_rel,
        "entries": entries,
    }


# ---------------------------------------------------------------------------
# pool building

def build_pool(repo: str, construct_rel: str, feature_rel: str, split_rel: str, evidence_rel: str) -> tuple[list[dict], dict]:
    """Build the rich segment pool."""
    construct = jload(os.path.join(repo, construct_rel))
    segments = construct.get("segments", {})

    feat_map: dict[str, dict] = {}
    with open(os.path.join(repo, feature_rel), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            feat_map[rec["checksum"]] = rec

    split_map: dict[str, dict] = {}
    with open(os.path.join(repo, split_rel), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            split_map[rec["map_checksum"]] = rec

    ws_map: dict[str, dict] = {}
    with open(os.path.join(repo, evidence_rel), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("rule", {}).get("id") != "ws01.local.slider_travel_segment":
                continue
            if rec.get("entity", {}).get("scope") != "SEGMENT":
                continue
            ent = rec["entity"]
            key = f"{ent['map_checksum']}::{ent['segment_index']}"
            ws_map[key] = {
                "status": rec.get("status"),
                "strength": rec.get("strength"),
                "direction": rec.get("value", {}).get("direction") if isinstance(rec.get("value"), dict) else None,
                "abstention_reason": rec.get("abstention_reason"),
                "diagnostics": rec.get("diagnostics", []),
            }

    pool: list[dict] = []
    for key, seg in segments.items():
        csum = seg["map_checksum"]
        feat = feat_map.get(csum, {})
        split_rec = split_map.get(csum, {})
        path_stats = seg.get("path_slider_only", {}) or {}
        time_stats = seg.get("time_slider_only", {}) or {}
        track_stats = seg.get("track_time_slider_only", {}) or {}
        ffeatures = feat.get("features", {}) or {}

        object_count = feat.get("object_count")
        slider_ratio = feat.get("slider_ratio")
        if object_count is None:
            object_count = ffeatures.get("temporal.object_count")
        if slider_ratio is None:
            slider_ratio = ffeatures.get("slider.slider_ratio")

        repeat_total = ffeatures.get("slider.repeat_count_total")
        span_total = ffeatures.get("slider.span_count_total")
        repeat_max = ffeatures.get("slider.repeat_count_max")
        span_max = ffeatures.get("slider.span_count_max")

        n_sliders = seg.get("n_slider_rows", 0)
        n_sliders_map_est = None
        if isinstance(object_count, (int, float)) and isinstance(slider_ratio, (int, float)):
            n_sliders_map_est = max(1.0, float(object_count) * float(slider_ratio))
        repeat_load = None
        span_load = None
        if repeat_total is not None and n_sliders_map_est:
            repeat_load = float(repeat_total) / n_sliders_map_est
        if span_total is not None and n_sliders_map_est:
            span_load = float(span_total) / n_sliders_map_est

        ws = ws_map.get(key, {})

        def fnum(name: str):
            v = feat.get(name)
            if v is None:
                v = ffeatures.get(name)
            return float(v) if isinstance(v, (int, float)) and math.isfinite(float(v)) else None

        def fnum_stats(stats: dict, name: str):
            v = stats.get(name)
            return float(v) if isinstance(v, (int, float)) and math.isfinite(float(v)) else None

        row = {
            "key": key,
            "map_checksum": csum,
            "segment_index": seg.get("segment_index"),
            "n_slider_rows": int(n_sliders) if isinstance(n_sliders, (int, float)) else 0,
            "path_p90": fnum_stats(path_stats, "p90"),
            "path_max": fnum_stats(path_stats, "max"),
            "path_median": fnum_stats(path_stats, "median"),
            "path_total": fnum_stats(path_stats, "total"),
            "time_p90": fnum_stats(time_stats, "p90"),
            "time_max": fnum_stats(time_stats, "max"),
            "time_median": fnum_stats(time_stats, "median"),
            "time_total": fnum_stats(time_stats, "total"),
            "track_time_p90": fnum_stats(track_stats, "p90"),
            "track_time_max": fnum_stats(track_stats, "max"),
            "bpm_max": fnum("bpm_max"),
            "cs": fnum("cs"),
            "ar": fnum("ar"),
            "od": fnum("od"),
            "duration_ms": fnum("duration_ms"),
            "object_count": object_count if isinstance(object_count, (int, float)) else None,
            "slider_ratio": slider_ratio if isinstance(slider_ratio, (int, float)) else None,
            "split": split_rec.get("split"),
            "set_group_key": split_rec.get("set_group_key"),
            "mapper_group_key": split_rec.get("mapper_group_key"),
            "sample_id": feat.get("sample_id"),
            "path_abs": feat.get("path_abs"),
            "segment_count": feat.get("segment_count"),
            "repeat_count_total": repeat_total if isinstance(repeat_total, (int, float)) else None,
            "span_count_total": span_total if isinstance(span_total, (int, float)) else None,
            "repeat_count_max": repeat_max if isinstance(repeat_max, (int, float)) else None,
            "span_count_max": span_max if isinstance(span_max, (int, float)) else None,
            "n_sliders_map_est": n_sliders_map_est,
            "repeat_load": repeat_load,
            "span_load": span_load,
            "ws_status": ws.get("status"),
            "ws_strength": ws.get("strength"),
            "ws_direction": ws.get("direction"),
            "ws_abstention_reason": ws.get("abstention_reason"),
            "ws_diagnostics": ws.get("diagnostics", []),
        }
        pool.append(row)

    # Deterministic ordering by key.
    pool.sort(key=lambda r: r["key"])
    return pool, {"segments": len(pool), "maps": len({r["map_checksum"] for r in pool})}


# ---------------------------------------------------------------------------
# candidate generation

@dataclass
class CandidateSet:
    name: str
    definition: str
    candidates: list[dict]


def _num_vec(pool: list[dict], name: str, default: float = np.nan) -> np.ndarray:
    return np.array([r.get(name) if isinstance(r.get(name), (int, float)) and math.isfinite(float(r[name])) else default for r in pool], dtype=float)


def _finite_mask(*arrays: np.ndarray) -> np.ndarray:
    mask = np.ones(len(arrays[0]), dtype=bool)
    for a in arrays:
        mask &= np.isfinite(a)
    return mask


def _neighbor_indices_1d(sorted_indices: np.ndarray, values: np.ndarray, k: int) -> list[list[int]]:
    """For each position in sorted_indices, return up to k nearest other positions."""
    n = len(sorted_indices)
    out: list[list[int]] = []
    for pos in range(n):
        left = pos - 1
        right = pos + 1
        neigh: list[int] = []
        while len(neigh) < k and (left >= 0 or right < n):
            if left >= 0 and (right >= n or abs(values[sorted_indices[pos]] - values[sorted_indices[left]]) <= abs(values[sorted_indices[right]] - values[sorted_indices[pos]])):
                neigh.append(left)
                left -= 1
            elif right < n:
                neigh.append(right)
                right += 1
        out.append(neigh)
    return out


def _add_pair(
    acc: dict[str, tuple],
    key_i: str,
    key_j: str,
    rec_i: dict,
    rec_j: dict,
    score: float,
    class_name: str,
    z_path_i: float,
    z_path_j: float,
    z_time_i: float,
    z_time_j: float,
    extra: dict | None = None,
) -> None:
    k = pair_key(key_i, key_j)
    if k in acc:
        return
    # Human judges compare two different beatmaps; never pair a segment with
    # another segment from the same map.
    if rec_i.get("map_checksum") == rec_j.get("map_checksum"):
        return
    zp_diff = z_path_i - z_path_j
    zt_diff = z_time_i - z_time_j
    extra = dict(extra or {})
    confound_penalty = float(extra.get("confound_penalty", 0.0))
    same_set = bool(
        rec_i.get("set_group_key") is not None
        and rec_j.get("set_group_key") is not None
        and rec_i.get("set_group_key") == rec_j.get("set_group_key")
    )
    same_mapper = bool(
        rec_i.get("mapper_group_key") is not None
        and rec_j.get("mapper_group_key") is not None
        and rec_i.get("mapper_group_key") == rec_j.get("mapper_group_key")
    )
    diversity_penalty = (0.35 if same_set else 0.0) + (0.20 if same_mapper else 0.0)
    final_score = float(score) - confound_penalty - diversity_penalty
    extra["confound_penalty"] = confound_penalty
    extra["diversity_penalty"] = diversity_penalty
    extra["same_set_group"] = same_set
    extra["same_mapper_group"] = same_mapper
    acc[k] = (
        final_score,
        key_i,
        key_j,
        rec_i,
        rec_j,
        class_name,
        zp_diff,
        zt_diff,
        extra,
    )


def _candidate_records(
    acc: dict[str, tuple],
    pool_lookup: dict[str, dict],
    class_name: str,
    top_k: int,
    score_desc: bool = True,
    excluded_keys: set[str] | None = None,
    max_same_map_pair: int | None = None,
) -> list[dict]:
    excluded_keys = excluded_keys or set()
    items = [v for k, v in acc.items() if k not in excluded_keys]
    items.sort(key=lambda v: (round(float(v[0]), 12), v[1], v[2]), reverse=score_desc)

    out: list[dict] = []
    map_pair_count: dict[str, int] = {}
    for item in items:
        if len(out) >= top_k:
            break
        score, key_i, key_j, rec_i, rec_j, cname, zp_diff, zt_diff, extra = item
        map_pair = pair_key(rec_i["map_checksum"], rec_j["map_checksum"])
        if max_same_map_pair is not None:
            if map_pair_count.get(map_pair, 0) >= max_same_map_pair:
                continue
        out.append(_make_candidate(score, key_i, key_j, rec_i, rec_j, class_name, zp_diff, zt_diff, extra))
        map_pair_count[map_pair] = map_pair_count.get(map_pair, 0) + 1
    return out


def _make_candidate(
    score: float,
    key_i: str,
    key_j: str,
    rec_i: dict,
    rec_j: dict,
    class_name: str,
    zp_diff: float,
    zt_diff: float,
    extra: dict | None = None,
) -> dict:
    extra = extra or {}
    path_diff = None
    time_diff = None
    if rec_i.get("path_p90") is not None and rec_j.get("path_p90") is not None:
        path_diff = float(rec_i["path_p90"]) - float(rec_j["path_p90"])
    if rec_i.get("time_p90") is not None and rec_j.get("time_p90") is not None:
        time_diff = float(rec_i["time_p90"]) - float(rec_j["time_p90"])
    return {
        "pair_key": pair_key(key_i, key_j),
        "class": class_name,
        "score": float(score),
        "side_a": _side_view(rec_i),
        "side_b": _side_view(rec_j),
        "path_p90_diff": path_diff,
        "time_p90_diff": time_diff,
        "path_z_diff": float(zp_diff),
        "time_z_diff": float(zt_diff),
        "path_p90_diff_abs": abs(path_diff) if path_diff is not None else None,
        "time_p90_diff_abs": abs(time_diff) if time_diff is not None else None,
        "percentile_diff": extra.get("percentile_diff"),
        "covariate_distance": extra.get("covariate_distance"),
        "confound_indicators": extra.get("confound_indicators", []),
        "confound_penalty": extra.get("confound_penalty", 0.0),
        "diversity_penalty": extra.get("diversity_penalty", 0.0),
        "same_set_group": extra.get("same_set_group", False),
        "same_mapper_group": extra.get("same_mapper_group", False),
        "formal_probe": extra.get("formal_probe", False),
        "reasons": extra.get("reasons", []),
        "why": extra.get("why", []),
    }


def _side_view(rec: dict) -> dict:
    return {
        "key": rec.get("key"),
        "map_checksum": rec.get("map_checksum"),
        "segment_index": rec.get("segment_index"),
        "path_p90": rec.get("path_p90"),
        "path_max": rec.get("path_max"),
        "time_p90": rec.get("time_p90"),
        "time_max": rec.get("time_max"),
        "track_time_p90": rec.get("track_time_p90"),
        "track_time_max": rec.get("track_time_max"),
        "n_slider_rows": rec.get("n_slider_rows"),
        "bpm_max": rec.get("bpm_max"),
        "cs": rec.get("cs"),
        "ar": rec.get("ar"),
        "od": rec.get("od"),
        "duration_ms": rec.get("duration_ms"),
        "object_count": rec.get("object_count"),
        "slider_ratio": rec.get("slider_ratio"),
        "split": rec.get("split"),
        "set_group_key": rec.get("set_group_key"),
        "mapper_group_key": rec.get("mapper_group_key"),
        "repeat_load": rec.get("repeat_load"),
        "span_load": rec.get("span_load"),
        "ws_status": rec.get("ws_status"),
        "ws_strength": rec.get("ws_strength"),
        "ws_direction": rec.get("ws_direction"),
        "ws_abstention_reason": rec.get("ws_abstention_reason"),
    }


def _classify_formal(pool_lookup: dict[str, dict], formal_keys: set[str]) -> None:
    pass


def _confound_indicators(rec_i: dict, rec_j: dict, zp_diff: float, zt_diff: float, path_diff: float | None, time_diff: float | None) -> list[str]:
    inds: list[str] = []
    for name, label in (("bpm_max", "bpm"), ("cs", "cs"), ("ar", "ar"), ("od", "od"), ("duration_ms", "duration"), ("object_count", "object_count"), ("slider_ratio", "slider_ratio")):
        a = rec_i.get(name)
        b = rec_j.get(name)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            denom = max(abs(float(a)), abs(float(b)), 1e-9)
            if abs(float(a) - float(b)) / denom > 0.25:
                inds.append(f"{label}_diff")
    if abs(rec_i.get("n_slider_rows", 0) - rec_j.get("n_slider_rows", 0)) >= 3:
        inds.append("n_slider_rows_diff>=3")
    if rec_i.get("split") != rec_j.get("split"):
        inds.append("split_diff")
    return inds


def _base_extra(
    rec_i: dict,
    rec_j: dict,
    zp_diff: float,
    zt_diff: float,
    path_diff: float | None,
    time_diff: float | None,
    pool_lookup: dict[str, dict],
    formal_keys: set[str],
    pct_path_i: float | None,
    pct_path_j: float | None,
    pct_time_i: float | None,
    pct_time_j: float | None,
) -> dict:
    formal = rec_i["key"] in formal_keys and rec_j["key"] in formal_keys
    pct_diff = None
    if None not in (pct_path_i, pct_path_j, pct_time_i, pct_time_j):
        pct_diff = {
            "path_percentile_diff": round(pct_path_i - pct_path_j, 6),
            "time_percentile_diff": round(pct_time_i - pct_time_j, 6),
            "path_percentile_side_a": round(pct_path_i, 6),
            "path_percentile_side_b": round(pct_path_j, 6),
            "time_percentile_side_a": round(pct_time_i, 6),
            "time_percentile_side_b": round(pct_time_j, 6),
        }
    confounds = _confound_indicators(rec_i, rec_j, zp_diff, zt_diff, path_diff, time_diff)
    return {
        "percentile_diff": pct_diff,
        "confound_indicators": confounds,
        "confound_penalty": 0.30 * len(confounds),
        "formal_probe": formal,
        "reasons": [],
        "why": [],
    }


def _covariate_matrix(pool: list[dict], idxs: list[int] | None = None) -> np.ndarray:
    """Covariate matrix used for matching. Values are standardised inside this function."""
    names = ["bpm_max", "cs", "ar", "od", "duration_ms", "object_count", "slider_ratio", "n_slider_rows", "segment_index"]
    raw = []
    for name in names:
        col = []
        for r in pool:
            v = r.get(name)
            if isinstance(v, (int, float)) and math.isfinite(float(v)):
                col.append(float(v))
            else:
                col.append(np.nan)
        raw.append(np.array(col, dtype=float))
    raw = np.vstack(raw).T
    if idxs is not None:
        raw = raw[idxs]
    X = raw.copy()
    # log-scale heavy-tailed counts/durations, then median-impute, then standardise.
    for j, name in enumerate(names):
        if name in ("duration_ms", "object_count"):
            X[:, j] = np.log1p(np.where(np.isfinite(X[:, j]), X[:, j], 0.0))
    # median impute
    for j in range(X.shape[1]):
        col = X[:, j]
        med = np.median(col[np.isfinite(col)])
        col[~np.isfinite(col)] = med
    # standardize robustly so covariate distance is not dominated by extremes
    for j in range(X.shape[1]):
        col = X[:, j]
        X[:, j] = np.clip(robust_z(col), -5.0, 5.0)
    return X


def _cov_dist_vec(X: np.ndarray, i: int, j: int) -> float:
    return float(np.sqrt(np.sum((X[i] - X[j]) ** 2)))


def _neighbors_nn(X: np.ndarray, k: int) -> list[list[int]]:
    """Exact-ish kNN via sklearn NearestNeighbors (deterministic brute force)."""
    n = X.shape[0]
    k = min(k, n - 1)
    if k <= 0:
        return [[] for _ in range(n)]
    if NearestNeighbors is None:
        # fallback: brute force all-pairs
        out = []
        for i in range(n):
            d = np.sqrt(np.sum((X - X[i]) ** 2, axis=1))
            d[i] = np.inf
            out.append([int(x) for x in np.argsort(d)[:k]])
        return out
    nn = NearestNeighbors(n_neighbors=k + 1, algorithm="brute", metric="euclidean")
    nn.fit(X)
    dist, idx = nn.kneighbors(X)
    return [[int(x) for x in row[1:]] for row in idx]


# ---------------------------------------------------------------------------
# human-judgability filter

def filter_pool_for_human_judgability(pool: list[dict]) -> tuple[list[dict], dict]:
    """Filter the segment pool to pairs a human can realistically judge.

    Hard filters: n_slider_rows 4..30; path_p90 20..400; path_max <=600;
    time_p90 80..2500; time_max <=3000.  Both PATH/TIME p90 and max must be
    present and finite.  Pairs are then required to come from different maps;
    same-set / same-mapper pairs are penalised later in scoring.
    """
    usable: list[dict] = []
    excluded_reasons: dict[str, int] = {}
    for r in pool:
        def num(v):
            return isinstance(v, (int, float)) and math.isfinite(float(v))
        path_p90 = r.get("path_p90")
        path_max = r.get("path_max")
        time_p90 = r.get("time_p90")
        time_max = r.get("time_max")
        n_sliders = r.get("n_slider_rows")
        reasons = []
        if not (num(path_p90) and num(path_max) and num(time_p90) and num(time_max)):
            reasons.append("missing_path_or_time_stat")
        else:
            if not (4 <= int(n_sliders) <= 30):
                reasons.append("n_slider_rows_out_of_range")
            if not (20.0 <= float(path_p90) <= 400.0):
                reasons.append("path_p90_out_of_range")
            if float(path_max) > 600.0:
                reasons.append("path_max_out_of_range")
            if not (80.0 <= float(time_p90) <= 2500.0):
                reasons.append("time_p90_out_of_range")
            if float(time_max) > 3000.0:
                reasons.append("time_max_out_of_range")
        if reasons:
            for reason in reasons:
                excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
            continue
        usable.append(r)
    usable.sort(key=lambda r: r["key"])
    return usable, {
        "filtered_in": len(usable),
        "filtered_out": len(pool) - len(usable),
        "excluded_reasons": excluded_reasons,
        "criteria": {
            "n_slider_rows": [4, 30],
            "path_p90": [20.0, 400.0],
            "path_max": 600.0,
            "time_p90": [80.0, 2500.0],
            "time_max": 3000.0,
            "require_different_map_checksum": True,
            "prefer_different_set_or_mapper": "penalised in score",
        },
    }


# ---------------------------------------------------------------------------
# main mining

def mine_candidates(pool: list[dict], top_per_class: int, seed: int, reserve_multiplier: int = 5) -> dict:
    rng = np.random.default_rng(seed)
    reserve_per_class = max(top_per_class, top_per_class * reserve_multiplier)
    pool_lookup = {r["key"]: r for r in pool}

    usable, filter_meta = filter_pool_for_human_judgability(pool)
    if not usable:
        raise ValueError("no usable segments after human-judgability filter")

    keys = np.array([r["key"] for r in usable])
    path = np.array([r["path_p90"] for r in usable], dtype=float)
    time = np.array([r["time_p90"] for r in usable], dtype=float)
    z_path = robust_z(path)
    z_time = robust_z(time)
    c_same = z_path + z_time
    c_rev = z_path - z_time
    X = _covariate_matrix(usable)
    n = len(usable)

    # Percentile vectors for reporting
    pct_path = np.array([np.mean(path <= v) for v in path])
    pct_time = np.array([np.mean(time <= v) for v in time])
    path_p99 = np.quantile(path, 0.99)
    time_p99 = np.quantile(time, 0.99)
    nslider_p99 = np.quantile([r["n_slider_rows"] for r in usable], 0.99)
    seg_idx_p95 = np.quantile([r["segment_index"] for r in usable], 0.95)
    path_p50 = np.quantile(path, 0.50)

    formal_keys = _formal_probe_keys(pool_lookup)

    def extras(i: int, j: int, zp_diff: float, zt_diff: float) -> dict:
        ex = _base_extra(
            usable[i], usable[j], zp_diff, zt_diff,
            float(path[i] - path[j]), float(time[i] - time[j]),
            pool_lookup, formal_keys,
            float(pct_path[i]), float(pct_path[j]), float(pct_time[i]), float(pct_time[j]),
        )
        ex["covariate_distance"] = round(_cov_dist_vec(X, i, j), 6)
        return ex

    def add(acc: dict, i: int, j: int, score: float, class_name: str, zp_diff: float, zt_diff: float, extra: dict | None = None) -> None:
        _add_pair(acc, keys[i], keys[j], usable[i], usable[j], score, class_name,
                  float(z_path[i]), float(z_path[j]), float(z_time[i]), float(z_time[j]),
                  extra=extra)

    # ----- P1: PATH separated, TIME matched ------------------------------
    time_sorted = np.argsort(time, kind="stable")
    neigh_time = _neighbor_indices_1d(time_sorted, time[time_sorted], 40)
    p1: dict[str, tuple] = {}
    for pos_i in range(n):
        i = int(time_sorted[pos_i])
        for pos_j in neigh_time[pos_i]:
            j = int(time_sorted[pos_j])
            if i == j:
                continue
            zp = float(z_path[i] - z_path[j])
            zt = float(z_time[i] - z_time[j])
            if abs(zt) > 0.25:
                continue
            if abs(zp) < 1.5:
                continue
            score = abs(zp) - 0.5 * abs(zt)
            ex = extras(i, j, zp, zt)
            ex["score_definition"] = "|z_path_diff| - 0.5*|z_time_diff|; time matched |dz|<=0.25, path separated |dz|>=1.5; confound/diversity penalties applied by _add_pair"
            add(p1, i, j, score, "P1_PATH_SEPARATED_TIME_MATCHED", zp, zt, ex)
    p1_list = _candidate_records(p1, pool_lookup, "P1_PATH_SEPARATED_TIME_MATCHED", top_per_class, max_same_map_pair=1)
    p1_reserve = _candidate_records(p1, pool_lookup, "P1_PATH_SEPARATED_TIME_MATCHED", reserve_per_class, max_same_map_pair=3)
    _annotate_reasons(p1_list, "PATH separated while TIME is matched; isolates the slider PATH construct.")
    _annotate_reasons(p1_reserve, "PATH separated while TIME is matched; isolates the slider PATH construct.")

    # ----- P2: TIME separated, PATH matched -------------------------------
    path_sorted = np.argsort(path, kind="stable")
    neigh_path = _neighbor_indices_1d(path_sorted, path[path_sorted], 40)
    p2: dict[str, tuple] = {}
    for pos_i in range(n):
        i = int(path_sorted[pos_i])
        for pos_j in neigh_path[pos_i]:
            j = int(path_sorted[pos_j])
            if i == j:
                continue
            zp = float(z_path[i] - z_path[j])
            zt = float(z_time[i] - z_time[j])
            if abs(zp) > 0.25:
                continue
            if abs(zt) < 1.5:
                continue
            score = abs(zt) - 0.5 * abs(zp)
            ex = extras(i, j, zp, zt)
            ex["score_definition"] = "|z_time_diff| - 0.5*|z_path_diff|; path matched |dz|<=0.25, time separated |dz|>=1.5; confound/diversity penalties applied by _add_pair"
            add(p2, i, j, score, "P2_TIME_SEPARATED_PATH_MATCHED", zp, zt, ex)
    p2_list = _candidate_records(p2, pool_lookup, "P2_TIME_SEPARATED_PATH_MATCHED", top_per_class, max_same_map_pair=1)
    p2_reserve = _candidate_records(p2, pool_lookup, "P2_TIME_SEPARATED_PATH_MATCHED", reserve_per_class, max_same_map_pair=3)
    _annotate_reasons(p2_list, "TIME separated while PATH is matched; isolates the slider TIME construct.")
    _annotate_reasons(p2_reserve, "TIME separated while PATH is matched; isolates the slider TIME construct.")

    # ----- P3: PATH/TIME same direction -----------------------------------
    order = np.argsort(c_same, kind="stable")
    top_n = min(700, n)
    p3: dict[str, tuple] = {}
    top_ids = [int(x) for x in order[-top_n:][::-1]]
    bottom_ids = [int(x) for x in order[:top_n]]
    for i in top_ids:
        for j in bottom_ids:
            if i == j:
                continue
            zp = float(z_path[i] - z_path[j])
            zt = float(z_time[i] - z_time[j])
            if sign_of(zp) != sign_of(zt) or sign_of(zp) == 0:
                continue
            if abs(zp) < 0.75 or abs(zt) < 0.75:
                continue
            score = abs(zp) + abs(zt)
            ex = extras(i, j, zp, zt)
            ex["score_definition"] = "|z_path_diff| + |z_time_diff| with same sign and both |dz|>=0.75; confound/diversity penalties applied"
            add(p3, i, j, score, "P3_PATH_TIME_SAME_DIRECTION", zp, zt, ex)
    p3_list = _candidate_records(p3, pool_lookup, "P3_PATH_TIME_SAME_DIRECTION", top_per_class, max_same_map_pair=1)
    p3_reserve = _candidate_records(p3, pool_lookup, "P3_PATH_TIME_SAME_DIRECTION", reserve_per_class, max_same_map_pair=3)
    _annotate_reasons(p3_list, "PATH and TIME move together; useful for calibrating same-direction answers.")
    _annotate_reasons(p3_reserve, "PATH and TIME move together; useful for calibrating same-direction answers.")

    # ----- P4: PATH/TIME opposite direction --------------------------------
    order_rev = np.argsort(c_rev, kind="stable")
    p4: dict[str, tuple] = {}
    top_ids = [int(x) for x in order_rev[-top_n:][::-1]]
    bottom_ids = [int(x) for x in order_rev[:top_n]]
    for i in top_ids:
        for j in bottom_ids:
            if i == j:
                continue
            zp = float(z_path[i] - z_path[j])
            zt = float(z_time[i] - z_time[j])
            if sign_of(zp) == 0 or sign_of(zt) == 0 or sign_of(zp) == sign_of(zt):
                continue
            if abs(zp) < 0.75 or abs(zt) < 0.75:
                continue
            score = abs(zp) + abs(zt)
            ex = extras(i, j, zp, zt)
            ex["score_definition"] = "|z_path_diff| + |z_time_diff| with opposite signs and both |dz|>=0.75; confound/diversity penalties applied"
            add(p4, i, j, score, "P4_PATH_TIME_OPPOSITE_DIRECTION", zp, zt, ex)
    p4_list = _candidate_records(p4, pool_lookup, "P4_PATH_TIME_OPPOSITE_DIRECTION", top_per_class, max_same_map_pair=1)
    p4_reserve = _candidate_records(p4, pool_lookup, "P4_PATH_TIME_OPPOSITE_DIRECTION", reserve_per_class, max_same_map_pair=3)
    _annotate_reasons(p4_list, "PATH and TIME point opposite ways; discriminates construct confusion.")
    _annotate_reasons(p4_reserve, "PATH and TIME point opposite ways; discriminates construct confusion.")

    # ----- P5: both close ------------------------------------------------
    metric_space = np.stack([z_path, z_time], axis=1)
    nn5 = _neighbors_nn(metric_space, 25)
    p5: dict[str, tuple] = {}
    for i in range(n):
        for j in nn5[i]:
            if i == j:
                continue
            zp = float(z_path[i] - z_path[j])
            zt = float(z_time[i] - z_time[j])
            d = math.hypot(zp, zt)
            if d > 0.5:
                continue
            score = -d
            ex = extras(i, j, zp, zt)
            ex["score_definition"] = "negative euclidean distance in (z_path, z_time) with d<=0.5; confound/diversity penalties applied"
            add(p5, i, j, score, "P5_BOTH_CLOSE", zp, zt, ex)
    p5_list = _candidate_records(p5, pool_lookup, "P5_BOTH_CLOSE", top_per_class, max_same_map_pair=1)
    p5_reserve = _candidate_records(p5, pool_lookup, "P5_BOTH_CLOSE", reserve_per_class, max_same_map_pair=3)
    _annotate_reasons(p5_list, "Both metrics are close; near-boundary / SAME calibration candidate.")
    _annotate_reasons(p5_reserve, "Both metrics are close; near-boundary / SAME calibration candidate.")

    # ----- P6: large-effect sanity/control --------------------------------
    p6: dict[str, tuple] = {}
    for i in top_ids:
        for j in bottom_ids:
            if i == j:
                continue
            zp = float(z_path[i] - z_path[j])
            zt = float(z_time[i] - z_time[j])
            if sign_of(zp) != sign_of(zt) or sign_of(zp) == 0:
                continue
            if abs(zp) < 2.5 or abs(zt) < 2.5:
                continue
            score = min(abs(zp), abs(zt))
            ex = extras(i, j, zp, zt)
            ex["score_definition"] = "min(|z_path_diff|, |z_time_diff|) with both >=2.5 and same sign; confound/diversity penalties applied"
            ex["reasons"].append("large_effect_positive_control: both questions should clearly point to the same side")
            add(p6, i, j, score, "P6_LARGE_EFFECT_SANITY_CONTROL", zp, zt, ex)
    excluded_p3 = {c["pair_key"] for c in p3_list}
    p6_list = _candidate_records(p6, pool_lookup, "P6_LARGE_EFFECT_SANITY_CONTROL", top_per_class, excluded_keys=excluded_p3, max_same_map_pair=1)
    p6_reserve = _candidate_records(p6, pool_lookup, "P6_LARGE_EFFECT_SANITY_CONTROL", reserve_per_class, excluded_keys=excluded_p3, max_same_map_pair=3)
    _annotate_reasons(p6_list, "Large-effect positive controls: both PATH and TIME clearly favor the same side.")
    _annotate_reasons(p6_reserve, "Large-effect positive controls: both PATH and TIME clearly favor the same side.")

    # ----- P7: near perceptual threshold ---------------------------------
    p7: dict[str, tuple] = {}
    target_z = 0.60
    for i in range(n):
        for j in nn5[i]:
            if i == j:
                continue
            zp = float(z_path[i] - z_path[j])
            zt = float(z_time[i] - z_time[j])
            azp = abs(zp)
            azt = abs(zt)
            path_threshold_ok = (0.25 <= azp <= 1.20) and azt <= 0.40
            time_threshold_ok = (0.25 <= azt <= 1.20) and azp <= 0.40
            if not (path_threshold_ok or time_threshold_ok):
                continue
            if path_threshold_ok:
                score = -abs(azp - target_z)
            else:
                score = -abs(azt - target_z)
            ex = extras(i, j, zp, zt)
            ex["score_definition"] = "one metric within [0.25,1.20]z and the other <=0.40z; closeness to 0.60z ideal threshold; confound/diversity penalties applied"
            add(p7, i, j, score, "P7_NEAR_PERCEPTUAL_THRESHOLD", zp, zt, ex)
    p7_list = _candidate_records(p7, pool_lookup, "P7_NEAR_PERCEPTUAL_THRESHOLD", top_per_class, max_same_map_pair=1)
    p7_reserve = _candidate_records(p7, pool_lookup, "P7_NEAR_PERCEPTUAL_THRESHOLD", reserve_per_class, max_same_map_pair=3)
    _annotate_reasons(p7_list, "At least one metric sits near the plausible perceptual decision boundary.")
    _annotate_reasons(p7_reserve, "At least one metric sits near the plausible perceptual decision boundary.")

    # ----- P8: repeat-heavy ----------------------------------------------
    repeat_vals = np.array([
        r["repeat_load"] if r.get("repeat_load") is not None and math.isfinite(float(r["repeat_load"])) else np.nan
        for r in usable
    ])
    span_vals = np.array([
        r["span_load"] if r.get("span_load") is not None and math.isfinite(float(r["span_load"])) else np.nan
        for r in usable
    ])
    repeat_mask = np.isfinite(repeat_vals)
    repeat_order = np.argsort(np.where(repeat_mask, repeat_vals, -np.inf), kind="stable")[::-1]
    heavy = [int(x) for x in repeat_order[:400] if repeat_mask[int(x)]]
    p8: dict[str, tuple] = {}
    for a_i in heavy:
        for b_i in heavy:
            if a_i == b_i or a_i > b_i:
                continue
            zp = float(z_path[a_i] - z_path[b_i])
            zt = float(z_time[a_i] - z_time[b_i])
            rl = float(repeat_vals[a_i]) + float(repeat_vals[b_i])
            sl = 0.0
            if span_vals[a_i] and math.isfinite(float(span_vals[a_i])) and span_vals[b_i] and math.isfinite(float(span_vals[b_i])):
                sl = float(span_vals[a_i]) + float(span_vals[b_i])
            score = rl + 0.2 * sl + 0.1 * max(abs(zp), abs(zt))
            ex = extras(a_i, b_i, zp, zt)
            ex["score_definition"] = "combined repeat_load + 0.2*span_load + 0.1*max metric separation"
            ex["reasons"].append(f"repeat_heavy_proxy: repeat_load side_a={repeat_vals[a_i]:.4f}, side_b={repeat_vals[b_i]:.4f} (map-level repeat total / estimated slider count)")
            add(p8, a_i, b_i, score, "P8_REPEAT_HEAVY", zp, zt, ex)
    p8_list = _candidate_records(p8, pool_lookup, "P8_REPEAT_HEAVY", top_per_class, max_same_map_pair=1)
    p8_reserve = _candidate_records(p8, pool_lookup, "P8_REPEAT_HEAVY", reserve_per_class, max_same_map_pair=3)
    _annotate_reasons(p8_list, "Repeat-heavy sliders (proxy); labels here test whether repeat structure biases human PATH/TIME judgements.")
    _annotate_reasons(p8_reserve, "Repeat-heavy sliders (proxy); labels here test whether repeat structure biases human PATH/TIME judgements.")

    # ----- P9: slider density confound ------------------------------------
    z_nslider = robust_z(np.array([r["n_slider_rows"] for r in usable], dtype=float))
    slider_ratio_arr = np.array([
        r["slider_ratio"] if r.get("slider_ratio") is not None and math.isfinite(float(r["slider_ratio"])) else np.nan
        for r in usable
    ])
    z_sratio = robust_z(np.where(np.isfinite(slider_ratio_arr), slider_ratio_arr, np.nanmedian(slider_ratio_arr)))
    density_order = np.argsort(z_nslider + z_sratio, kind="stable")
    p9: dict[str, tuple] = {}
    top_d = [int(x) for x in density_order[-400:][::-1]]
    bottom_d = [int(x) for x in density_order[:400]]
    for i in top_d:
        for j in bottom_d:
            if i == j:
                continue
            zp = float(z_path[i] - z_path[j])
            zt = float(z_time[i] - z_time[j])
            score = float(z_nslider[i] - z_nslider[j]) + float(z_sratio[i] - z_sratio[j]) - 0.15 * (abs(zp) + abs(zt))
            ex = extras(i, j, zp, zt)
            ex["score_definition"] = "slider-density contrast minus 0.15*metric separation; surfaces density confound"
            ex["reasons"].append(
                f"slider_density_confound: n_slider_rows {usable[i]['n_slider_rows']} vs {usable[j]['n_slider_rows']}; "
                f"slider_ratio {usable[i].get('slider_ratio')} vs {usable[j].get('slider_ratio')}"
            )
            add(p9, i, j, score, "P9_SLIDER_DENSITY_CONFOUND", zp, zt, ex)
    p9_list = _candidate_records(p9, pool_lookup, "P9_SLIDER_DENSITY_CONFOUND", top_per_class, max_same_map_pair=1)
    p9_reserve = _candidate_records(p9, pool_lookup, "P9_SLIDER_DENSITY_CONFOUND", reserve_per_class, max_same_map_pair=3)
    _annotate_reasons(p9_list, "Slider density differs strongly; labels here test whether density confounds PATH/TIME judgements.")
    _annotate_reasons(p9_reserve, "Slider density differs strongly; labels here test whether density confounds PATH/TIME judgements.")

    # ----- P10: structural anomaly/stress ---------------------------------
    anomaly_score = np.zeros(n, dtype=float)
    anomaly_reasons: list[list[str]] = [[] for _ in range(n)]
    for idx, r in enumerate(usable):
        flags = []
        if r["n_slider_rows"] > 0 and r.get("path_p90") == 0:
            flags.append("zero_path_p90_with_sliders")
        if r["n_slider_rows"] > 0 and r.get("time_p90") == 0:
            flags.append("zero_time_p90_with_sliders")
        if r.get("path_p90") is not None and path[idx] > path_p99:
            flags.append(f"path_p90>p99 ({path_p99:.1f})")
        if r.get("time_p90") is not None and time[idx] > time_p99:
            flags.append(f"time_p90>p99 ({time_p99:.1f}ms)")
        if r["n_slider_rows"] > nslider_p99:
            flags.append(f"n_slider_rows>p99 ({nslider_p99:.0f})")
        if r["segment_index"] > seg_idx_p95:
            flags.append(f"late_segment_index>p95 ({seg_idx_p95:.0f})")
        if r.get("track_time_p90") is not None and r.get("time_p90") is not None and r["track_time_p90"] > r["time_p90"]:
            flags.append("track_time_p90>time_p90")
        if r.get("path_p90") is not None and 0 < path[idx] < path_p50 * 0.05:
            flags.append("path_p90_low_nonzero")
        anomaly_score[idx] = float(len(flags))
        anomaly_reasons[idx] = flags

    anomaly_order = np.argsort(anomaly_score, kind="stable")[::-1]
    p10: dict[str, tuple] = {}
    anchor_ids = [int(x) for x in anomaly_order[:600] if anomaly_score[int(x)] >= 1]
    # nearest normal neighbors for each anchor
    normal_mask = anomaly_score <= 0
    normal_ids = [int(x) for x in np.where(normal_mask)[0]]
    X_anom = X[anchor_ids]
    X_normal = X[normal_ids]
    nn10 = None
    if len(anchor_ids) and len(normal_ids):
        if NearestNeighbors is not None:
            nn10 = NearestNeighbors(n_neighbors=min(25, len(normal_ids)), algorithm="brute", metric="euclidean")
            nn10.fit(X_normal)
            _d, _idx = nn10.kneighbors(X_anom)
            for pos, i in enumerate(anchor_ids):
                for local_j in _idx[pos]:
                    j = normal_ids[int(local_j)]
                    if i == j:
                        continue
                    zp = float(z_path[i] - z_path[j])
                    zt = float(z_time[i] - z_time[j])
                    cov = _cov_dist_vec(X, i, j)
                    score = float(anomaly_score[i]) - 0.3 * cov
                    ex = extras(i, j, zp, zt)
                    ex["score_definition"] = "anomaly_score - 0.3*covariate_distance; anomaly paired with covariate-matched normal"
                    ex["reasons"].extend(f"anomaly: {flag}" for flag in anomaly_reasons[i])
                    add(p10, i, j, score, "P10_STRUCTURAL_ANOMALY_STRESS", zp, zt, ex)
    p10_list = _candidate_records(p10, pool_lookup, "P10_STRUCTURAL_ANOMALY_STRESS", top_per_class, max_same_map_pair=1)
    p10_reserve = _candidate_records(p10, pool_lookup, "P10_STRUCTURAL_ANOMALY_STRESS", reserve_per_class, max_same_map_pair=3)
    _annotate_reasons(p10_list, "Structurally anomalous or stressed segments paired with covariate-matched controls.")
    _annotate_reasons(p10_reserve, "Structurally anomalous or stressed segments paired with covariate-matched controls.")

    candidates = {
        "P1_PATH_SEPARATED_TIME_MATCHED": p1_list,
        "P2_TIME_SEPARATED_PATH_MATCHED": p2_list,
        "P3_PATH_TIME_SAME_DIRECTION": p3_list,
        "P4_PATH_TIME_OPPOSITE_DIRECTION": p4_list,
        "P5_BOTH_CLOSE": p5_list,
        "P6_LARGE_EFFECT_SANITY_CONTROL": p6_list,
        "P7_NEAR_PERCEPTUAL_THRESHOLD": p7_list,
        "P8_REPEAT_HEAVY": p8_list,
        "P9_SLIDER_DENSITY_CONFOUND": p9_list,
        "P10_STRUCTURAL_ANOMALY_STRESS": p10_list,
    }
    reserve = {
        "P1_PATH_SEPARATED_TIME_MATCHED": p1_reserve,
        "P2_TIME_SEPARATED_PATH_MATCHED": p2_reserve,
        "P3_PATH_TIME_SAME_DIRECTION": p3_reserve,
        "P4_PATH_TIME_OPPOSITE_DIRECTION": p4_reserve,
        "P5_BOTH_CLOSE": p5_reserve,
        "P6_LARGE_EFFECT_SANITY_CONTROL": p6_reserve,
        "P7_NEAR_PERCEPTUAL_THRESHOLD": p7_reserve,
        "P8_REPEAT_HEAVY": p8_reserve,
        "P9_SLIDER_DENSITY_CONFOUND": p9_reserve,
        "P10_STRUCTURAL_ANOMALY_STRESS": p10_reserve,
    }
    return {
        "pool_size": len(usable),
        "total_pool_size": len(pool),
        "human_judgability_filter": filter_meta,
        "candidate_classes": candidates,
        "reserve_candidates": reserve,
        "reserve_candidate_counts": {k: len(v) for k, v in reserve.items()},
        "formal_keys": sorted(formal_keys),
    }


def _annotate_reasons(items: list[dict], class_reason: str) -> None:
    for item in items:
        reasons = list(item.get("reasons", []))
        reasons.insert(0, class_reason)
        item["reasons"] = reasons


def _formal_probe_keys(pool_lookup: dict[str, dict]) -> set[str]:
    """Build formal probe side keys without loading package again; uses the pool marker set below."""
    return getattr(_formal_probe_keys, "_cache", set())


def _set_formal_probe_keys(keys: set[str]) -> None:
    _formal_probe_keys._cache = keys  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# matching frontier (Phase F)

def matching_frontier(pool: list[dict], seed: int) -> dict:
    usable, filter_meta = filter_pool_for_human_judgability(pool)
    if not usable:
        raise ValueError("no usable segments after human-judgability filter for matching frontier")
    path = np.array([r["path_p90"] for r in usable], dtype=float)
    time = np.array([r["time_p90"] for r in usable], dtype=float)
    z_path = robust_z(path)
    z_time = robust_z(time)
    X = _covariate_matrix(usable)
    n = len(usable)
    rng = np.random.default_rng(seed)
    anchor_idx = np.sort(rng.choice(n, size=min(2000, n), replace=False)).tolist()

    def frontier_for(metric_z: np.ndarray, metric_name: str) -> dict:
        # Random baseline: average covariate distance of random pairs
        cov_before = []
        sep_before = []
        for _ in range(3000):
            a, b = rng.integers(0, n, size=2)
            if a == b:
                continue
            cov_before.append(_cov_dist_vec(X, int(a), int(b)))
            sep_before.append(abs(float(metric_z[int(a)] - metric_z[int(b)])))

        nn = _neighbors_nn(X, 1)
        cov_after = []
        sep_after = []
        for i in anchor_idx:
            if not nn[i]:
                continue
            j = nn[i][0]
            cov_after.append(_cov_dist_vec(X, i, j))
            sep_after.append(abs(float(metric_z[i] - metric_z[j])))

        # Constrained search: for each anchor, among nearest covariate neighbors
        # find the largest metric separation within increasing covariate radius.
        thresholds = [0.25, 0.5, 1.0, 2.0, 4.0]
        radius_nn = _neighbors_nn(X, 60)
        rows = []
        for thr in thresholds:
            seps = []
            covs = []
            counts = 0
            for i in anchor_idx:
                best_sep = 0.0
                best_cov = None
                for j in radius_nn[i]:
                    d = _cov_dist_vec(X, i, j)
                    if d > thr:
                        continue
                    sep = abs(float(metric_z[i] - metric_z[j]))
                    if sep > best_sep:
                        best_sep = sep
                        best_cov = d
                if best_cov is not None:
                    seps.append(best_sep)
                    covs.append(best_cov)
                    counts += 1
            if seps:
                rows.append({
                    "covariate_radius_z": thr,
                    "pairs_found": counts,
                    "mean_target_separation_z": round(float(np.mean(seps)), 6),
                    "mean_covariate_distance_z": round(float(np.mean(covs)), 6),
                    "target_separation_z_p50": round(float(np.median(seps)), 6),
                })
        return {
            "metric": metric_name,
            "baseline_random_pairs": {
                "mean_covariate_distance_z": round(float(np.mean(cov_before)), 6),
                "mean_target_separation_z": round(float(np.mean(sep_before)), 6),
            },
            "nearest_covariate_matching": {
                "mean_covariate_distance_z_after": round(float(np.mean(cov_after)), 6),
                "mean_target_separation_z_after": round(float(np.mean(sep_after)), 6),
                "anchors": len(cov_after),
            },
            "constrained_search": rows,
        }

    return {
        "phase": "F",
        "definition": "Matching frontier for PATH and TIME target separation vs average standardised covariate distance before/after matching. Higher separation at low covariate distance is better; this is an audit aid, not a human label.",
        "human_judgability_filter": filter_meta,
        "frontier": [
            frontier_for(z_path, "PATH"),
            frontier_for(z_time, "TIME"),
        ],
    }


# ---------------------------------------------------------------------------
# top queues (Phase G)

def _allowed_why(reasons: list[str]) -> list[str]:
    allowed_prefixes = (
        "weak_supervision_disagreement",
        "weak_supervision_abstention",
        "path_time_reversal",
        "near_decision_boundary",
        "underrepresented_region",
        "calibration_leverage",
    )
    return [r for r in reasons if r.startswith(allowed_prefixes)]


def build_reasons_for_pair(rec_i: dict, rec_j: dict, zp_diff: float, zt_diff: float, formal: bool) -> list[str]:
    reasons: list[str] = []
    # weak supervision disagreement / abstention
    statuses = {rec_i.get("ws_status"), rec_j.get("ws_status")}
    if "ABSTAINED" in statuses:
        reasons.append("weak_supervision_abstention: at least one side has ws01.local.slider_travel_segment ABSTAINED")
    if "EMITTED" in statuses and ("ABSTAINED" in statuses or "UNAVAILABLE" in statuses):
        reasons.append("weak_supervision_disagreement: weak-supervision status differs between sides")
    if rec_i.get("ws_status") == "EMITTED" and rec_j.get("ws_status") == "EMITTED":
        dirs = {rec_i.get("ws_direction"), rec_j.get("ws_direction")}
        if len(dirs) > 1:
            reasons.append("weak_supervision_disagreement: both EMITTED but direction fields differ")

    # PATH/TIME reversal
    if sign_of(zp_diff) != 0 and sign_of(zt_diff) != 0 and sign_of(zp_diff) != sign_of(zt_diff):
        reasons.append("path_time_reversal: PATH and TIME standardised differences point in opposite directions")

    # near decision boundary / calibration leverage (mutually exclusive, both allowed sources)
    zmax = max(abs(zp_diff), abs(zt_diff))
    if 0.15 <= zmax <= 1.00:
        reasons.append("near_decision_boundary: at least one metric is within [0.15,1.00] robust-z of the decision boundary")
    elif zmax > 1.00:
        reasons.append("calibration_leverage: high robust-z separation provides calibration signal between SAME and CLEAR")

    # underrepresented region
    for tag, rec in (("side_a", rec_i), ("side_b", rec_j)):
        if rec.get("split") in ("val", "test"):
            reasons.append(f"underrepresented_region: {tag} split={rec.get('split')}")
            break
    else:
        if rec_i.get("n_slider_rows", 0) <= 1 or rec_j.get("n_slider_rows", 0) <= 1:
            reasons.append("underrepresented_region: segment with <=1 slider row")
        elif rec_i.get("segment_index", 0) >= 50 or rec_j.get("segment_index", 0) >= 50:
            reasons.append("underrepresented_region: late map segment (segment_index>=50)")

    return reasons


def build_top_queues(mined: dict, seed: int) -> dict:
    classes = mined.get("reserve_candidates", mined["candidate_classes"])
    all_cands: dict[str, dict] = {}
    for cls_name, items in classes.items():
        for item in items:
            k = item["pair_key"]
            if k not in all_cands:
                all_cands[k] = item
            else:
                # merge reasons from other class
                all_cands[k]["reasons"] = list(dict.fromkeys(all_cands[k].get("reasons", []) + item.get("reasons", [])))

    # Priority score: high information without leaking the target metric to participants
    for k, item in all_cands.items():
        zp = abs(item.get("path_z_diff", 0.0) or 0.0)
        zt = abs(item.get("time_z_diff", 0.0) or 0.0)
        ws_bonus = 0.0
        sa = item["side_a"]
        sb = item["side_b"]
        if sa.get("ws_status") == "ABSTAINED" or sb.get("ws_status") == "ABSTAINED":
            ws_bonus += 0.5
        if sa.get("ws_status") != sb.get("ws_status"):
            ws_bonus += 0.5
        item["_priority"] = 0.35 * max(zp, zt) + 0.25 * min(zp, zt) + 0.2 * ws_bonus + 0.1 * min(1.0, item.get("score", 0.0) / 10.0)
        item["_zmax"] = max(zp, zt)

    ordered = sorted(all_cands.values(), key=lambda it: (-it["_priority"], it["pair_key"]))

    def greedy(k: int) -> list[dict]:
        chosen: list[dict] = []
        seg_use: dict[str, int] = {}
        map_pair_use: dict[str, int] = {}
        for item in ordered:
            if len(chosen) >= k:
                break
            key_a = item["side_a"]["key"]
            key_b = item["side_b"]["key"]
            map_pair = pair_key(item["side_a"]["map_checksum"], item["side_b"]["map_checksum"])
            if seg_use.get(key_a, 0) >= 3 or seg_use.get(key_b, 0) >= 3:
                continue
            if map_pair_use.get(map_pair, 0) >= 2:
                continue
            reasons = list(item.get("reasons", []))
            why = [r for r in reasons if r.startswith((
                "weak_supervision_disagreement",
                "weak_supervision_abstention",
                "path_time_reversal",
                "near_decision_boundary",
                "underrepresented_region",
                "calibration_leverage",
            ))]
            if not why:
                # fallback must still be one of the allowed why-sources; never a
                # class reason and never a fabricated human answer.
                why = (
                    ["near_decision_boundary: at least one metric is within [0.15,1.00] robust-z of the decision boundary"]
                    if item.get("_zmax", 0.0) <= 1.00
                    else ["calibration_leverage: high robust-z separation provides calibration signal between SAME and CLEAR"]
                )
            out_item = {kk: vv for kk, vv in item.items() if not kk.startswith("_")}
            out_item["why"] = why[:6]
            chosen.append(out_item)
            seg_use[key_a] = seg_use.get(key_a, 0) + 1
            seg_use[key_b] = seg_use.get(key_b, 0) + 1
            map_pair_use[map_pair] = map_pair_use.get(map_pair, 0) + 1
        return chosen

    return {
        "phase": "G",
        "queue_definition": "Internal audit queues only. why-reasons are restricted to: weak-supervision disagreement/abstention, PATH/TIME reversal, near decision boundary, underrepresented region, calibration leverage. These are NOT participant-facing and never expose the target metric.",
        "TOP_25": greedy(25),
        "TOP_50": greedy(50),
        "TOP_100": greedy(100),
        "TOP_200": greedy(200),
    }


# ---------------------------------------------------------------------------
# main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=DEFAULT_REPO)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--candidate-pool-out", default=DEFAULT_POOL_OUT)
    parser.add_argument("--top-per-class", type=int, default=DEFAULT_TOP_PER_CLASS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    repo = args.repo_root
    package_rel = "training/datasets/retest_v01/package/retest_package_10x6_v01.json"
    construct_rel = "tmp/gap_audit/all_segment_construct_stats_v01.json"
    feature_rel = "training/datasets/feature_qa_v02/feature_qa_5k.jsonl"
    split_rel = "training/datasets/splits/v02/set_disjoint.jsonl"
    evidence_rel = "training/datasets/weak_supervision_v01/pilot/evidence.jsonl"

    print("[pair-mine] building pool ...")
    pool, pool_meta = build_pool(repo, construct_rel, feature_rel, split_rel, evidence_rel)

    # Formal probe side keys for FORMAL detection
    package = jload(os.path.join(repo, package_rel))
    formal_keys = set()
    for probe in package["probes"]:
        for side_name in ("side_a", "side_b"):
            side = probe[side_name]
            formal_keys.add(f"{side['map_checksum']}::{side['segment_index']}")
    _set_formal_probe_keys(formal_keys)

    print(f"[pair-mine] pool={pool_meta['segments']} segments, {pool_meta['maps']} maps, formal sides={len(formal_keys)}")

    print("[pair-mine] Phase D formal re-audit ...")
    formal = formal_reaudit(repo, package_rel, construct_rel, feature_rel)

    print("[pair-mine] Phase E candidate mining ...")
    mined = mine_candidates(pool, args.top_per_class, args.seed)

    print("[pair-mine] Phase F matching frontier ...")
    frontier = matching_frontier(pool, args.seed)

    print("[pair-mine] Phase G top queues ...")
    top_queues = build_top_queues(mined, args.seed)

    # Final annotation pass: ensure every candidate has the five allowed why-source
    # reasons where applicable and never silently promotes stress/diagnostic pairs.
    all_cands = []
    for cls, items in mined["reserve_candidates"].items():
        all_cands.extend(items)
    by_key = {}
    for it in all_cands:
        k = it["pair_key"]
        by_key[k] = it
        it["reasons"] = list(dict.fromkeys(it.get("reasons", [])))
    for it in all_cands:
        sa = it["side_a"]
        sb = it["side_b"]
        auto = build_reasons_for_pair(sa, sb, it.get("path_z_diff", 0.0) or 0.0, it.get("time_z_diff", 0.0) or 0.0, it.get("formal_probe", False))
        it["reasons"] = list(dict.fromkeys(it.get("reasons", []) + auto))
        it["why"] = _allowed_why(it["reasons"])[:6]

    output = {
        "audit_id": "SKILL_PROFILER_LABEL_EFFICIENCY_AUDIT_V01",
        "generated_by": "tools/skill-profiler-pair-mine.py",
        "deterministic": True,
        "seed": args.seed,
        "formal_pair_reaudit": formal,
        "candidate_classes": mined["candidate_classes"],
        "candidate_class_counts": {k: len(v) for k, v in mined["candidate_classes"].items()},
        "reserve_candidate_class_counts": mined.get("reserve_candidate_counts", {}),
        "total_candidates": sum(len(v) for v in mined["candidate_classes"].values()),
        "total_unique_reserve_candidates": len({it["pair_key"] for it in all_cands}),
        "matching_frontier": frontier,
        "top_queues": top_queues,
        "phase_g_top_queue_lengths": {k: len(v) for k, v in top_queues.items() if k.startswith("TOP_")},
        "metadata": {
            "pool": pool_meta,
            "human_judgability_filter": mined.get("human_judgability_filter", {}),
            "robust_z_scale": "IQR/1.349 (Gaussian-equivalent; matches 1.4826*MAD)",
            "class_definitions": {
                "P1_PATH_SEPARATED_TIME_MATCHED": "PATH robust-z separation >=1.5 while TIME matched |dz|<=0.25",
                "P2_TIME_SEPARATED_PATH_MATCHED": "TIME robust-z separation >=1.5 while PATH matched |dz|<=0.25",
                "P3_PATH_TIME_SAME_DIRECTION": "PATH and TIME robust-z differences have the same sign and both |dz|>=0.75",
                "P4_PATH_TIME_OPPOSITE_DIRECTION": "PATH and TIME robust-z differences have opposite signs and both |dz|>=0.75",
                "P5_BOTH_CLOSE": "both metrics close in robust-z space (euclidean d<=0.5)",
                "P6_LARGE_EFFECT_SANITY_CONTROL": "positive controls with both robust-z differences >=2.5 and same sign",
                "P7_NEAR_PERCEPTUAL_THRESHOLD": "one metric in robust-z [0.25,1.20] and the other <=0.40",
                "P8_REPEAT_HEAVY": "repeat-heavy proxy from map-level repeat/span totals and estimated slider count",
                "P9_SLIDER_DENSITY_CONFOUND": "large slider-density contrast (n_slider_rows and slider_ratio)",
                "P10_STRUCTURAL_ANOMALY_STRESS": "structural anomalies paired with covariate-matched controls",
            },
            "scoring": "Every candidate score subtracts 0.30 per confound_indicator plus 0.35 for same set_group and 0.20 for same mapper_group. Candidates require different map_checksum.",
            "internal_only_notice": "This JSON is an internal audit artifact. It intentionally contains target-metric values that must NOT be exposed to participants. FORMAL probe statuses are never altered by this audit.",
        },
    }

    print(f"[pair-mine] writing {args.out}")
    jwrite(args.out, output)
    if args.candidate_pool_out:
        pool_for_sim = {
            "generated_by": "tools/skill-profiler-pair-mine.py",
            "seed": args.seed,
            "candidates": all_cands,
        }
        print(f"[pair-mine] writing candidate pool {args.candidate_pool_out}")
        jwrite(args.candidate_pool_out, pool_for_sim)

    # quick report
    print("[pair-mine] done")
    print("formal entries:", [e["status"] for e in formal["entries"]])
    print("candidate counts:", {k: len(v) for k, v in mined["candidate_classes"].items()})
    print("top queue lengths:", {k: len(v) for k, v in top_queues.items() if k.startswith("TOP_")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
