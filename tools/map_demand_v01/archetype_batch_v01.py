"""Batch QA and blind human-review package builder for MAP_ARCHETYPE_V01."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import contract as C
from .archetype_v01 import (
    AXIS_ORDER as ARCHETYPE_AXIS_ORDER,
    AXIS_SCHEMA_VERSION,
    ARCHETYPE_SCHEMA_VERSION,
    LEGACY_AXIS_ORDER,
    LEGACY_AXIS_SCHEMA_VERSION,
    PREVIOUS_ATOMIC_AXIS_SCHEMA_VERSION,
    PREVIOUS_ATOMIC_AXIS_ORDER,
    POLICY_ID,
    classify_axes,
    validate_human_response,
)
from .model import analyze_components


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_key(value: Any) -> str:
    """Keep aggregate JSON object keys sortable and explicit."""
    return value if isinstance(value, str) else "NONE"


def _load_feature_metadata(path: Path) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            checksum = record.get("checksum")
            if checksum:
                metadata[checksum] = {
                    "sample_id": record.get("sample_id"),
                    "path": record.get("path"),
                    "path_abs": record.get("path_abs"),
                    "duration_ms": record.get("duration_ms"),
                    "bpm_max": record.get("bpm_max"),
                    "ar": record.get("ar"),
                    "od": record.get("od"),
                    "cs": record.get("cs"),
                    "object_count": record.get("object_count"),
                }
    return metadata


def read_beatmap_id(path_value: Any) -> int | None:
    """Read the real BeatmapID from an .osu file; never infer it from folders."""
    if not isinstance(path_value, str) or not path_value:
        return None
    path = Path(path_value)
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            for line in fh:
                if line.startswith("BeatmapID:"):
                    value = int(line.partition(":")[2].strip())
                    return value if value > 0 else None
    except (OSError, ValueError):
        return None
    return None


def _load_task_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list) or any(not isinstance(task, dict) for task in tasks):
        raise ValueError(f"invalid task list: {path}")
    ids = [task.get("task_id") for task in tasks]
    if any(not isinstance(task_id, str) or not task_id for task_id in ids):
        raise ValueError(f"missing task_id in: {path}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate task_id in: {path}")
    return tasks


def _select_review_items(results: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    classified = [row for row in results if row["archetype"]["status"] == "CLASSIFIED"]
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in classified:
        by_type[row["archetype"]["primary_type"]].append(row)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(row: dict[str, Any], reason: str) -> None:
        if row["checksum"] in seen or len(selected) >= count:
            return
        selected.append({**row, "selection_reason": reason})
        seen.add(row["checksum"])

    # Every observed type gets one boundary case and one clean exemplar.
    for primary in sorted(by_type):
        rows = by_type[primary]
        uncertain = sorted(
            rows,
            key=lambda row: (-row["archetype"]["uncertainty_score"], row["checksum"]),
        )
        confident = sorted(
            rows,
            key=lambda row: (row["archetype"]["uncertainty_score"], row["checksum"]),
        )
        add(uncertain[0], f"boundary:{primary}")
        add(confident[0], f"exemplar:{primary}")

    # Fill the remaining budget with globally uncertain cases, capped so one
    # common type cannot consume the entire human budget.
    cap = max(3, count // max(1, len(by_type)) + 2)
    selected_counts = Counter(row["archetype"]["primary_type"] for row in selected)
    for row in sorted(
        classified,
        key=lambda item: (-item["archetype"]["uncertainty_score"], item["checksum"]),
    ):
        primary = row["archetype"]["primary_type"]
        if selected_counts[primary] >= cap:
            continue
        before = len(selected)
        add(row, "global_boundary")
        if len(selected) > before:
            selected_counts[primary] += 1
        if len(selected) >= count:
            break

    return selected


def build_archetype_review_package(
    *,
    samples_path: Path,
    calibration: dict[str, Any],
    feature_qa_path: Path,
    out_dir: Path,
    review_count: int = 60,
) -> dict[str, Any]:
    if review_count <= 0:
        raise ValueError("review_count must be positive")
    out_dir = out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata = _load_feature_metadata(feature_qa_path)
    results: list[dict[str, Any]] = []
    with samples_path.open("r", encoding="utf-8") as source:
        for line in source:
            sample = json.loads(line)
            checksum = sample["checksum"]
            output = analyze_components(
                checksum=checksum,
                components=sample["components"],
                calibration=calibration,
            )
            axes = {
                axis: output["axes"][axis].get("score")
                if output["axes"][axis].get("status") == "EMITTED"
                else None
                for axis in C.AXIS_ORDER
            }
            results.append(
                {
                    "checksum": checksum,
                    "status": output["status"],
                    "axes": axes,
                    "archetype": output["archetype"],
                    "metadata": metadata.get(checksum, {}),
                }
            )

    results_path = out_dir / "archetype_results.jsonl"
    with results_path.open("w", encoding="utf-8") as fh:
        for row in results:
            fh.write(C.strict_json_dumps(row) + "\n")

    primary_counts = Counter(_count_key(row["archetype"]["primary_type"]) for row in results)
    confidence_counts = Counter(_count_key(row["archetype"]["confidence"]) for row in results)
    tier_counts = Counter(_count_key(row["archetype"]["demand_tier"]) for row in results)
    status_counts = Counter(_count_key(row["archetype"]["status"]) for row in results)
    classified_count = status_counts.get("CLASSIFIED", 0)
    dominant_axis_counts = Counter(
        axis for row in results for axis in row["archetype"].get("dominant_axes", [])
    )
    report = {
        "schema_version": "map_archetype_qa_v0.3.0",
        "archetype_schema_version": ARCHETYPE_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "map_demand_version": C.MAP_DEMAND_VERSION,
        "calibration_id": calibration.get("calibration_id"),
        "sample_count": len(results),
        "classified_count": classified_count,
        "status_counts": dict(sorted(status_counts.items())),
        "primary_type_counts": dict(sorted(primary_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "demand_tier_counts": dict(sorted(tier_counts.items())),
        "dominant_axis_counts": dict(sorted(dominant_axis_counts.items())),
        "human_validation_required": True,
        "policy_is_ground_truth": False,
    }
    (out_dir / "qa_report.json").write_text(
        C.strict_json_dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    selected = _select_review_items(results, review_count)
    tasks: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for index, row in enumerate(selected, start=1):
        task_id = f"map-arch-atomic-v03-{index:03d}"
        meta = row["metadata"]
        beatmap_id = read_beatmap_id(meta.get("path_abs"))
        tasks.append(
            {
                "task_id": task_id,
                "checksum": row["checksum"],
                "sample_id": meta.get("sample_id"),
                "path": meta.get("path"),
                "path_abs": meta.get("path_abs"),
                "duration_ms": meta.get("duration_ms"),
                "bpm_max": meta.get("bpm_max"),
                "ar": meta.get("ar"),
                "od": meta.get("od"),
                "cs": meta.get("cs"),
                "object_count": meta.get("object_count"),
                "beatmap_id": beatmap_id,
                "axis_schema_version": AXIS_SCHEMA_VERSION,
                "allowed_primary_axes": list(C.AXIS_ORDER),
                "allowed_special_answers": ["BALANCED", "CANNOT_JUDGE"],
            }
        )
        audit.append(
            {
                "task_id": task_id,
                "checksum": row["checksum"],
                "selection_reason": row["selection_reason"],
                "axes": row["axes"],
                "archetype": row["archetype"],
            }
        )

    tasks_path = out_dir / "human_review_tasks.json"
    audit_path = out_dir / "human_review_private_audit.json"
    tasks_path.write_text(C.strict_json_dumps({"tasks": tasks}, indent=2) + "\n", encoding="utf-8")
    audit_path.write_text(C.strict_json_dumps({"tasks": audit}, indent=2) + "\n", encoding="utf-8")
    (out_dir / "human_responses.jsonl").write_text("", encoding="utf-8")
    instructions = """# Atomic Map Archetype V0.3 human review

