"""Dataset Split & Leakage Audit v0.1 tooling.

Builds the deterministic benchmark boundary for osu-skill-profiler:

- canonical map / set / mapper identities from the corpus manifest;
- SET_DISJOINT, MAPPER_DISJOINT and STRICT_SET_AND_MAPPER_DISJOINT splits;
- LEGACY_FORMAT_OOD, PATHOLOGICAL_CHALLENGE and
  REFERENCE_DISAGREEMENT_CHALLENGE subsets;
- strict verification that every claimed leakage constraint actually holds.

Metadata-only: no `.osu` parsing and no feature/signal recomputation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osu_skill_profiler.dataset.split_v01 import (  # noqa: E402
    CHECKSUM_RE,
    DEFAULT_SEED,
    LEGACY_FORMAT_MAX,
    SPLIT_VERSION,
    assign_components,
    build_components,
    build_split_records,
    legacy_format_flags,
    mapper_group_key,
    normalize_mapper_name,
    pathological_reasons,
    reference_disagreement_entry,
    set_group_key,
    source_manifest_checksum,
    stream_manifest_samples,
)

GENERATOR_VERSION = "0.1.0"
DEFAULT_WORKERS = 1
MAX_WORKERS = 4


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _git_state(repo_root: Path) -> dict:
    state = {"head": None, "dirty": True}
    try:
        head = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if head.returncode == 0:
            state["head"] = head.stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if status.returncode == 0:
            state["dirty"] = bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return state


def _load_candidates(path: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            candidate = json.loads(line)
            checksum = candidate.get("checksum")
            if checksum:
                out[checksum].append(reference_disagreement_entry(candidate))
    return out


def _load_qa_flags(
    feature_qa: Path,
    ref_qa: Path,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Stream QA summaries and index the per-map provenance we need."""

    feature_flags: dict[str, dict] = {}
    ref_flags: dict[str, dict] = {}

    for path, target in ((feature_qa, feature_flags), (ref_qa, ref_flags)):
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                checksum = record.get("checksum")
                if not checksum:
                    continue
                validation = record.get("validation") or {}
                geometry_blocked_count = int(validation.get("geometry_blocked_count") or 0)
                target[checksum] = {
                    "flags": sorted(record.get("flags") or []),
                    "short_lt100": bool(record.get("short_lt100")),
                    "short_lt1000": bool(record.get("short_lt1000")),
                    "ok": bool(record.get("ok")),
                    "geometry_blocked": geometry_blocked_count > 0,
                    "geometry_blocked_count": geometry_blocked_count,
                }
    return feature_flags, ref_flags


def _load_manifest_records(manifest: Path, seed: str) -> tuple[dict, list[dict], list[str]]:
    """Stream the manifest once and build annotated working records."""

    header = None
    records: list[dict] = []
    diagnostics: list[str] = []
    with manifest.open("r", encoding="utf-8") as handle:
        first = handle.readline()
        if first.startswith("{"):
            header = json.loads(first.rstrip("\n") + " ]}")
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ("]}", "]"):
                break
            if stripped.endswith(","):
                stripped = stripped[:-1]
            sample = json.loads(stripped)
            checksum = sample.get("checksum") or sample.get("sha256")
            if not isinstance(checksum, str) or not CHECKSUM_RE.fullmatch(checksum):
                diagnostics.append(f"invalid checksum: {sample.get('sample_id')!r}")
                continue
            record = {
                "map_checksum": checksum,
                "sample_id": sample.get("sample_id"),
                "source": sample.get("source"),
                "relative_path": sample.get("relative_path") or sample.get("reference"),
                "beatmap_id": sample.get("beatmap_id"),
                "beatmapset_id": sample.get("beatmapset_id"),
                "beatmapset_id_source": sample.get("beatmapset_id_source"),
                "local_set_group": sample.get("local_set_group"),
                "artist": sample.get("artist"),
                "title": sample.get("title"),
                "creator": sample.get("creator"),
                "mapper": sample.get("mapper"),
                "version": sample.get("version"),
                "mode": sample.get("mode"),
                "format_version": sample.get("format_version"),
                "metadata": sample.get("metadata"),
            }
            try:
                set_key, set_policy = set_group_key(record)
                mapper_key, mapper_quality = mapper_group_key(record)
            except Exception as exc:  # noqa: BLE001 - collected as diagnostic
                diagnostics.append(f"{sample.get('sample_id')!r}: {exc}")
                continue
            record["set_group_key"] = set_key
            record["set_group_policy"] = set_policy
            record["mapper_group_key"] = mapper_key
            record["mapper_identity_quality"] = mapper_quality
            record["duplicate_class"] = "UNIQUE"
            records.append(record)
    return header or {}, records, diagnostics


