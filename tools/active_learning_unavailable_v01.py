#!/usr/bin/env python3
"""Classify every Weak Supervision v0.1 pilot UNAVAILABLE record.

This is a bounded, read-only source audit. It reuses the production Local
0.3 canonical segmentation implementation and does not change Foundation or
Weak Supervision semantics. Outputs are deterministic evidence for the Active
Learning v0.1 design gate, not labels or ground truth.
"""

from __future__ import annotations

from collections import Counter
import argparse
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

from osu_skill_profiler.signals.extractor import segment_local_signals  # noqa: E402


SCHEMA_VERSION = "0.1.0"
GENERATOR_VERSION = "0.1.0"
DEFAULT_EVIDENCE = ROOT / "training/datasets/weak_supervision_v01/pilot/evidence.jsonl"
DEFAULT_FEATURE = ROOT / "training/datasets/feature_qa_v02/feature_qa_5k.jsonl"
DEFAULT_LOCAL = ROOT / "training/datasets/local_signal_qa_v03/local_signal_qa_5k.jsonl"
DEFAULT_REFERENCE = ROOT / "training/datasets/reference_signal_qa_v02/reference_qa_5k.jsonl"
DEFAULT_OUTPUT = ROOT / "training/datasets/active_learning_v01/dry_run"

CLASS_LEGITIMATE = "legitimate_unavailable"
CLASS_UNEXPECTED = "unexpected_unavailable"
CLASS_UNRESOLVED = "unresolved"

LOCAL_BLOCKING_PREFIXES = (
    "path_blocked:",
    "slider_spans_exceeded",
    "slider_tick_count_exceeded",
)


def canonical_json(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":") if indent is None else None,
        indent=indent,
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at line {line_number} in {path.name}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object at line {line_number} in {path.name}")
            yield value


def load_unavailable(path: Path) -> list[dict[str, Any]]:
    records = [row for row in iter_jsonl(path) if row.get("status") == "UNAVAILABLE"]
    return sorted(records, key=record_key)


def record_key(record: dict[str, Any]) -> tuple[Any, ...]:
    entity = record["entity"]
    return (
        entity["map_checksum"],
        entity["scope"],
        entity.get("segment_index", -1),
        record["rule"]["id"],
        record["rule"]["version"],
    )


def record_id(record: dict[str, Any]) -> str:
    identity = {
        "entity": record["entity"],
        "proposition": record["proposition"],
        "rule": record["rule"],
        "source": record["source"],
    }
    return "al01-unavailable-" + hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()[:20]


