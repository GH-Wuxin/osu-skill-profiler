#!/usr/bin/env python3
"""Deterministic bounded Weak Evidence v0.1 pilot.

The runner joins existing corrected 5k QA artifacts by checksum, selects a
bounded deterministic sample, emits strict JSONL evidence, and writes compact
audit/provenance reports. It does not parse the full corpus or train a model.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from osu_skill_profiler.weak_supervision.audit_v01 import audit_evidence  # noqa: E402
from osu_skill_profiler.weak_supervision.contracts_v01 import EntityRef, EntityScope, RuleContext  # noqa: E402
from osu_skill_profiler.weak_supervision.leakage_v01 import audit_evidence_for_model_inputs  # noqa: E402
from osu_skill_profiler.weak_supervision.pilot_v01 import (  # noqa: E402
    PILOT_PROPOSITIONS,
    PILOT_RULE_REGISTRY,
    PILOT_RULES,
    PILOT_SOURCES,
)
from osu_skill_profiler.weak_supervision.runtime_v01 import canonical_json, execute_rules, serialize_records  # noqa: E402
from osu_skill_profiler.signals.extractor import segment_local_signals  # noqa: E402

PILOT_SCHEMA_VERSION = "0.1.0"
PILOT_GENERATOR_VERSION = "0.1.0"
DEFAULT_SEED = "osu-skill-profiler-weak-supervision-pilot-v01"

DEFAULT_FEATURE = ROOT / "training/datasets/feature_qa_v02/feature_qa_5k.jsonl"
DEFAULT_LOCAL = ROOT / "training/datasets/local_signal_qa_v03/local_signal_qa_5k.jsonl"
DEFAULT_REFERENCE = ROOT / "training/datasets/reference_signal_qa_v02/reference_qa_5k.jsonl"
DEFAULT_SPLITS = ROOT / "training/datasets/splits/v02"
DEFAULT_OUTPUT = ROOT / "training/datasets/weak_supervision_v01/pilot"


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def assert_normalized_output(value: Any, path: str = "$") -> None:
    """Reject non-finite numbers and machine-local path-shaped strings."""

    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite output at {path}")
    if isinstance(value, str):
        lowered = value.replace("\\", "/")
        if len(lowered) >= 3 and lowered[1:3] == ":/":
            raise ValueError(f"absolute Windows path in output at {path}")
        if lowered.startswith("/"):
            raise ValueError(f"absolute POSIX path in output at {path}")
    elif isinstance(value, dict):
        for key, item in value.items():
            assert_normalized_output(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_normalized_output(item, f"{path}[{index}]")


def strict_dump(value: Any, path: Path) -> dict[str, Any]:
    assert_normalized_output(value)
    payload = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"path": path.name, "bytes": len(payload), "sha256": sha256_bytes(payload)}


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            yield value


def iter_selected_jsonl(path: Path, checksums: set[str]) -> Iterable[dict[str, Any]]:
    """Parse only selected giant QA rows after a cheap exact checksum scan."""

    needle = '"checksum": "'
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            start = line.find(needle)
            if start < 0:
                continue
            start += len(needle)
            end = line.find('"', start)
            if end < 0 or line[start:end] not in checksums:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            yield value


def quantile(values: list[float], q: float) -> float | None:
    finite = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not finite:
        return None
    return finite[int(q * (len(finite) - 1))]


def load_challenge_checksums(split_dir: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for name in ("legacy_format_ood", "pathological_challenge", "reference_disagreement_challenge"):
        result[name] = {str(row["map_checksum"]) for row in iter_jsonl(split_dir / f"{name}.jsonl")}
    return result


def load_feature_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in iter_jsonl(path):
        checksum = row.get("checksum")
        if row.get("ok") is True and isinstance(checksum, str) and isinstance(row.get("features"), dict):
            rows[checksum] = row
    return rows


def extract_local_summary(row: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    objects = row.get("objects", [])
    if not objects:
        return [], False
    ordered = sorted(objects, key=lambda value: (value.get("ls.start_time_ms", 0), value.get("ls.original_index", 0)))
    canonical = segment_local_signals(objects, signal_version="0.3.0")
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(canonical):
        aggregate = segment.get("aggregates", {}).get("ls.lazy_travel_distance_cs_normalised", {})
        members = ordered[segment["start_idx"]:segment["end_idx"]]
        segments.append({
            "segment_index": index,
            "start_ms": segment["start_ms"],
            "end_ms": segment["end_ms"],
            "lazy_travel_p90": aggregate.get("p90"),
            "lazy_travel_max": aggregate.get("max"),
            "geometry_blocked": any(
                any(str(flag).startswith(("path_blocked:", "slider_spans_exceeded", "slider_tick_count_exceeded")) for flag in member.get("ls.provenance", []))
                for member in members
            ),
        })
    blocked = any(segment["geometry_blocked"] for segment in segments)
    return segments, blocked


def extract_reference_summary(row: dict[str, Any]) -> tuple[float | None, bool]:
    values = [
        float(obj["ref.ppy.snap_include_sliders"])
        for obj in row.get("objects", [])
        if isinstance(obj.get("ref.ppy.snap_include_sliders"), (int, float))
        and math.isfinite(float(obj["ref.ppy.snap_include_sliders"]))
        and float(obj["ref.ppy.snap_include_sliders"]) > 0
    ]
    validation = row.get("validation", {})
    blocked = bool(validation.get("geometry_blocked_count", 0))
    return quantile(values, .90), blocked


def load_summaries(
    selected_rows: list[dict[str, Any]],
    local_path: Path,
    reference_path: Path,
) -> dict[str, dict[str, Any]]:
    joined: dict[str, dict[str, Any]] = {
        row["checksum"]: {
            "checksum": row["checksum"],
            "sample_id": row.get("sample_id"),
            "feature": row,
            "local_segments": None,
            "local_geometry_blocked": False,
            "reference_snap_p90": None,
            "reference_geometry_blocked": False,
        }
        for row in selected_rows
    }
    selected_checksums = set(joined)
    for row in iter_selected_jsonl(local_path, selected_checksums):
        checksum = row.get("checksum")
        if checksum in joined and row.get("ok") is True:
            segments, blocked = extract_local_summary(row)
            joined[checksum]["local_segments"] = segments
            joined[checksum]["local_geometry_blocked"] = blocked
    for row in iter_selected_jsonl(reference_path, selected_checksums):
        checksum = row.get("checksum")
        if checksum in joined and row.get("ok") is True:
            snap_p90, blocked = extract_reference_summary(row)
            joined[checksum]["reference_snap_p90"] = snap_p90
            joined[checksum]["reference_geometry_blocked"] = blocked
    return joined


def deterministic_rank(seed: str, checksum: str) -> str:
    return hashlib.sha256(f"{PILOT_GENERATOR_VERSION}\n{seed}\n{checksum}".encode()).hexdigest()


def select_pilot(
    feature_rows: dict[str, dict[str, Any]],
    challenges: dict[str, set[str]],
    count: int,
    seed: str,
) -> list[dict[str, Any]]:
    if count < 1 or count > 5000:
        raise ValueError("pilot count must be in [1, 5000]")
    available = list(feature_rows.values())
    if count > len(available):
        raise ValueError(f"requested {count}, only {len(available)} joined maps are available")
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    quotas = {
        "reference_disagreement_challenge": min(25, max(1, count // 40)),
        "pathological_challenge": min(100, max(1, count // 10)),
        "legacy_format_ood": min(100, max(1, count // 10)),
    }
    for category, quota in quotas.items():
        candidates = [row for row in available if row.get("checksum") in challenges[category] and row.get("checksum") not in selected_ids]
        candidates.sort(key=lambda row: (deterministic_rank(seed + ":" + category, row["checksum"]), row["checksum"]))
        for row in candidates[:quota]:
            selected.append(row)
            selected_ids.add(row["checksum"])
    ordinary = [
        row for row in available
        if row.get("checksum") not in selected_ids
        and not any(row.get("checksum") in values for values in challenges.values())
    ]
    ordinary.sort(key=lambda row: (deterministic_rank(seed + ":ordinary", row["checksum"]), row["checksum"]))
    for row in ordinary[: max(0, count - len(selected))]:
        selected.append(row)
        selected_ids.add(row["checksum"])
    if len(selected) < count:
        remainder = [row for row in available if row["checksum"] not in selected_ids]
        remainder.sort(key=lambda row: (deterministic_rank(seed + ":remainder", row["checksum"]), row["checksum"]))
        selected.extend(remainder[: count - len(selected)])
    selected.sort(key=lambda row: row["checksum"])
    return selected


def map_context(row: dict[str, Any]) -> RuleContext:
    values = dict(row["feature"]["features"])
    values["ref.ppy.snap_include_sliders"] = row["reference_snap_p90"]
    return RuleContext(
        entity=EntityRef(EntityScope.MAP, row["checksum"]),
        values=values,
        provenance={
            "feature_version": row["feature"].get("feature_version"),
            "local_signal_version": "0.3.0",
            "reference_version": "0.2.0",
            "reference_only": True,
            "geometry_blocked": row["reference_geometry_blocked"],
        },
    )


def segment_context(checksum: str, segment: dict[str, Any]) -> RuleContext:
    return RuleContext(
        entity=EntityRef(
            EntityScope.SEGMENT,
            checksum,
            segment["segment_index"],
            segment["start_ms"],
            segment["end_ms"],
        ),
        values={"ls.lazy_travel_distance_cs_normalised": segment["lazy_travel_p90"]},
        provenance={
            "local_signal_version": "0.3.0",
            "canonical_segmentation": "LocalSignal fixed-time 5000ms, object start-time assignment",
            "source_segment_max": segment["lazy_travel_max"],
            "geometry_blocked": segment["geometry_blocked"],
        },
    )


def run_pilot(
    *,
    feature_path: Path,
    local_path: Path,
    reference_path: Path,
    split_dir: Path,
    output_dir: Path,
    count: int,
    seed: str,
) -> dict[str, Any]:
    features = load_feature_rows(feature_path)
    challenges = load_challenge_checksums(split_dir)
    selected_features = select_pilot(features, challenges, count, seed)
    joined = load_summaries(selected_features, local_path, reference_path)
    missing = sorted(checksum for checksum, row in joined.items() if row["local_segments"] is None)
    if missing:
        raise RuntimeError(f"selected maps missing corrected Local rows: {missing[:5]}")
    selected = [joined[row["checksum"]] for row in selected_features]

    map_rules = tuple(rule for rule in PILOT_RULES if EntityScope.MAP in rule.definition.applicable_scopes)
    segment_rules = tuple(rule for rule in PILOT_RULES if EntityScope.SEGMENT in rule.definition.applicable_scopes)
    records = []
    selection_rows = []
    for row in selected:
        categories = sorted(name for name, values in challenges.items() if row["checksum"] in values)
        selection_rows.append({"map_checksum": row["checksum"], "categories": categories or ["ordinary"]})
        records.extend(execute_rules(map_context(row), map_rules, PILOT_PROPOSITIONS, PILOT_SOURCES, PILOT_RULE_REGISTRY))
        for segment in row["local_segments"]:
            records.extend(execute_rules(segment_context(row["checksum"], segment), segment_rules, PILOT_PROPOSITIONS, PILOT_SOURCES, PILOT_RULE_REGISTRY))

    output_dir.mkdir(parents=True, exist_ok=True)
    selection_bytes = ("\n".join(canonical_json(row) for row in selection_rows) + "\n").encode()
    evidence_bytes = serialize_records(records)
    assert_normalized_output(selection_rows)
    assert_normalized_output([record.as_dict() for record in records])
    (output_dir / "selection.jsonl").write_bytes(selection_bytes)
    (output_dir / "evidence.jsonl").write_bytes(evidence_bytes)

    audit = audit_evidence(records)
    leakage_results = {
        "independent_observable_input": audit_evidence_for_model_inputs(records, ["difficulty.CS"]).as_dict(),
        "negative_reference_overlap": audit_evidence_for_model_inputs(records, ["ref.ppy.snap_include_sliders"]).as_dict(),
        "negative_challenge_input": audit_evidence_for_model_inputs(records, ["reference_disagreement_challenge"]).as_dict(),
    }
    if leakage_results["independent_observable_input"]["status"] != "PASS":
        raise RuntimeError("independent leakage control unexpectedly failed")
    if leakage_results["negative_reference_overlap"]["status"] != "FAIL" or leakage_results["negative_challenge_input"]["status"] != "FAIL":
        raise RuntimeError("negative leakage controls unexpectedly passed")

    selection_counts = Counter(category for row in selection_rows for category in row["categories"])
    manifest = {
        "schema_version": PILOT_SCHEMA_VERSION,
        "generator_version": PILOT_GENERATOR_VERSION,
        "seed": seed,
        "count": len(selection_rows),
        "selection_strategy": "deterministic challenge quotas then hash-ranked ordinary fill; challenge flags are selection-only",
        "selection_category_counts": dict(sorted(selection_counts.items())),
        "selection_identity_hash": sha256_bytes(selection_bytes),
        "inputs": {
            "feature": {"artifact": feature_path.relative_to(ROOT).as_posix(), "version": "0.2.0", "sha256": sha256_file(feature_path)},
            "local": {"artifact": local_path.relative_to(ROOT).as_posix(), "version": "0.3.0", "sha256": sha256_file(local_path)},
            "reference": {"artifact": reference_path.relative_to(ROOT).as_posix(), "version": "0.2.0", "sha256": sha256_file(reference_path), "reference_only": True},
            "split": {"artifact": split_dir.relative_to(ROOT).as_posix(), "split_version": "0.1.0", "challenge_version": "0.2.0"},
        },
        "outputs": {
            "selection.jsonl": {"bytes": len(selection_bytes), "sha256": sha256_bytes(selection_bytes), "retention": "canonical"},
            "evidence.jsonl": {"bytes": len(evidence_bytes), "sha256": sha256_bytes(evidence_bytes), "retention": "canonical"},
            "audit.json": {"retention": "regenerable"},
            "leakage.json": {"retention": "regenerable"},
            "registries.json": {"retention": "canonical"},
        },
        "storage_estimate": {
            "estimated_bytes_before_run": count * 35 * 1100,
            "assumption": "approximately four map records plus one segment record per non-empty 5s segment at <=1100 bytes each",
            "actual_evidence_bytes": len(evidence_bytes),
        },
        "no_absolute_paths_in_outputs": True,
        "no_model_trained": True,
        "weak_evidence_is_ground_truth": False,
    }
    registries = {
        "schema_version": PILOT_SCHEMA_VERSION,
        "proposition_registry": PILOT_PROPOSITIONS.as_dict(),
        "source_registry": PILOT_SOURCES.as_dict(),
        "rules": [
            {
                "rule_id": definition.rule_id,
                "version": definition.version,
                "source_id": definition.source_id,
                "source_version": definition.source_version,
                "proposition_key": definition.proposition_key,
                "proposition_version": definition.proposition_version,
                "applicable_scopes": [scope.value for scope in definition.applicable_scopes],
                "input_dependencies": list(definition.input_dependencies),
                "confidence_semantics": definition.confidence_semantics,
                "abstention_conditions": list(definition.abstention_conditions),
                "rationale": definition.rationale,
                "discriminator": definition.discriminator,
                "failure_modes": list(definition.failure_modes),
            }
            for definition in PILOT_RULE_REGISTRY.definitions()
        ],
    }

    audit_info = strict_dump(audit, output_dir / "audit.json")
    leakage_info = strict_dump(leakage_results, output_dir / "leakage.json")
    registry_info = strict_dump(registries, output_dir / "registries.json")
    manifest["outputs"]["audit.json"].update(audit_info)
    manifest["outputs"]["leakage.json"].update(leakage_info)
    manifest["outputs"]["registries.json"].update(registry_info)
    manifest_info = strict_dump(manifest, output_dir / "manifest.json")
    return {"manifest": manifest, "manifest_file": manifest_info, "audit": audit, "leakage": leakage_results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature", type=Path, default=DEFAULT_FEATURE)
    parser.add_argument("--local", type=Path, default=DEFAULT_LOCAL)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    result = run_pilot(
        feature_path=args.feature.resolve(), local_path=args.local.resolve(), reference_path=args.reference.resolve(),
        split_dir=args.split_dir.resolve(), output_dir=args.output_dir.resolve(), count=args.count, seed=args.seed,
    )
    print(json.dumps({
        "status": "PASS",
        "count": result["manifest"]["count"],
        "evidence_records": result["audit"]["total_records"],
        "manifest_sha256": result["manifest_file"]["sha256"],
        "output_dir": args.output_dir.as_posix(),
    }, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