def _annotate_qa(
    records: list[dict],
    feature_flags: dict[str, dict],
    ref_flags: dict[str, dict],
) -> list[str]:
    diagnostics: list[str] = []
    for record in records:
        checksum = record["map_checksum"]
        feature = feature_flags.get(checksum)
        ref = ref_flags.get(checksum)
        if feature is None or ref is None:
            diagnostics.append(f"missing QA row: {checksum}")
            continue
        qa_flags = sorted(set((feature.get("flags") or []) + (ref.get("flags") or [])))
        record["qa_flags"] = qa_flags
        record["short_lt100"] = feature.get("short_lt100")
        record["short_lt1000"] = feature.get("short_lt1000")
        record["geometry_blocked"] = bool(
            feature.get("geometry_blocked") or ref.get("geometry_blocked")
        )
        record["geometry_blocked_count"] = max(
            int(feature.get("geometry_blocked_count") or 0),
            int(ref.get("geometry_blocked_count") or 0),
        )
        reasons = pathological_reasons(
            record,
            qa_flags=qa_flags,
            short_lt100=feature.get("short_lt100"),
            short_lt1000=feature.get("short_lt1000"),
        )
        if record["geometry_blocked"]:
            reasons.append(f"geometry_blocked:{record['geometry_blocked_count']}")
        record["pathological_reasons"] = reasons
        record["subset_flags"] = sorted(
            set(legacy_format_flags(record.get("format_version")) + reasons)
        )
    return diagnostics


def _identity_audit(records: list[dict]) -> dict:
    by_checksum: dict[str, list[dict]] = defaultdict(list)
    by_beatmap_id: dict[Any, list[dict]] = defaultdict(list)
    by_set_key: dict[str, list[dict]] = defaultdict(list)
    by_local_group: dict[str, list[dict]] = defaultdict(list)
    by_mapper: dict[str, list[dict]] = defaultdict(list)

    for record in records:
        by_checksum[record["map_checksum"]].append(record)
        if record.get("beatmap_id") is not None:
            by_beatmap_id[record["beatmap_id"]].append(record)
        by_set_key[record["set_group_key"]].append(record)
        if record.get("local_set_group"):
            by_local_group[record["local_set_group"]].append(record)
        by_mapper[record["mapper_group_key"]].append(record)

    checksum_classes: Counter[str] = Counter()
    checksum_conflicts: list[dict] = []
    for checksum, group in by_checksum.items():
        set_keys = {r["set_group_key"] for r in group}
        mapper_keys = {r["mapper_group_key"] for r in group}
        if len(group) == 1:
            checksum_classes["UNIQUE"] += 1
        elif len(set_keys) == 1 and len(mapper_keys) == 1:
            checksum_classes["KNOWN_DUPLICATE"] += 1
            for record in group:
                record["duplicate_class"] = "KNOWN_DUPLICATE"
        else:
            checksum_classes["CONFLICT"] += 1
            checksum_conflicts.append(
                {
                    "map_checksum": checksum,
                    "count": len(group),
                    "set_group_keys": sorted(set_keys),
                    "mapper_group_keys": sorted(mapper_keys),
                    "sample_ids": sorted(r["sample_id"] for r in group),
                }
            )
            for record in group:
                record["duplicate_class"] = "CONFLICT"

    beatmap_id_conflicts = [
        {
            "beatmap_id": beatmap_id,
            "count": len(group),
            "checksums": sorted(r["map_checksum"] for r in group),
            "sample_ids": sorted(r["sample_id"] for r in group),
        }
        for beatmap_id, group in by_beatmap_id.items()
        if len({r["map_checksum"] for r in group}) > 1
    ]
    beatmap_id_conflicts.sort(key=lambda item: item["beatmap_id"])
    checksum_conflicts.sort(key=lambda item: item["map_checksum"])

    set_key_local_groups = {
        set_key: sorted({r["local_set_group"] for r in group if r.get("local_set_group")})
        for set_key, group in by_set_key.items()
        if len({r["local_set_group"] for r in group if r.get("local_set_group")}) > 1
    }
    set_key_local_groups = dict(sorted(set_key_local_groups.items()))

    local_group_set_ids = {}
    for local_group, group in by_local_group.items():
        set_ids = {r["beatmapset_id"] for r in group if isinstance(r.get("beatmapset_id"), int)}
        missing_in_group = [r for r in group if not isinstance(r.get("beatmapset_id"), int)]
        if len(set_ids) > 1 and missing_in_group:
            local_group_set_ids[local_group] = {
                "beatmapset_ids": sorted(set_ids),
                "missing_beatmapset_id_count": len(missing_in_group),
            }
    local_group_set_ids = dict(sorted(local_group_set_ids.items()))

    mapper_names: dict[str, list[str]] = defaultdict(list)
    unknown_mapper_count = 0
    for record in records:
        name = normalize_mapper_name(record.get("mapper") or record.get("creator"))
        if name is None:
            unknown_mapper_count += 1
        else:
            raw = (record.get("mapper") or record.get("creator") or "").strip()
            if raw not in mapper_names[name]:
                mapper_names[name].append(raw)

    return {
        "record_count": len(records),
        "checksum_classes": {
            key: checksum_classes[key]
            for key in ("UNIQUE", "KNOWN_DUPLICATE", "CONFLICT")
        },
        "checksum_conflict_count": len(checksum_conflicts),
        "checksum_conflicts": checksum_conflicts,
        "beatmap_id_conflict_count": len(beatmap_id_conflicts),
        "beatmap_id_conflicts": beatmap_id_conflicts,
        "set_key_multi_local_group_count": len(set_key_local_groups),
        "set_key_multi_local_groups": set_key_local_groups,
        "local_group_with_multi_set_id_and_missing_beatmapset_id_count": len(local_group_set_ids),
        "local_group_with_multi_set_id_and_missing_beatmapset_id": local_group_set_ids,
        "mapper_group_count": len(by_mapper),
        "unknown_mapper_count": unknown_mapper_count,
        "mapper_raw_name_variants": dict(
            sorted(
                (name, sorted(variants))
                for name, variants in mapper_names.items()
                if len(variants) > 1
            )
        ),
        "mapper_raw_name_variant_groups": sum(1 for v in mapper_names.values() if len(v) > 1),
    }