The algorithm prediction and axis scores are intentionally hidden from the reviewer.
Do not open `human_review_private_audit.json` before completing review.

Start the local Chinese review page:

`python tools/skill-profiler-map-demand-v01.py archetype-review-ui`

The page shows neutral beatmap metadata and its local path. Play the map yourself,
then rate all eight human skill-demand axes from 0 (none) to 10 (extreme). Every slider must be
touched before saving so untouched defaults cannot become labels. Use cannot-judge
when the map cannot be assessed. Progress is saved automatically to
`human_responses.jsonl`; manual JSON editing is not required.

For exploratory comparison, add `--show-algorithm`. That mode reveals the
algorithm scores and type, and every saved response is explicitly tagged
`ASSISTED_ALGORITHM_VISIBLE`; it is not counted as blind evidence.

After annotation (partial progress is accepted), run:
`python tools/skill-profiler-map-demand-v01.py archetype-review-eval --review-dir training/datasets/map_archetype_atomic_v03`

The resulting agreement report is descriptive. It does not silently promote the
heuristic policy to ground truth.
"""
    instructions_path = out_dir / "REVIEW_INSTRUCTIONS.md"
    instructions_path.write_text(instructions, encoding="utf-8")

    manifest = {
        "schema_version": "map_archetype_review_manifest_v0.3.0",
        "axis_schema_version": AXIS_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "sample_count": len(results),
        "review_task_count": len(tasks),
        "source_artifacts": {
            str(samples_path): _sha256(samples_path),
            str(feature_qa_path): _sha256(feature_qa_path),
        },
        "artifacts": {
            "archetype_results.jsonl": _sha256(results_path),
            "qa_report.json": _sha256(out_dir / "qa_report.json"),
            "human_review_tasks.json": _sha256(tasks_path),
            "human_review_private_audit.json": _sha256(audit_path),
            "REVIEW_INSTRUCTIONS.md": _sha256(instructions_path),
        },
    }
    (out_dir / "manifest.json").write_text(
        C.strict_json_dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return report


def evaluate_archetype_review(
    *,
    tasks_path: Path,
    audit_path: Path,
    responses_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    """Validate human JSONL and compare it with the hidden heuristic output."""
    tasks = _load_task_list(tasks_path)
    audit = _load_task_list(audit_path)
    task_ids = {task["task_id"] for task in tasks}
    task_by_id = {task["task_id"]: task for task in tasks}
    audit_by_id = {task["task_id"]: task for task in audit}
    if set(audit_by_id) != task_ids:
        raise ValueError("public task ids and private audit task ids differ")

    responses: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    with responses_path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid response JSON at line {line_number}: {exc}") from exc
            if not isinstance(response, dict):
                raise ValueError(f"response line {line_number} must be an object")
            try:
                validate_human_response(response, task_ids)
            except ValueError as exc:
                raise ValueError(f"invalid response at line {line_number}: {exc}") from exc
            pair = (response["task_id"], response["reviewer_id"].strip())
            if pair in seen_pairs:
                raise ValueError(f"duplicate task/reviewer response at line {line_number}: {pair}")
            seen_pairs.add(pair)
            responses.append(response)

    comparisons: list[dict[str, Any]] = []
    responded_task_ids: set[str] = set()
    blind_responded_task_ids: set[str] = set()
    reviewers: set[str] = set()
    review_mode_counts: Counter[str] = Counter()
    axis_schema_counts: Counter[str] = Counter()
    legacy_incomparable_count = 0
    exact_count = 0
    primary_count = 0
    judgeable_count = 0
    jaccard_sum = 0.0
    axis_absolute_error_sum = 0.0
    axis_absolute_error_count = 0
    per_axis_error_sum = {axis: 0.0 for axis in ARCHETYPE_AXIS_ORDER}
    per_axis_error_count = {axis: 0 for axis in ARCHETYPE_AXIS_ORDER}
    for response in responses:
        task_id = response["task_id"]
        reviewer_id = response["reviewer_id"].strip()
        review_mode = response.get("review_mode", "BLIND_LEGACY")
        review_mode_counts[review_mode] += 1
        response_schema = response.get("axis_schema_version")
        if response_schema is None:
            ratings = response.get("axis_ratings")
            task_axes = task_by_id[task_id].get("allowed_primary_axes")
            if isinstance(ratings, dict) and set(ratings) == set(LEGACY_AXIS_ORDER):
                response_schema = LEGACY_AXIS_SCHEMA_VERSION
            elif isinstance(ratings, dict) and set(ratings) == set(PREVIOUS_ATOMIC_AXIS_ORDER):
                response_schema = PREVIOUS_ATOMIC_AXIS_SCHEMA_VERSION
            elif isinstance(task_axes, list) and set(task_axes) == set(LEGACY_AXIS_ORDER):
                response_schema = LEGACY_AXIS_SCHEMA_VERSION
            elif isinstance(task_axes, list) and set(task_axes) == set(PREVIOUS_ATOMIC_AXIS_ORDER):
                response_schema = PREVIOUS_ATOMIC_AXIS_SCHEMA_VERSION
            else:
                response_schema = AXIS_SCHEMA_VERSION
        axis_schema_counts[response_schema] += 1
        responded_task_ids.add(task_id)
        if review_mode in {"BLIND", "BLIND_LEGACY"}:
            blind_responded_task_ids.add(task_id)
        reviewers.add(reviewer_id)
        prediction = audit_by_id[task_id]["archetype"]
        predicted_axes = list(prediction.get("dominant_axes", []))
        if response_schema in {
            LEGACY_AXIS_SCHEMA_VERSION,
            PREVIOUS_ATOMIC_AXIS_SCHEMA_VERSION,
        }:
            legacy_incomparable_count += 1
            comparisons.append(
                {
                    "task_id": task_id,
                    "reviewer_id": reviewer_id,
                    "review_mode": review_mode,
                    "axis_schema_version": response_schema,
                    "human": response,
                    "prediction": prediction,
                    "included_in_agreement": False,
                    "exclusion_reason": "PREVIOUS_AXIS_SCHEMA_INCOMPARABLE",
                }
            )
            continue
        cannot_judge = response.get("cannot_judge") is True
        if cannot_judge:
            comparisons.append(
                {
                    "task_id": task_id,
                    "reviewer_id": reviewer_id,
                    "review_mode": review_mode,
                    "human": "CANNOT_JUDGE",
                    "prediction": prediction,
                    "included_in_agreement": False,
                }
            )
            continue

        judgeable_count += 1
        if response.get("axis_ratings") is not None:
            ratings = response["axis_ratings"]
            human_scores = {axis: ratings[axis] / 10.0 for axis in ARCHETYPE_AXIS_ORDER}
            human_archetype = classify_axes(
                {
                    axis: {"status": "EMITTED", "score": human_scores[axis]}
                    for axis in ARCHETYPE_AXIS_ORDER
                }
            )
            human_axes = list(human_archetype.get("dominant_axes", []))
            predicted_set = set(predicted_axes)
            human_set = set(human_axes)
            union = predicted_set | human_set
            exact = human_archetype.get("primary_type") == prediction.get("primary_type")
            if human_archetype.get("primary_type") == "BALANCED":
                primary_match = prediction.get("primary_type") == "BALANCED"
            else:
                primary_match = bool(predicted_axes and human_axes) and predicted_axes[0] == human_axes[0]
            jaccard = len(predicted_set & human_set) / len(union) if union else 1.0
            errors: dict[str, float] = {}
            predicted_scores = prediction.get("axis_scores", {})
            for axis in ARCHETYPE_AXIS_ORDER:
                predicted_score = predicted_scores.get(axis)
                if isinstance(predicted_score, (int, float)):
                    error = abs(float(predicted_score) - human_scores[axis])
                    errors[axis] = error
                    axis_absolute_error_sum += error
                    axis_absolute_error_count += 1
                    per_axis_error_sum[axis] += error
                    per_axis_error_count[axis] += 1
            human_label = {
                "axis_ratings": ratings,
                "normalized_axis_scores": human_scores,
                "derived_archetype": human_archetype,
            }
        elif response.get("balanced") is True:
            human_axes: list[str] = []
            exact = prediction.get("primary_type") == "BALANCED"
            primary_match = exact
            jaccard = 1.0 if exact else 0.0
            human_label: Any = "BALANCED"
        else:
            human_axes = [response["primary_axis"], *response.get("secondary_axes", [])]
            predicted_set = set(predicted_axes)
            human_set = set(human_axes)
            union = predicted_set | human_set
            exact = predicted_set == human_set and prediction.get("primary_type") != "BALANCED"
            primary_match = bool(predicted_axes) and predicted_axes[0] == response["primary_axis"]
            jaccard = len(predicted_set & human_set) / len(union) if union else 1.0
            human_label = {
                "primary_axis": response["primary_axis"],
                "secondary_axes": response.get("secondary_axes", []),
            }
        exact_count += int(exact)
        primary_count += int(primary_match)
        jaccard_sum += jaccard
        comparisons.append(
            {
                "task_id": task_id,
                "reviewer_id": reviewer_id,
                "review_mode": review_mode,
                "human": human_label,
                "prediction": prediction,
                "included_in_agreement": True,
                "exact_axis_set_match": exact,
                "primary_match": primary_match,
                "axis_jaccard": jaccard,
                **({"axis_absolute_errors": errors} if response.get("axis_ratings") is not None else {}),
            }
        )

    coverage = len(responded_task_ids) / len(task_ids) if task_ids else 0.0
    blind_coverage = len(blind_responded_task_ids) / len(task_ids) if task_ids else 0.0
    assisted_count = review_mode_counts.get("ASSISTED_ALGORITHM_VISIBLE", 0)
    if not responses:
        validation_status = "HUMAN_INPUT_REQUIRED"
    elif legacy_incomparable_count == len(responses):
        validation_status = "LEGACY_RESPONSES_PRESERVED_INCOMPARABLE"
    elif coverage < 1.0:
        validation_status = (
            "ASSISTED_HUMAN_REVIEW_IN_PROGRESS"
            if assisted_count
            else "INCOMPLETE_HUMAN_REVIEW"
        )
    elif blind_coverage < 1.0:
        validation_status = "HUMAN_REVIEW_COMPLETE_WITH_ASSISTED_RESPONSES"
    else:
        validation_status = "HUMAN_REVIEW_COMPLETE_DESCRIPTIVE_ONLY"
    report = {
        "schema_version": "map_archetype_human_eval_v0.3.0",
        "axis_schema_version": AXIS_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "validation_status": validation_status,
        "policy_validated": False,
        "task_count": len(task_ids),
        "responded_task_count": len(responded_task_ids),
        "task_coverage": coverage,
        "blind_task_coverage": blind_coverage,
        "review_mode_counts": dict(sorted(review_mode_counts.items())),
        "axis_schema_counts": dict(sorted(axis_schema_counts.items())),
        "legacy_incomparable_response_count": legacy_incomparable_count,
        "reviewer_count": len(reviewers),
        "response_count": len(responses),
        "atomic_response_count": len(responses) - legacy_incomparable_count,
        "judgeable_response_count": judgeable_count,
        "cannot_judge_count": len(responses) - legacy_incomparable_count - judgeable_count,
        "agreement": {
            "exact_axis_set_rate": exact_count / judgeable_count if judgeable_count else None,
            "primary_rate": primary_count / judgeable_count if judgeable_count else None,
            "mean_axis_jaccard": jaccard_sum / judgeable_count if judgeable_count else None,
            "mean_axis_absolute_error": (
                axis_absolute_error_sum / axis_absolute_error_count
                if axis_absolute_error_count
                else None
            ),
            "per_axis_mean_absolute_error": {
                axis: (
                    per_axis_error_sum[axis] / per_axis_error_count[axis]
                    if per_axis_error_count[axis]
                    else None
                )
                for axis in ARCHETYPE_AXIS_ORDER
            },
        },
        "comparisons": comparisons,
        "notes": [
            "Agreement is descriptive and does not make the heuristic policy ground truth.",
            "Threshold changes require an explicit reviewed policy decision and version bump.",
            "Broad v0.3 and atomic v0.4 responses are preserved but never converted into atomic v0.5 labels.",
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(C.strict_json_dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