def load_selected_rows(path: Path, checksums: set[str]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
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
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid selected row at line {line_number} in {path.name}") from exc
            checksum = row.get("checksum")
            if checksum in rows:
                raise ValueError(f"duplicate checksum {checksum} in {path.name}")
            rows[str(checksum)] = row
    missing = sorted(checksums - set(rows))
    if missing:
        raise ValueError(f"missing source rows in {path.name}: {missing}")
    return rows


def source_snapshot(
    feature: dict[str, Any],
    local: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    return {
        "feature": {
            "artifact": "training/datasets/feature_qa_v02/feature_qa_5k.jsonl",
            "checksum": feature["checksum"],
            "feature_version": feature.get("feature_version"),
            "ok": feature.get("ok"),
            "sample_id": feature.get("sample_id"),
        },
        "local": {
            "artifact": "training/datasets/local_signal_qa_v03/local_signal_qa_5k.jsonl",
            "checksum": local["checksum"],
            "signal_version": local.get("signal_version", "0.3.0"),
            "ok": local.get("ok"),
        },
        "reference": {
            "artifact": "training/datasets/reference_signal_qa_v02/reference_qa_5k.jsonl",
            "checksum": reference["checksum"],
            "reference_version": reference.get("reference_version"),
            "ok": reference.get("ok"),
            "reference_only": True,
        },
    }


def build_local_segments(row: dict[str, Any]) -> list[dict[str, Any]]:
    objects = list(row.get("objects", []))
    ordered = sorted(
        objects,
        key=lambda value: (value.get("ls.start_time_ms", 0), value.get("ls.original_index", 0)),
    )
    canonical = segment_local_signals(objects, signal_version="0.3.0")
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(canonical):
        members = ordered[segment["start_idx"] : segment["end_idx"]]
        aggregate = segment.get("aggregates", {}).get("ls.lazy_travel_distance_cs_normalised", {})
        blockers = []
        missing = []
        for member in members:
            flags = tuple(str(flag) for flag in member.get("ls.provenance", []))
            blocking_flags = tuple(
                flag for flag in flags if flag.startswith(LOCAL_BLOCKING_PREFIXES)
            )
            details = {
                "object_index": member.get("ls.original_index"),
                "start_ms": member.get("ls.start_time_ms"),
                "object_type": member.get("ls.object_type"),
                "provenance": list(flags),
            }
            if blocking_flags:
                blockers.append({**details, "blocking_flags": list(blocking_flags)})
            if member.get("ls.lazy_travel_distance_cs_normalised") is None:
                missing.append(details)
        segments.append(
            {
                "segment_index": index,
                "start_ms": segment["start_ms"],
                "end_ms": segment["end_ms"],
                "start_idx": segment["start_idx"],
                "end_idx": segment["end_idx"],
                "object_count": segment["object_count"],
                "lazy_travel_p90": aggregate.get("p90"),
                "lazy_travel_max": aggregate.get("max"),
                "blockers": blockers,
                "missing": missing,
            }
        )
    return segments


def classify_record(
    record: dict[str, Any],
    feature: dict[str, Any],
    local: dict[str, Any],
    reference: dict[str, Any],
    local_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    rule_id = record["rule"]["id"]
    reason = record.get("abstention_reason")
    entity = record["entity"]
    classification = CLASS_UNRESOLVED
    concrete_reason = "UNRESOLVED_SOURCE_SEMANTICS"
    assessment: dict[str, Any] = {}
    blocks_phase = True

    if reason == "GEOMETRY_BLOCKED" and rule_id == "ws01.reference.ppy_snap_tail":
        validation = reference.get("validation", {})
        blocked_count = int(validation.get("geometry_blocked_count", 0))
        classification = CLASS_LEGITIMATE if blocked_count > 0 else CLASS_UNRESOLVED
        concrete_reason = (
            "REFERENCE_GEOMETRY_GUARD_TRIGGERED"
            if blocked_count > 0
            else "REFERENCE_GEOMETRY_FLAG_NOT_REPRODUCED"
        )
        assessment = {
            "reference_geometry_blocked_count": blocked_count,
            "reference_unavailable_rows": validation.get("unavailable_rows"),
            "policy": "Reference map rule fails closed when any protected geometry is blocked",
        }
        blocks_phase = blocked_count <= 0

    elif reason == "GEOMETRY_BLOCKED" and rule_id == "ws01.local.slider_travel_segment":
        index = int(entity["segment_index"])
        segment = local_segments[index] if 0 <= index < len(local_segments) else None
        bounds_match = bool(
            segment
            and segment["start_ms"] == entity.get("segment_start_ms")
            and segment["end_ms"] == entity.get("segment_end_ms")
        )
        blockers = [] if segment is None else segment["blockers"]
        classification = CLASS_LEGITIMATE if bounds_match and blockers else CLASS_UNRESOLVED
        concrete_reason = (
            "LOCAL_SEGMENT_CONTAINS_GUARDED_SLIDER_GEOMETRY"
            if classification == CLASS_LEGITIMATE
            else "LOCAL_GEOMETRY_FLAG_NOT_REPRODUCED"
        )
        assessment = {
            "canonical_bounds_match": bounds_match,
            "segment_object_count": None if segment is None else segment["object_count"],
            "blocking_objects": blockers,
            "policy": "Local segment rule fails closed rather than aggregating across blocked geometry",
        }
        blocks_phase = classification != CLASS_LEGITIMATE

    elif reason == "MISSING_REQUIRED_SIGNAL" and rule_id == "ws01.observable.movement_tail":
        values = feature.get("features", {})
        distance = values.get("spatial.distance_norm_p95")
        velocity = values.get("spatial.velocity_norm_per_s_p95")
        object_count = feature.get("object_count")
        sparse = object_count == 1 and distance is None and velocity is None
        classification = CLASS_LEGITIMATE if sparse else CLASS_UNRESOLVED
        concrete_reason = (
            "SINGLE_OBJECT_MAP_HAS_NO_MOVEMENT_TRANSITION"
            if sparse
            else "MOVEMENT_TAIL_MISSING_WITHOUT_SPARSE_MAP_EXPLANATION"
        )
        assessment = {
            "object_count": object_count,
            "distance_norm_p95": distance,
            "velocity_norm_per_s_p95": velocity,
            "feature_flags": feature.get("flags", []),
        }
        blocks_phase = not sparse

    elif reason == "REFERENCE_UNAVAILABLE" and rule_id == "ws01.reference.ppy_snap_tail":
        raw = [
            obj.get("ref.ppy.snap_include_sliders")
            for obj in reference.get("objects", [])
            if isinstance(obj.get("ref.ppy.snap_include_sliders"), (int, float))
            and math.isfinite(float(obj["ref.ppy.snap_include_sliders"]))
        ]
        positive = [float(value) for value in raw if float(value) > 0]
        zeros = [value for value in raw if float(value) == 0]
        missing_count = sum(
            obj.get("ref.ppy.snap_include_sliders") is None
            for obj in reference.get("objects", [])
        )
        if raw and not positive and zeros:
            classification = CLASS_UNEXPECTED
            concrete_reason = "VALID_REFERENCE_ZERO_VALUES_DROPPED_BY_POSITIVE_ONLY_PILOT_SUMMARY"
            blocks_phase = False
        elif not raw and feature.get("object_count") == 1:
            classification = CLASS_LEGITIMATE
            concrete_reason = "SINGLE_OBJECT_MAP_HAS_NO_COMPUTABLE_REFERENCE_TRANSITION"
            blocks_phase = False
        else:
            classification = CLASS_UNRESOLVED
            concrete_reason = "REFERENCE_SUMMARY_EMPTY_WITHOUT_SUPPORTED_EXPLANATION"
            blocks_phase = True
        assessment = {
            "finite_reference_values": len(raw),
            "positive_reference_values": len(positive),
            "zero_reference_values": len(zeros),
            "missing_reference_values": missing_count,
            "object_count": feature.get("object_count"),
            "known_defect": classification == CLASS_UNEXPECTED,
            "defect_impact": (
                "one valid all-zero Reference map was marked UNAVAILABLE instead of producing negative evidence"
                if classification == CLASS_UNEXPECTED
                else None
            ),
            "containment": (
                "exclude this map from Active Learning v0.1 candidate construction; preserve Weak Supervision v0.1 artifact unchanged"
                if classification == CLASS_UNEXPECTED
                else None
            ),
        }

    elif reason == "MISSING_REQUIRED_SIGNAL" and rule_id == "ws01.observable.slider_control_load":
        values = feature.get("features", {})
        duration = values.get("slider.duration_ms_p90")
        ratio = values.get("slider.slider_ratio")
        repeats = values.get("slider.repeat_count_total")
        local_sliders = [
            obj for obj in local.get("objects", []) if obj.get("ls.object_type") == "slider"
        ]
        local_finite_duration = sum(
            isinstance(obj.get("ls.slider_total_duration_ms"), (int, float))
            and math.isfinite(float(obj["ls.slider_total_duration_ms"]))
            for obj in local_sliders
        )
        source_is_missing = duration is None and isinstance(ratio, (int, float)) and float(ratio) > 0
        classification = CLASS_LEGITIMATE if source_is_missing else CLASS_UNRESOLVED
        concrete_reason = (
            "DECLARED_FEATURE_DURATION_AGGREGATE_UNAVAILABLE"
            if source_is_missing
            else "SLIDER_CONTROL_SOURCE_MISSING_NOT_REPRODUCED"
        )
        assessment = {
            "feature_slider_ratio": ratio,
            "feature_slider_duration_p90": duration,
            "feature_repeat_count_total": repeats,
            "feature_format_version": feature.get("format_version"),
            "local_slider_count_crosscheck": len(local_sliders),
            "local_finite_total_duration_crosscheck": local_finite_duration,
            "join_defect": False,
            "note": (
                "the declared rule source is Feature 0.2 and its row itself contains null; Local 0.3 values are a different source and are not substituted"
            ),
        }
        blocks_phase = not source_is_missing

    elif reason == "MISSING_REQUIRED_SIGNAL" and rule_id == "ws01.local.slider_travel_segment":
        index = int(entity["segment_index"])
        segment = local_segments[index] if 0 <= index < len(local_segments) else None
        bounds_match = bool(
            segment
            and segment["start_ms"] == entity.get("segment_start_ms")
            and segment["end_ms"] == entity.get("segment_end_ms")
        )
        missing = [] if segment is None else segment["missing"]
        known_timing_guard = bool(missing) and all(
            "beat_length_nonpositive" in item["provenance"] for item in missing
        )
        aggregate_missing = bool(
            segment
            and segment["lazy_travel_p90"] is None
            and segment["lazy_travel_max"] is None
        )
        legitimate = bounds_match and aggregate_missing and known_timing_guard
        classification = CLASS_LEGITIMATE if legitimate else CLASS_UNRESOLVED
        concrete_reason = (
            "ALL_SEGMENT_SLIDER_TRAVEL_VALUES_BLOCKED_BY_NONPOSITIVE_BEAT_LENGTH"
            if legitimate
            else "LOCAL_SEGMENT_AGGREGATE_MISSING_WITHOUT_SUPPORTED_GUARD"
        )
        assessment = {
            "canonical_bounds_match": bounds_match,
            "segment_object_count": None if segment is None else segment["object_count"],
            "lazy_travel_p90": None if segment is None else segment["lazy_travel_p90"],
            "lazy_travel_max": None if segment is None else segment["lazy_travel_max"],
            "missing_objects": missing,
            "join_defect": False,
        }
        blocks_phase = not legitimate

    return {
        "schema_version": SCHEMA_VERSION,
        "classification_id": record_id(record),
        "classification": classification,
        "concrete_reason": concrete_reason,
        "blocks_active_learning_phase": blocks_phase,
        "evidence_record": {
            "entity": record["entity"],
            "proposition": record["proposition"],
            "rule": record["rule"],
            "source": record["source"],
            "abstention_reason": reason,
            "diagnostics": record.get("diagnostics", []),
        },
        "source_snapshot": source_snapshot(feature, local, reference),
        "assessment": assessment,
        "weak_evidence_is_ground_truth": False,
    }


def classify_all(
    evidence_path: Path,
    feature_path: Path,
    local_path: Path,
    reference_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    unavailable = load_unavailable(evidence_path)
    if len(unavailable) != 42:
        raise ValueError(f"expected exactly 42 pilot UNAVAILABLE records, found {len(unavailable)}")
    checksums = {record["entity"]["map_checksum"] for record in unavailable}
    features = load_selected_rows(feature_path, checksums)
    locals_ = load_selected_rows(local_path, checksums)
    references = load_selected_rows(reference_path, checksums)
    local_segments = {
        checksum: build_local_segments(locals_[checksum]) for checksum in sorted(checksums)
    }
    classified = [
        classify_record(
            record,
            features[record["entity"]["map_checksum"]],
            locals_[record["entity"]["map_checksum"]],
            references[record["entity"]["map_checksum"]],
            local_segments[record["entity"]["map_checksum"]],
        )
        for record in unavailable
    ]
    classified.sort(key=lambda item: item["classification_id"])
    counts = Counter(item["classification"] for item in classified)
    blocking = [item["classification_id"] for item in classified if item["blocks_active_learning_phase"]]
    unexpected = [item for item in classified if item["classification"] == CLASS_UNEXPECTED]
    reason_counts = Counter(item["concrete_reason"] for item in classified)
    rule_counts = Counter(item["evidence_record"]["rule"]["id"] for item in classified)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "total": len(classified),
        "classification_counts": {
            CLASS_LEGITIMATE: counts[CLASS_LEGITIMATE],
            CLASS_UNEXPECTED: counts[CLASS_UNEXPECTED],
            CLASS_UNRESOLVED: counts[CLASS_UNRESOLVED],
        },
        "concrete_reason_counts": dict(sorted(reason_counts.items())),
        "rule_counts": dict(sorted(rule_counts.items())),
        "unique_maps": len(checksums),
        "blocking_classification_ids": blocking,
        "unexpected_defects": [
            {
                "defect_id": "ALV01-UNAVAILABLE-001",
                "classification_id": item["classification_id"],
                "layer": "Weak Supervision pilot Reference summary",
                "cause": item["concrete_reason"],
                "impact": item["assessment"]["defect_impact"],
                "phase_blocking": item["blocks_active_learning_phase"],
                "activation": "any downstream use of this map's Reference weak evidence",
                "containment": item["assessment"]["containment"],
                "fix_applied": False,
            }
            for item in unexpected
        ],
        "active_learning_gate": "PASS" if not blocking else "BLOCKED",
        "assessment": (
            "One deterministic pilot summary defect is contained and non-blocking; no Foundation artifact or Weak Supervision v0.1 record was changed."
            if unexpected and not blocking
            else "No blocking unavailable classification remains."
        ),
        "weak_evidence_is_ground_truth": False,
    }
    return classified, summary


def write_outputs(
    classified: list[dict[str, Any]],
    summary: dict[str, Any],
    output_dir: Path,
    inputs: dict[str, Path],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    classification_payload = (
        "\n".join(canonical_json(item) for item in classified) + "\n"
    ).encode("utf-8")
    classification_path = output_dir / "unavailable_classification.jsonl"
    classification_path.write_bytes(classification_payload)
    summary_payload = (canonical_json(summary, indent=2) + "\n").encode("utf-8")
    summary_path = output_dir / "unavailable_summary.json"
    summary_path.write_bytes(summary_payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "inputs": {
            name: {
                "artifact": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for name, path in sorted(inputs.items())
        },
        "outputs": {
            "unavailable_classification.jsonl": {
                "bytes": len(classification_payload),
                "sha256": sha256_bytes(classification_payload),
            },
            "unavailable_summary.json": {
                "bytes": len(summary_payload),
                "sha256": sha256_bytes(summary_payload),
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--feature", type=Path, default=DEFAULT_FEATURE)
    parser.add_argument("--local", type=Path, default=DEFAULT_LOCAL)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    classified, summary = classify_all(args.evidence, args.feature, args.local, args.reference)
    manifest = write_outputs(
        classified,
        summary,
        args.output,
        {
            "weak_evidence": args.evidence,
            "feature": args.feature,
            "local": args.local,
            "reference": args.reference,
        },
    )
    print(canonical_json({"summary": summary, "manifest": manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