def _near_duplicate_diagnostics(records: list[dict]) -> list[dict]:
    """Lightweight, no-fingerprint near-duplicate diagnostics."""

    buckets: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        artist = normalize_mapper_name(record.get("artist"))
        title = normalize_mapper_name(record.get("title"))
        mapper = normalize_mapper_name(record.get("mapper") or record.get("creator"))
        if artist is None or title is None or mapper is None:
            continue
        buckets[(artist, title, mapper)].append(record)

    all_examples: list[dict] = []
    total_pairs = 0
    truncated_buckets = 0
    for key, group in buckets.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda r: (r["map_checksum"], r.get("sample_id") or ""))
        # Bounded pair scan: the diagnostic is lightweight by contract and
        # never builds a fingerprint. Large same-artist/title/mapper buckets
        # are sampled deterministically instead of exploded pairwise.
        scan_group = group[:200] if len(group) > 200 else group
        if len(group) > len(scan_group):
            truncated_buckets += 1
        for i in range(len(scan_group)):
            for j in range(i + 1, len(scan_group)):
                left, right = scan_group[i], scan_group[j]
                duration_close = _durations_close(left, right)
                objects_equal = _objects_equal(left, right)
                if left["map_checksum"] == right["map_checksum"]:
                    classification = "KNOWN_DUPLICATE"
                elif left["set_group_key"] == right["set_group_key"]:
                    classification = "SAME_SET"
                else:
                    if duration_close and objects_equal:
                        classification = "POSSIBLE_NEAR_DUPLICATE"
                    else:
                        classification = "NO_EVIDENCE"
                total_pairs += 1
                if classification in ("KNOWN_DUPLICATE", "SAME_SET", "POSSIBLE_NEAR_DUPLICATE"):
                    all_examples.append(
                        {
                            "classification": classification,
                            "left_checksum": left["map_checksum"],
                            "right_checksum": right["map_checksum"],
                            "left_sample_id": left.get("sample_id"),
                            "right_sample_id": right.get("sample_id"),
                            "left_set_group_key": left.get("set_group_key"),
                            "right_set_group_key": right.get("set_group_key"),
                            "duration_close": duration_close,
                            "objects_equal": objects_equal,
                        }
                    )

    by_class: Counter[str] = Counter()
    for row in all_examples:
        by_class[row["classification"]] += 1
    all_examples.sort(
        key=lambda e: (
            e["classification"],
            e["left_checksum"],
            e["right_checksum"],
        )
    )
    examples = all_examples[:200]
    return {
        "total_pair_count": total_pairs,
        "example_count": len(examples),
        "truncated_bucket_count": truncated_buckets,
        "examples": examples,
    }


def _durations_close(left: dict, right: dict) -> bool:
    left_ms = (left.get("metadata") or {}).get("duration_ms")
    right_ms = (right.get("metadata") or {}).get("duration_ms")
    if not isinstance(left_ms, (int, float)) or not isinstance(right_ms, (int, float)):
        return False
    left_ms, right_ms = float(left_ms), float(right_ms)
    if max(left_ms, right_ms) <= 0:
        return left_ms == right_ms
    return abs(left_ms - right_ms) / max(left_ms, right_ms) <= 0.05


