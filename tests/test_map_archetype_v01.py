"""Contract tests for atomic MAP_ARCHETYPE_V02 and its review package."""

from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import contract as C  # noqa: E402
from map_demand_v01.archetype_batch_v01 import (  # noqa: E402
    build_archetype_review_package,
    evaluate_archetype_review,
    read_beatmap_id,
)
from map_demand_v01.archetype_v01 import (  # noqa: E402
    AXIS_SCHEMA_VERSION,
    LEGACY_AXIS_SCHEMA_VERSION,
    classify_axes,
    validate_human_response,
)
from map_demand_v01.archetype_review_ui_v01 import ArchetypeReviewStore  # noqa: E402
from map_demand_v01.model import analyze_components  # noqa: E402


def emitted_axes(**scores: float) -> dict:
    return {
        axis: {
            "status": "EMITTED" if axis in scores else "INSUFFICIENT_EVIDENCE",
            "score": scores.get(axis),
        }
        for axis in C.AXIS_ORDER
    }


def mini_calibration(seed: int = 11) -> dict:
    rnd = random.Random(seed)
    names = {
        signal
        for axis in C.AXIS_ORDER
        for signal in C.AXIS_META[axis]["signals"]
    }
    return {
        "calibration_id": f"mini:{seed}",
        "distributions": {
            name: sorted(rnd.uniform(0.01, 100.0) for _ in range(64))
            for name in sorted(names)
        },
    }


def full_components(scale: float = 1.0) -> dict:
    return {
        "jump_aim_strain_p90": 40.0 * scale,
        "flow_aim_continuity_share": min(1.0, 0.5 * scale),
        "flow_aim_chain_length_p90": 35.0 * scale,
        "flow_aim_chain_velocity_p90": 28.0 * scale,
        "aim_control_angle_change_p90": 32.0 * scale,
        "aim_control_velocity_change_p90": 28.0 * scale,
        "spatial_precision_pressure_p90": 50.0 * scale,
        "raw_speed_strain_p90": 45.0 * scale,
        "stamina_sustained_ms": 55.0 * scale,
        "stamina_duration_share": min(1.0, 0.35 * scale),
        "stamina_density": 42.0 * scale,
        "finger_control_interval_entropy": 30.0 * scale,
        "finger_control_interval_diversity": min(1.0, 0.25 * scale),
        "finger_control_interval_ratio": 38.0 * scale,
        "timing_precision_window_pressure": 36.0 * scale,
        "reading_preempt_median_ms": 520.0,
        "reading_density": 41.0 * scale,
        "reading_visual_change": min(1.0, 0.45 * scale),
        "row_counts": {},
    }


