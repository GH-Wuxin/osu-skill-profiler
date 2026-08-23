#!/usr/bin/env python3
"""Build the deterministic Active Learning + Human Annotation v0.1 dry run."""

from __future__ import annotations

from collections import defaultdict
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

from osu_skill_profiler.active_learning.batch_v01 import BatchConfig, build_batch  # noqa: E402
from osu_skill_profiler.active_learning.contracts_v01 import canonical_json  # noqa: E402
from osu_skill_profiler.active_learning.presentation_v01 import DEFAULT_PRESENTATION, blind_task_payload  # noqa: E402
from osu_skill_profiler.active_learning.selection_v01 import candidate_diagnostics, extract_candidates  # noqa: E402


SCHEMA_VERSION = "0.1.0"
GENERATOR_VERSION = "0.1.0"
DEFAULT_EVIDENCE = ROOT / "training/datasets/weak_supervision_v01/pilot/evidence.jsonl"
DEFAULT_SELECTION = ROOT / "training/datasets/weak_supervision_v01/pilot/selection.jsonl"
DEFAULT_FEATURE = ROOT / "training/datasets/feature_qa_v02/feature_qa_5k.jsonl"
DEFAULT_SPLIT = ROOT / "training/datasets/splits/v02/set_disjoint.jsonl"
DEFAULT_SPLIT_DIR = ROOT / "training/datasets/splits/v02"
DEFAULT_UNAVAILABLE = ROOT / "training/datasets/active_learning_v01/dry_run/unavailable_summary.json"
DEFAULT_OUTPUT = ROOT / "training/datasets/active_learning_v01/dry_run"


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in {path.name}:{line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"non-object JSON row in {path.name}:{line_number}")
            yield row


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _strict(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite at {path}")
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or (len(normalized) >= 3 and normalized[1:3] == ":/"):
            raise ValueError(f"absolute path at {path}")
    elif isinstance(value, dict):
        for key, item in value.items():
            _strict(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _strict(item, f"{path}[{index}]")


def _selected_jsonl(path: Path, checksums: set[str], key: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in iter_jsonl(path):
        checksum = row.get(key)
        if checksum in checksums:
            rows[str(checksum)] = row
    missing = checksums - rows.keys()
    if missing:
        raise ValueError(f"{path.name} missing {len(missing)} selected maps")
    return rows


def _challenge_memberships(split_dir: Path) -> dict[str, tuple[str, ...]]:
    memberships: dict[str, set[str]] = defaultdict(set)
    for name in ("legacy_format_ood", "pathological_challenge", "reference_disagreement_challenge"):
        for row in iter_jsonl(split_dir / f"{name}.jsonl"):
            checksum = row.get("map_checksum") or row.get("checksum")
            if checksum:
                memberships[str(checksum)].add(name)
    return {checksum: tuple(sorted(names)) for checksum, names in memberships.items()}


def _write(path: Path, value: Any, *, jsonl: bool = False) -> dict[str, Any]:
    _strict(value)
    if jsonl:
        payload = ("\n".join(canonical_json(row) for row in value) + "\n").encode("utf-8")
    else:
        payload = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return {"bytes": len(payload), "sha256": sha256_bytes(payload)}


def build_dry_run(
    evidence_path: Path,
    selection_path: Path,
    feature_path: Path,
    split_path: Path,
    split_dir: Path,
    unavailable_path: Path,
    output_dir: Path,
    config: BatchConfig,
) -> dict[str, Any]:
    evidence = list(iter_jsonl(evidence_path))
    pilot_selection = list(iter_jsonl(selection_path))
    checksums = {str(row["map_checksum"]) for row in pilot_selection}
    features = _selected_jsonl(feature_path, checksums, "checksum")
    split_rows = _selected_jsonl(split_path, checksums, "map_checksum")
    challenge = _challenge_memberships(split_dir)
    unavailable = json.loads(unavailable_path.read_text(encoding="utf-8"))
    if unavailable.get("active_learning_gate") != "PASS" or unavailable.get("classification_counts", {}).get("unresolved") != 0:
        raise ValueError("UNAVAILABLE classification gate has not passed")
    candidates = extract_candidates(evidence, split_rows, features, challenge)
    tasks, batch_diagnostics = build_batch(candidates, config)
    task_rows = [task.as_dict() for task in tasks]
    blind_rows = [blind_task_payload(task) for task in tasks]
    diagnostics = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "candidates": candidate_diagnostics(candidates),
        "batch": batch_diagnostics,
        "unavailable_classification": {
            "total": unavailable["total"],
            "classification_counts": unavailable["classification_counts"],
            "active_learning_gate": unavailable["active_learning_gate"],
            "unexpected_defects": unavailable["unexpected_defects"],
        },
        "presentation_blindness_checked": True,
        "real_human_responses_collected": 0,
        "human_semantic_conclusions": None,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "batch.jsonl": _write(output_dir / "batch.jsonl", task_rows, jsonl=True),
        "blind_batch.jsonl": _write(output_dir / "blind_batch.jsonl", blind_rows, jsonl=True),
        "diagnostics.json": _write(output_dir / "diagnostics.json", diagnostics),
        "presentation_contract.json": _write(output_dir / "presentation_contract.json", DEFAULT_PRESENTATION.as_dict()),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "batch_builder_version": "0.1.0",
        "seed": config.seed,
        "inputs": {
            "weak_evidence": {"artifact": evidence_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(evidence_path), "bytes": evidence_path.stat().st_size},
            "pilot_selection": {"artifact": selection_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(selection_path), "bytes": selection_path.stat().st_size},
            "feature": {"artifact": feature_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(feature_path), "bytes": feature_path.stat().st_size},
            "split": {"artifact": split_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(split_path), "bytes": split_path.stat().st_size},
            "unavailable_summary": {"artifact": unavailable_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(unavailable_path), "bytes": unavailable_path.stat().st_size},
        },
        "outputs": outputs,
        "task_count": len(tasks),
        "strict_serialization": True,
        "no_absolute_paths": True,
        "no_timestamps_or_random_uuids": True,
        "no_model_trained": True,
        "taxonomy_frozen": False,
        "human_evidence_is_ground_truth": False,
    }
    manifest_info = _write(output_dir / "manifest.json", manifest)
    return {"manifest": manifest, "manifest_file": manifest_info, "diagnostics": diagnostics}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--feature", type=Path, default=DEFAULT_FEATURE)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    parser.add_argument("--unavailable", type=Path, default=DEFAULT_UNAVAILABLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_dry_run(
        args.evidence, args.selection, args.feature, args.split, args.split_dir,
        args.unavailable, args.output, BatchConfig(),
    )
    print(canonical_json({
        "status": "PASS",
        "task_count": result["manifest"]["task_count"],
        "manifest_sha256": result["manifest_file"]["sha256"],
        "batch_sha256": result["manifest"]["outputs"]["batch.jsonl"]["sha256"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