def _objects_equal(left: dict, right: dict) -> bool:
    left_count = (left.get("metadata") or {}).get("counts", {}).get("objects")
    right_count = (right.get("metadata") or {}).get("counts", {}).get("objects")
    return left_count == right_count and left_count is not None


def _make_assignments(records: list[dict], keys: list[str], *, include_unknown: bool, seed: str):
    annotated, components = build_components(
        records, keys, include_unknown_mapper=include_unknown
    )
    by_checksum = {r["map_checksum"]: r for r in records}
    assignments = assign_components(components, by_checksum, seed=seed)
    return annotated, assignments


def _distribution_audit(records: list[dict], assignments: dict[str, str], split_rows: list[dict]) -> dict:
    """Per-split descriptive distributions for SET_DISJOINT."""

    per_split: dict[str, dict] = {}
    for split in ("train", "val", "test"):
        subset = [r for r in split_rows if r["split"] == split]
        checksums = {r["map_checksum"] for r in subset}
        maps = [r for r in records if r["map_checksum"] in checksums]
        stats = _summarize_maps(maps)
        per_split[split] = stats

    return {
        "split_counts": {
            split: {
                "map_count": len([r for r in split_rows if r["split"] == split]),
                "set_count": len({r["set_group_key"] for r in split_rows if r["split"] == split}),
                "known_mapper_count": len(
                    {
                        r["mapper_group_key"]
                        for r in split_rows
                        if r["split"] == split and r["mapper_identity_quality"] == "NAME_ONLY"
                    }
                ),
                "unknown_mapper_count": len(
                    [
                        r
                        for r in split_rows
                        if r["split"] == split and r["mapper_identity_quality"] == "UNKNOWN"
                    ]
                ),
            }
            for split in ("train", "val", "test")
        },
        "per_split": per_split,
    }


def _summarize_maps(maps: list[dict]) -> dict:
    def numeric(key, transform=lambda v: v):
        values = []
        for record in maps:
            value = transform(record)
            if isinstance(value, (int, float)):
                values.append(float(value))
        return _quantiles(values) if values else {}

    def metadata_numeric(field):
        return numeric(field, lambda r: (r.get("metadata") or {}).get(field))

    def difficulty_numeric(field):
        return numeric(field, lambda r: ((r.get("metadata") or {}).get("difficulty") or {}).get(field))

    format_counter: Counter[Any] = Counter()
    pathological = 0
    geometry_blocked = 0
    disagreement = 0
    legacy = 0
    for record in maps:
        format_counter[record.get("format_version")] += 1
        if record.get("pathological_reasons"):
            pathological += 1
        if record.get("geometry_blocked"):
            geometry_blocked += 1
        if "legacy_format" in (record.get("subset_flags") or []):
            legacy += 1
        if record.get("reference_disagreement"):
            disagreement += 1

    return {
        "map_count": len(maps),
        "object_count": numeric("object_count", lambda r: ((r.get("metadata") or {}).get("counts") or {}).get("objects")),
        "duration_ms": metadata_numeric("duration_ms"),
        "bpm_max": metadata_numeric("bpm_max"),
        "AR": difficulty_numeric("AR"),
        "OD": difficulty_numeric("OD"),
        "CS": difficulty_numeric("CS"),
        "HP": difficulty_numeric("HP"),
        "format_version": dict(sorted(format_counter.items())),
        "pathological_count": pathological,
        "pathological_rate": pathological / len(maps) if maps else None,
        "geometry_blocked_count": geometry_blocked,
        "geometry_blocked_rate": geometry_blocked / len(maps) if maps else None,
        "legacy_format_count": legacy,
        "legacy_format_rate": legacy / len(maps) if maps else None,
        "reference_disagreement_count": disagreement,
        "reference_disagreement_rate": disagreement / len(maps) if maps else None,
    }


def _quantiles(values: list[float]) -> dict:
    if not values:
        return {}
    values = sorted(values)
    n = len(values)

    def pct(p):
        if n == 1:
            return values[0]
        rank = p * (n - 1)
        low = int(rank)
        high = min(low + 1, n - 1)
        frac = rank - low
        return values[low] + (values[high] - values[low]) * frac

    mean = sum(values) / n
    return {
        "count": n,
        "min": values[0],
        "p1": pct(0.01),
        "p5": pct(0.05),
        "p25": pct(0.25),
        "p50": pct(0.50),
        "p75": pct(0.75),
        "p95": pct(0.95),
        "p99": pct(0.99),
        "max": values[-1],
        "mean": mean,
    }