class ArchetypePolicyTests(unittest.TestCase):
    def test_balanced_is_shape_not_low_demand(self):
        low = classify_axes(emitted_axes(**{axis: 0.20 for axis in C.AXIS_ORDER}))
        high = classify_axes(emitted_axes(**{axis: 0.90 for axis in C.AXIS_ORDER}))
        self.assertEqual(low["primary_type"], "BALANCED")
        self.assertEqual(high["primary_type"], "BALANCED")
        self.assertEqual(low["demand_tier"], "LOW")
        self.assertEqual(high["demand_tier"], "EXTREME")

    def test_single_and_named_pair_dominance(self):
        base = {axis: 0.33 for axis in C.AXIS_ORDER}
        single = classify_axes(
            emitted_axes(**{**base, "jump_aim": 0.91, "spatial_precision": 0.51})
        )
        pair = classify_axes(
            emitted_axes(**{**base, "jump_aim": 0.91, "spatial_precision": 0.86})
        )
        self.assertEqual(single["primary_type"], "JUMP_AIM_DOMINANT")
        self.assertEqual(single["dominant_axes"], ["jump_aim"])
        self.assertEqual(pair["primary_type"], "JUMP_PRECISION")
        self.assertEqual(pair["dominant_axes"], ["jump_aim", "spatial_precision"])

    def test_three_way_is_hybrid_and_deterministic(self):
        scores = {axis: 0.31 for axis in C.AXIS_ORDER}
        scores.update(jump_aim=0.90, spatial_precision=0.86, raw_speed=0.84)
        axes = emitted_axes(**scores)
        first = classify_axes(axes)
        self.assertEqual(first, classify_axes(axes))
        self.assertEqual(first["primary_type"], "HYBRID")
        self.assertEqual(
            first["dominant_axes"], ["jump_aim", "spatial_precision", "raw_speed"]
        )

    def test_insufficient_axes_fail_closed(self):
        result = classify_axes(
            emitted_axes(jump_aim=0.9, spatial_precision=0.8, raw_speed=0.7)
        )
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(result["primary_type"])

    def test_human_response_validator_is_fail_closed(self):
        task_ids = {"task-1"}
        validate_human_response(
            {
                "task_id": "task-1",
                "reviewer_id": "human-a",
                "axis_schema_version": AXIS_SCHEMA_VERSION,
                "primary_axis": "jump_aim",
                "secondary_axes": ["spatial_precision"],
            },
            task_ids,
        )
        with self.assertRaises(ValueError):
            validate_human_response(
                {
                    "task_id": "task-1",
                    "reviewer_id": "human-a",
                    "cannot_judge": True,
                    "axis_schema_version": AXIS_SCHEMA_VERSION,
                    "primary_axis": "jump_aim",
                },
                task_ids,
            )
    def test_eight_axis_ratings_are_complete_numeric_and_exclusive(self):
        task_ids = {"task-1"}
        ratings = {axis: index for index, axis in enumerate(C.AXIS_ORDER)}
        validate_human_response(
            {
                "task_id": "task-1",
                "reviewer_id": "human-a",
                "axis_schema_version": AXIS_SCHEMA_VERSION,
                "axis_ratings": ratings,
            },
            task_ids,
        )
        with self.assertRaises(ValueError):
            validate_human_response(
                {
                    "task_id": "task-1",
                    "reviewer_id": "human-a",
                    "axis_schema_version": AXIS_SCHEMA_VERSION,
                    "axis_ratings": {"jump_aim": 5},
                },
                task_ids,
            )
        with self.assertRaises(ValueError):
            validate_human_response(
                {
                    "task_id": "task-1",
                    "reviewer_id": "human-a",
                    "axis_ratings": ratings,
                    "review_mode": "SECRETLY_ASSISTED",
                },
                task_ids,
            )
        validate_human_response(
            {
                "task_id": "task-1",
                "reviewer_id": "human-a",
                "axis_schema_version": AXIS_SCHEMA_VERSION,
                "axis_ratings": {**ratings, "jump_aim": 12.5},
            },
            task_ids,
        )
        validate_human_response(
            {
                "task_id": "task-1",
                "reviewer_id": "legacy-human",
                "axis_schema_version": LEGACY_AXIS_SCHEMA_VERSION,
                "axis_ratings": {
                    "aim": 7,
                    "precision": 5,
                    "speed": 4,
                    "stamina": 3,
                    "rhythm": 6,
                    "reading": 2,
                },
            },
            task_ids,
        )
        with self.assertRaises(ValueError):
            validate_human_response(
                {
                    "task_id": "task-1",
                    "reviewer_id": "human-a",
                    "axis_ratings": ratings,
                    "balanced": True,
                },
                task_ids,
            )

    def test_archetype_accepts_star_normalized_scores_above_one(self):
        scores = {axis: 0.60 for axis in C.AXIS_ORDER}
        scores.update(jump_aim=1.35, spatial_precision=1.05, raw_speed=0.95)
        result = classify_axes(
            emitted_axes(**scores)
        )
        self.assertEqual(result["status"], "CLASSIFIED")
        self.assertEqual(result["axis_scores"]["jump_aim"], 1.35)


class ArchetypeIntegrationTests(unittest.TestCase):
    def test_beatmap_id_is_read_from_metadata_not_folder_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "999999 misleading folder.osu"
            path.write_text(
                "osu file format v14\n\n[Metadata]\nBeatmapSetID:111\nBeatmapID:2738143\n",
                encoding="utf-8",
            )
            self.assertEqual(read_beatmap_id(str(path)), 2738143)
            path.write_text(
                "osu file format v14\n\n[Metadata]\nBeatmapID:0\n", encoding="utf-8"
            )
            self.assertIsNone(read_beatmap_id(str(path)))

    def test_map_demand_output_contains_archetype(self):
        output = analyze_components(
            checksum="sha256:integration",
            components=full_components(),
            calibration=mini_calibration(),
        )
        self.assertEqual(output["status"], "OK")
        self.assertIn(output["archetype"]["status"], {"CLASSIFIED", "INSUFFICIENT_EVIDENCE"})
        self.assertEqual(
            output["archetype"]["policy_id"],
            "HEURISTIC_ATOMIC_STAR_SCALED_DOMINANCE_V04",
        )
        self.assertEqual(set(output["summaries"]), set(C.SUMMARY_ORDER))

    def test_unsupported_mod_keeps_archetype_unavailable(self):
        output = analyze_components(
            checksum="sha256:blocked",
            requested_mods=["FL"],
            components=full_components(),
            calibration=mini_calibration(),
        )
        self.assertEqual(output["status"], "UNSUPPORTED_MOD_STATE")
        self.assertEqual(output["archetype"]["status"], "UNAVAILABLE")

    def test_review_package_blinds_predictions_and_refuses_overwrite(self):
        calibration = mini_calibration()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples.jsonl"
            features = root / "features.jsonl"
            rows = []
            feature_rows = []
            for index, scale in enumerate((0.7, 1.0, 1.3), start=1):
                checksum = f"sha256:sample-{index}"
                map_path = root / f"{index}.osu"
                map_path.write_text(
                    f"osu file format v14\n\n[Metadata]\nBeatmapID:{1000 + index}\n",
                    encoding="utf-8",
                )
                rows.append({"checksum": checksum, "components": full_components(scale)})
                feature_rows.append(
                    {
                        "checksum": checksum,
                        "sample_id": f"sample-{index}",
                        "path": f"maps/{index}.osu",
                        "path_abs": str(map_path),
                        "duration_ms": 100000,
                        "bpm_max": 180,
                        "ar": 9,
                        "od": 8,
                        "cs": 4,
                        "object_count": 500,
                    }
                )
            samples.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            features.write_text(
                "".join(json.dumps(row) + "\n" for row in feature_rows), encoding="utf-8"
            )
            out_dir = root / "review"
            report = build_archetype_review_package(
                samples_path=samples,
                calibration=calibration,
                feature_qa_path=features,
                out_dir=out_dir,
                review_count=3,
            )
            self.assertEqual(report["sample_count"], 3)
            tasks = json.loads((out_dir / "human_review_tasks.json").read_text(encoding="utf-8"))["tasks"]
            audit = json.loads((out_dir / "human_review_private_audit.json").read_text(encoding="utf-8"))["tasks"]
            self.assertGreater(len(tasks), 0)
            self.assertIsInstance(tasks[0]["beatmap_id"], int)
            self.assertNotIn("axes", tasks[0])
            self.assertNotIn("archetype", tasks[0])
            self.assertIn("axes", audit[0])
            self.assertIn("archetype", audit[0])
            self.assertTrue((out_dir / "manifest.json").exists())
            empty_report = evaluate_archetype_review(
                tasks_path=out_dir / "human_review_tasks.json",
                audit_path=out_dir / "human_review_private_audit.json",
                responses_path=out_dir / "human_responses.jsonl",
                out_path=out_dir / "human_evaluation.json",
            )
            self.assertEqual(empty_report["validation_status"], "HUMAN_INPUT_REQUIRED")
            self.assertEqual(empty_report["task_coverage"], 0.0)

            legacy_response = {
                "task_id": tasks[0]["task_id"],
                "reviewer_id": "legacy-human",
                "axis_schema_version": LEGACY_AXIS_SCHEMA_VERSION,
                "axis_ratings": {
                    "aim": 7,
                    "precision": 5,
                    "speed": 4,
                    "stamina": 3,
                    "rhythm": 6,
                    "reading": 2,
                },
            }
            (out_dir / "human_responses.jsonl").write_text(
                json.dumps(legacy_response) + "\n", encoding="utf-8"
            )
            legacy_report = evaluate_archetype_review(
                tasks_path=out_dir / "human_review_tasks.json",
                audit_path=out_dir / "human_review_private_audit.json",
                responses_path=out_dir / "human_responses.jsonl",
                out_path=out_dir / "human_evaluation.json",
            )
            self.assertEqual(
                legacy_report["validation_status"],
                "LEGACY_RESPONSES_PRESERVED_INCOMPARABLE",
            )
            self.assertEqual(legacy_report["legacy_incomparable_response_count"], 1)
            self.assertEqual(legacy_report["judgeable_response_count"], 0)

            response = {
                "task_id": tasks[0]["task_id"],
                "reviewer_id": "human-a",
                "axis_schema_version": AXIS_SCHEMA_VERSION,
                "primary_axis": "jump_aim",
                "secondary_axes": [],
                "confidence": "MEDIUM",
                "notes": "blind review",
            }
            (out_dir / "human_responses.jsonl").write_text(
                json.dumps(response) + "\n", encoding="utf-8"
            )
            partial_report = evaluate_archetype_review(
                tasks_path=out_dir / "human_review_tasks.json",
                audit_path=out_dir / "human_review_private_audit.json",
                responses_path=out_dir / "human_responses.jsonl",
                out_path=out_dir / "human_evaluation.json",
            )
            self.assertEqual(partial_report["validation_status"], "INCOMPLETE_HUMAN_REVIEW")
            self.assertEqual(partial_report["responded_task_count"], 1)
            self.assertFalse(partial_report["policy_validated"])

            store = ArchetypeReviewStore(
                tasks_path=out_dir / "human_review_tasks.json",
                responses_path=out_dir / "human_responses.jsonl",
                reviewer_id="human-a",
            )
            slider_ratings = {
                "jump_aim": 9,
                "flow_aim": 6,
                "aim_control": 7,
                "spatial_precision": 8,
                "raw_speed": 4,
                "stamina": 3,
                "finger_control": 5,
                "reading": 2,
            }
            next_state = store.save(
                {
                    "task_id": tasks[0]["task_id"],
                    "axis_ratings": slider_ratings,
                    "confidence": "HIGH",
                    "notes": "played locally",
                }
            )
            self.assertEqual(next_state["completed"], 1)
            self.assertEqual(
                next_state["responses"][tasks[0]["task_id"]]["axis_ratings"],
                slider_ratings,
            )
            response_lines = [
                line
                for line in (out_dir / "human_responses.jsonl").read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual(len(response_lines), 1)
            slider_report = evaluate_archetype_review(
                tasks_path=out_dir / "human_review_tasks.json",
                audit_path=out_dir / "human_review_private_audit.json",
                responses_path=out_dir / "human_responses.jsonl",
                out_path=out_dir / "human_evaluation.json",
            )
            self.assertIsNotNone(slider_report["agreement"]["mean_axis_absolute_error"])
            self.assertEqual(
                set(slider_report["agreement"]["per_axis_mean_absolute_error"]),
                set(C.AXIS_ORDER),
            )

            assisted_store = ArchetypeReviewStore(
                tasks_path=out_dir / "human_review_tasks.json",
                audit_path=out_dir / "human_review_private_audit.json",
                responses_path=out_dir / "human_responses.jsonl",
                reviewer_id="human-b",
                show_algorithm=True,
            )
            assisted_state = assisted_store.state()
            self.assertTrue(assisted_state["algorithm_visible"])
            self.assertIn("algorithm", assisted_state["tasks"][0])
            assisted_state = assisted_store.save(
                {
                    "task_id": tasks[1]["task_id"],
                    "axis_ratings": slider_ratings,
                    "confidence": "LOW",
                    "notes": "machine result was visible",
                }
            )
            self.assertEqual(
                assisted_state["responses"][tasks[1]["task_id"]]["review_mode"],
                "ASSISTED_ALGORITHM_VISIBLE",
            )
            assisted_report = evaluate_archetype_review(
                tasks_path=out_dir / "human_review_tasks.json",
                audit_path=out_dir / "human_review_private_audit.json",
                responses_path=out_dir / "human_responses.jsonl",
                out_path=out_dir / "human_evaluation.json",
            )
            self.assertEqual(
                assisted_report["review_mode_counts"],
                {"ASSISTED_ALGORITHM_VISIBLE": 1, "BLIND": 1},
            )
            self.assertEqual(
                assisted_report["validation_status"],
                "ASSISTED_HUMAN_REVIEW_IN_PROGRESS",
            )
            with self.assertRaises(FileExistsError):
                build_archetype_review_package(
                    samples_path=samples,
                    calibration=calibration,
                    feature_qa_path=features,
                    out_dir=out_dir,
                    review_count=3,
                )


if __name__ == "__main__":
    unittest.main()