def generate(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    feature_qa = Path(args.feature_qa)
    ref_qa = Path(args.ref_qa)
    disagreement = Path(args.disagreement)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    workers = max(1, min(int(args.workers), MAX_WORKERS))

    diagnostics: list[str] = []
    header, records, manifest_diag = _load_manifest_records(manifest, args.seed)
    diagnostics.extend(manifest_diag)

    if getattr(args, "shuffle_input", False):
        rng = random.Random(12345)
        rng.shuffle(records)

    feature_flags, ref_flags = _load_qa_flags(feature_qa, ref_qa)
    diagnostics.extend(_annotate_qa(records, feature_flags, ref_flags))

    candidates = _load_candidates(disagreement)
    disagreement_checksums = set(candidates)
    for record in records:
        record["reference_disagreement"] = record["map_checksum"] in disagreement_checksums

    identity = _identity_audit(records)
    near_duplicate = _near_duplicate_diagnostics(records)

    seed = args.seed
    set_rows_all, set_assignments = _make_assignments(
        records, ["set_group_key"], include_unknown=True, seed=seed
    )
    set_split_rows = build_split_records(set_rows_all, set_assignments, benchmark="set_disjoint")

    known_records = [r for r in records if r["mapper_identity_quality"] == "NAME_ONLY"]
    unknown_records = [r for r in records if r["mapper_identity_quality"] == "UNKNOWN"]
    mapper_known, mapper_assignments = _make_assignments(
        known_records, ["mapper_group_key"], include_unknown=False, seed=seed
    )
    mapper_split_rows = build_split_records(mapper_known, mapper_assignments, benchmark="mapper_disjoint")
    unknown_split_rows = [
        {
            "map_checksum": r["map_checksum"],
            "sample_id": r.get("sample_id"),
            "beatmap_id": r.get("beatmap_id"),
            "set_group_key": r.get("set_group_key"),
            "set_group_policy": r.get("set_group_policy"),
            "mapper_group_key": r.get("mapper_group_key"),
            "mapper_identity_quality": r.get("mapper_identity_quality"),
            "split": "unknown",
            "benchmark": "mapper_disjoint_unknown",
        }
        for r in sorted(unknown_records, key=lambda r: (r["map_checksum"], r.get("sample_id") or ""))
    ]

    strict_rows, strict_assignments = _make_assignments(
        records, ["set_group_key", "mapper_group_key"], include_unknown=True, seed=seed
    )
    strict_split_rows = build_split_records(strict_rows, strict_assignments, benchmark="strict_disjoint")

    split_by_checksum = {r["map_checksum"]: r for r in set_split_rows}
    legacy_rows = [
        row for row in set_split_rows if "legacy_format" in (row.get("subset_flags") or [])
    ]
    pathological_rows = [
        row for row in set_split_rows if row.get("pathological_reasons")
    ]
    disagreement_rows = []
    for checksum in sorted(disagreement_checksums):
        row = split_by_checksum.get(checksum)
        if row is None:
            diagnostics.append(f"disagreement candidate missing from corpus: {checksum}")
            continue
        disagreement_rows.append(
            {
                "map_checksum": checksum,
                "sample_id": row.get("sample_id"),
                "beatmap_id": row.get("beatmap_id"),
                "set_group_key": row.get("set_group_key"),
                "split": row.get("split"),
                "candidate_count": len(candidates[checksum]),
                "object_indexes": sorted({c.get("object_index") for c in candidates[checksum] if c.get("object_index") is not None}),
                "reasons": sorted({c.get("reason") for c in candidates[checksum] if c.get("reason")}),
            }
        )

    distribution = _distribution_audit(records, set_assignments, set_split_rows)
    challenge_counts = {
        "legacy_format_ood": len(legacy_rows),
        "pathological_challenge": len(pathological_rows),
        "reference_disagreement_challenge": len(disagreement_rows),
        "reference_disagreement_candidate_objects": sum(
            len(candidates[c]) for c in disagreement_checksums
        ),
    }

    files = {
        "set_disjoint.jsonl": set_split_rows,
        "mapper_disjoint.jsonl": mapper_split_rows,
        "mapper_disjoint_unknown.jsonl": unknown_split_rows,
        "strict_disjoint.jsonl": strict_split_rows,
        "legacy_format_ood.jsonl": legacy_rows,
        "pathological_challenge.jsonl": pathological_rows,
        "reference_disagreement_challenge.jsonl": disagreement_rows,
    }
    written: dict[str, str] = {}
    for name, rows in files.items():
        path = out_dir / name
        _write_jsonl(path, rows)
        written[name] = _sha256_file(path)

    identity_path = out_dir / "identity_audit.json"
    identity_path.write_text(
        json.dumps(identity, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    written["identity_audit.json"] = _sha256_file(identity_path)

    near_path = out_dir / "near_duplicate_diagnostics.jsonl"
    _write_jsonl(
        near_path,
        [
            {
                "classification": example["classification"],
                "left_checksum": example["left_checksum"],
                "right_checksum": example["right_checksum"],
                "left_sample_id": example["left_sample_id"],
                "right_sample_id": example["right_sample_id"],
                "duration_close": example["duration_close"],
                "objects_equal": example["objects_equal"],
            }
            for example in near_duplicate["examples"]
        ],
    )
    written["near_duplicate_diagnostics.jsonl"] = _sha256_file(near_path)

    distribution_path = out_dir / "distribution_audit.json"
    distribution_path.write_text(
        json.dumps(distribution, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    written["distribution_audit.json"] = _sha256_file(distribution_path)

    elapsed = time.time() - started
    summary = {
        "dataset_version": "v0.1",
        "split_version": SPLIT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "source_manifest_checksum": source_manifest_checksum(str(manifest)),
        "source_record_count": len(records),
        "feature_version": header.get("feature_version"),
        "local_signal_version": "0.2.0",
        "reference_signal_version": "0.1.0",
        "seed": seed,
        "set_group_policy": "beatmapset_id if present else local_set_group",
        "mapper_identity_policy": "normalised exact creator name (NAME_ONLY); creator_id unavailable",
        "challenge_subset_versions": {
            "legacy_format_ood": "0.1.0",
            "pathological_challenge": "0.1.0",
            "reference_disagreement_challenge": "0.1.0",
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "workers": workers,
        "wall_time_seconds": round(elapsed, 3),
        "worktree": _git_state(Path(__file__).resolve().parents[1]),
        "identity_audit": {
            "checksum_classes": identity["checksum_classes"],
            "checksum_conflict_count": identity["checksum_conflict_count"],
            "beatmap_id_conflict_count": identity["beatmap_id_conflict_count"],
            "unknown_mapper_count": identity["unknown_mapper_count"],
            "mapper_group_count": identity["mapper_group_count"],
            "mapper_raw_name_variant_groups": identity["mapper_raw_name_variant_groups"],
        },
        "near_duplicate": {
            "total_pair_count": near_duplicate["total_pair_count"],
            "example_count": near_duplicate["example_count"],
        },
        "split_counts": {
            "set_disjoint": {
                split: len([r for r in set_split_rows if r["split"] == split])
                for split in ("train", "val", "test")
            },
            "mapper_disjoint": {
                split: len([r for r in mapper_split_rows if r["split"] == split])
                for split in ("train", "val", "test")
            },
            "mapper_disjoint_unknown": len(unknown_split_rows),
            "strict_disjoint": {
                split: len([r for r in strict_split_rows if r["split"] == split])
                for split in ("train", "val", "test")
            },
        },
        "challenge_counts": challenge_counts,
        "files": written,
        "diagnostics": diagnostics,
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    written["summary.json"] = _sha256_file(summary_path)

    dataset_manifest = {
        "dataset_version": summary["dataset_version"],
        "split_version": SPLIT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "source_manifest_checksum": summary["source_manifest_checksum"],
        "source_record_count": len(records),
        "feature_version": header.get("feature_version"),
        "local_signal_version": "0.2.0",
        "reference_signal_version": "0.1.0",
        "set_group_policy": summary["set_group_policy"],
        "mapper_identity_policy": summary["mapper_identity_policy"],
        "challenge_subset_versions": summary["challenge_subset_versions"],
        "generated_at": summary["generated_at"],
        "worktree": summary["worktree"],
        "files": written,
    }
    dataset_manifest_path = out_dir / "manifest.json"
    dataset_manifest_path.write_text(
        json.dumps(dataset_manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    written["manifest.json"] = _sha256_file(dataset_manifest_path)

    if args.verify:
        verify_args = argparse.Namespace(
            out=out_dir,
            manifest=args.manifest,
            disagreement=args.disagreement,
            seed=seed,
        )
        errors = verify(verify_args)
        if errors:
            diagnostics.extend(errors)

    print(json.dumps({
        "out_dir": str(out_dir),
        "source_record_count": len(records),
        "split_counts": summary["split_counts"],
        "challenge_counts": summary["challenge_counts"],
        "wall_time_seconds": round(elapsed, 3),
        "workers": workers,
        "diagnostics_count": len(diagnostics),
        "errors": diagnostics[:50],
    }, ensure_ascii=False, indent=2))
    return 1 if diagnostics else 0


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def verify(args: argparse.Namespace) -> list[str]:
    out_dir = Path(args.out)
    errors: list[str] = []

    summary_path = out_dir / "summary.json"
    if not summary_path.exists():
        return [f"missing summary: {summary_path}"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("seed") != args.seed:
        errors.append(f"seed mismatch: {summary.get('seed')!r} != {args.seed!r}")

    set_rows = _load_jsonl(out_dir / "set_disjoint.jsonl")
    mapper_rows = _load_jsonl(out_dir / "mapper_disjoint.jsonl")
    unknown_rows = _load_jsonl(out_dir / "mapper_disjoint_unknown.jsonl")
    strict_rows = _load_jsonl(out_dir / "strict_disjoint.jsonl")
    legacy_rows = _load_jsonl(out_dir / "legacy_format_ood.jsonl")
    pathological_rows = _load_jsonl(out_dir / "pathological_challenge.jsonl")
    disagreement_rows = _load_jsonl(out_dir / "reference_disagreement_challenge.jsonl")

    _validate_schema(set_rows, errors, "set_disjoint")
    _validate_schema(mapper_rows, errors, "mapper_disjoint")
    _validate_schema(unknown_rows, errors, "mapper_disjoint_unknown")
    _validate_schema(strict_rows, errors, "strict_disjoint")
    _validate_schema(legacy_rows, errors, "legacy_format_ood")
    _validate_schema(pathological_rows, errors, "pathological_challenge")
    _validate_schema(
        disagreement_rows,
        errors,
        "reference_disagreement_challenge",
        require_mapper=False,
    )

    source_ids = _source_identity_set(Path(args.manifest))
    set_ids = {(r["map_checksum"], r.get("sample_id")) for r in set_rows}
    missing = source_ids - set_ids
    extra = set_ids - source_ids
    if missing:
        errors.append(f"set_disjoint coverage missing {len(missing)} rows")
    if extra:
        errors.append(f"set_disjoint has {len(extra)} rows not in source manifest")

    _check_no_split_leakage(set_rows, "set_group_key", "set_disjoint", errors)
    _check_no_split_leakage(set_rows, "map_checksum", "set_disjoint", errors)
    _check_no_split_leakage(mapper_rows, "mapper_group_key", "mapper_disjoint", errors)
    _check_no_split_leakage(mapper_rows, "map_checksum", "mapper_disjoint", errors)
    _check_no_split_leakage(strict_rows, "set_group_key", "strict_disjoint", errors)
    _check_no_split_leakage(strict_rows, "mapper_group_key", "strict_disjoint", errors)
    _check_no_split_leakage(strict_rows, "map_checksum", "strict_disjoint", errors)

    if unknown_rows:
        if any(r.get("split") != "unknown" for r in unknown_rows):
            errors.append("mapper_disjoint_unknown rows must all have split=unknown")
        if any(r.get("mapper_identity_quality") != "UNKNOWN" for r in unknown_rows):
            errors.append("mapper_disjoint_unknown rows must all have UNKNOWN quality")

    set_by_key = {(r["map_checksum"], r.get("sample_id")): r for r in set_rows}
    for label, rows in (
        ("legacy_format_ood", legacy_rows),
        ("pathological_challenge", pathological_rows),
    ):
        for row in rows:
            key = (row["map_checksum"], row.get("sample_id"))
            if key not in set_by_key:
                errors.append(f"{label} row not in set_disjoint: {key}")
        seen = {(r["map_checksum"], r.get("sample_id")) for r in rows}
        if len(seen) != len(rows):
            errors.append(f"{label} contains duplicate rows")
    for row in legacy_rows:
        if "legacy_format" not in (row.get("subset_flags") or []):
            errors.append(f"legacy row missing legacy_format flag: {row['map_checksum']}")
    for row in pathological_rows:
        if not row.get("pathological_reasons"):
            errors.append(f"pathological row missing reasons: {row['map_checksum']}")

    candidates = _load_candidates(Path(args.disagreement))
    seen_disagreement = set()
    for row in disagreement_rows:
        checksum = row["map_checksum"]
        if checksum not in candidates:
            errors.append(f"disagreement row not in source candidates: {checksum}")
        if checksum in seen_disagreement:
            errors.append(f"duplicate disagreement row: {checksum}")
        seen_disagreement.add(checksum)
        if row.get("candidate_count") != len(candidates.get(checksum, [])):
            errors.append(f"disagreement candidate_count mismatch: {checksum}")
    for checksum in candidates:
        if checksum not in seen_disagreement:
            errors.append(f"disagreement candidate missing from challenge: {checksum}")

    _verify_file_checksums(out_dir, summary, errors)
    return errors


def _validate_schema(
    rows: list[dict],
    errors: list[str],
    label: str,
    *,
    require_mapper: bool = True,
) -> None:
    allowed_splits = {"train", "val", "test", "unknown"}
    previous: tuple | None = None
    for row in rows:
        checksum = row.get("map_checksum")
        if not isinstance(checksum, str) or not CHECKSUM_RE.fullmatch(checksum):
            errors.append(f"{label}: invalid map_checksum {checksum!r}")
        if row.get("split") not in allowed_splits:
            errors.append(f"{label}: invalid split {row.get('split')!r}")
        if not row.get("set_group_key"):
            errors.append(f"{label}: missing set_group_key for {checksum}")
        if require_mapper:
            if not row.get("mapper_group_key"):
                errors.append(f"{label}: missing mapper_group_key for {checksum}")
            if row.get("mapper_identity_quality") not in ("NAME_ONLY", "UNKNOWN"):
                errors.append(f"{label}: invalid mapper identity quality")
        current = (checksum, row.get("sample_id"))
        if previous is not None and current < previous:
            errors.append(f"{label}: rows not in canonical sorted order at {current}")
        previous = current


def _source_identity_set(manifest: Path) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for sample in stream_manifest_samples(str(manifest)):
        checksum = sample.get("checksum") or sample.get("sha256")
        if isinstance(checksum, str) and CHECKSUM_RE.fullmatch(checksum):
            out.add((checksum, sample.get("sample_id")))
    return out


def _check_no_split_leakage(rows: list[dict], key: str, label: str, errors: list[str]) -> None:
    seen: dict[Any, set[str]] = defaultdict(set)
    for row in rows:
        split = row.get("split")
        if split in ("unknown", None):
            continue
        seen[row.get(key)].add(split)
    violations = {value: sorted(splits) for value, splits in seen.items() if len(splits) > 1}
    if violations:
        errors.append(
            f"{label}: {key} crosses splits ({len(violations)} groups)"
        )


def _verify_file_checksums(out_dir: Path, summary: dict, errors: list[str]) -> None:
    expected = summary.get("files") or {}
    for name, digest in expected.items():
        path = out_dir / name
        if not path.exists():
            errors.append(f"missing output file: {name}")
            continue
        actual = _sha256_file(path)
        if actual != digest:
            errors.append(f"checksum mismatch for {name}: {actual} != {digest}")


def regenerate_check(args: argparse.Namespace) -> int:
    """Regenerate into a temp dir and compare content checksums."""

    import tempfile

    out_dir = Path(args.out)
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    original_files = summary.get("files") or {}
    content_files = [
        name
        for name in original_files
        if name not in ("summary.json", "manifest.json")
    ]
    errors: list[str] = []

    for shuffle in (False, True):
        with tempfile.TemporaryDirectory(prefix="split-regen-") as tmp:
            tmp_path = Path(tmp)
            gen_args = argparse.Namespace(
                manifest=args.manifest,
                feature_qa=args.feature_qa,
                ref_qa=args.ref_qa,
                disagreement=args.disagreement,
                out=str(tmp_path),
                seed=args.seed,
                workers=args.workers,
                shuffle_input=shuffle,
                verify=False,
            )
            generate(gen_args)
            for name in content_files:
                digest = original_files[name]
                path = tmp_path / name
                if not path.exists():
                    errors.append(f"regenerated missing {name}")
                    continue
                if _sha256_file(path) != digest:
                    errors.append(
                        f"regeneration mismatch ({'shuffled' if shuffle else 'same order'}): {name}"
                    )
    if errors:
        print("REGEN FAIL", len(errors))
        for error in errors[:20]:
            print(error)
        return 1
    print("REGEN OK: byte-identical regeneration in same order and shuffled order")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--manifest", required=True)
    common.add_argument("--feature-qa", required=True)
    common.add_argument("--ref-qa", required=True)
    common.add_argument("--disagreement", required=True)
    common.add_argument("--out", required=True)
    common.add_argument("--seed", default=DEFAULT_SEED)
    common.add_argument("--workers", type=int, default=DEFAULT_WORKERS)

    gen = sub.add_parser("generate", parents=[common])
    gen.add_argument("--verify", action="store_true", default=True)
    gen.add_argument("--shuffle-input", action="store_true", default=False)
    gen.set_defaults(handler=generate)

    ver = sub.add_parser("verify", parents=[common])
    ver.set_defaults(
        handler=lambda a: _run_verify(a)
    )

    regen = sub.add_parser("regenerate-check", parents=[common])
    regen.add_argument("--shuffle-input", action="store_true", default=False)
    regen.set_defaults(handler=regenerate_check)

    args = parser.parse_args(argv)
    return args.handler(args)


def _run_verify(args: argparse.Namespace) -> int:
    errors = verify(args)
    if errors:
        print(f"VERIFY FAIL: {len(errors)} errors")
        for error in errors[:100]:
            print(error)
        return 1
    print("VERIFY OK: all constraints hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
