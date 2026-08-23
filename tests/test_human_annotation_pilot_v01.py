from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from osu_skill_profiler.active_learning.human_pilot_v01 import (
    AssetResolver,
    DEFAULT_ANNOTATOR_ID,
    DEFAULT_SESSION_ID,
    PILOT_ID,
    ResponseStore,
    read_jsonl,
    select_pilot_tasks,
    validate_blind_payloads,
)
from osu_skill_profiler.signals.slider import approach_rate_preempt_ms


ROOT = Path(__file__).resolve().parents[1]
DRY = ROOT / "training/datasets/active_learning_v01/dry_run"
PILOT = ROOT / "training/datasets/active_learning_v01/human_pilot_v01"


def _prepared():
    tasks = read_jsonl(PILOT / "pilot_tasks.jsonl")
    blind = read_jsonl(PILOT / "blind_pilot.jsonl")
    manifest = json.loads((PILOT / "pilot_manifest.json").read_text(encoding="utf-8"))
    return tasks, blind, manifest


@unittest.skipUnless(
    (PILOT / "pilot_tasks.jsonl").exists(),
    "requires local human-pilot dataset",
)
class HumanAnnotationPilotV01Tests(unittest.TestCase):
    def test_prepared_pilot_identity_composition_controls_and_blindness(self):
        tasks, blind, manifest = _prepared()
        self.assertEqual(manifest["pilot_id"], PILOT_ID)
        self.assertEqual(len(tasks), 40)
        self.assertEqual(len(blind), 40)
        self.assertEqual([row["task_id"] for row in tasks], manifest["task_order"])
        self.assertEqual([row["task_id"] for row in blind], manifest["task_order"])
        self.assertEqual(manifest["composition"]["by_scope"], {"MAP_PAIR": 10, "SEGMENT_PAIR": 30})
        self.assertEqual(manifest["composition"]["explicit_control_count"], 10)
        self.assertEqual(manifest["composition"]["explicit_control_ratio"], 0.25)
        validate_blind_payloads(blind)
        serialized = json.dumps(blind, sort_keys=True)
        for forbidden in (
            "control_type", "selection_reason", "weak_evidence_snapshot",
            "challenge_categories", "sampling_groups", "acquisition_score",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_repeat_and_inversion_sources_resolve_and_are_spaced(self):
        tasks, _, manifest = _prepared()
        by_id = {row["task_id"]: row for row in tasks}
        indices = {row["task_id"]: index for index, row in enumerate(tasks)}
        paired = [row for row in tasks if row["control_type"] in ("EXACT_REPEAT", "AB_INVERSION")]
        self.assertEqual(len(paired), 4)
        for control in paired:
            source = by_id[control["source_task_id"]]
            self.assertGreaterEqual(indices[control["task_id"]] - indices[source["task_id"]], 8)
            self.assertEqual(control["entity_a"]["entity"], source["entity_a"]["entity"])
            self.assertEqual(control["entity_b"]["entity"], source["entity_b"]["entity"])
            if control["control_type"] == "EXACT_REPEAT":
                self.assertEqual(control["presentation_order"], source["presentation_order"])
            else:
                self.assertNotEqual(control["presentation_order"], source["presentation_order"])
        self.assertGreaterEqual(manifest["composition"]["repeat_inversion_minimum_spacing"], 8)

    def test_selection_replays_deterministically_from_existing_batch(self):
        source_tasks = read_jsonl(DRY / "batch.jsonl")
        source_blind = read_jsonl(DRY / "blind_batch.jsonl")
        inventory = json.loads((PILOT / "asset_inventory.json").read_text(encoding="utf-8"))
        unavailable = {row["task_id"] for row in inventory["source_batch_unavailable_tasks"]}
        eligible = {row["task_id"] for row in source_tasks} - unavailable
        first = select_pilot_tasks(source_tasks, source_blind, eligible)
        second = select_pilot_tasks(source_tasks, source_blind, eligible)
        expected_tasks, expected_blind, _ = _prepared()
        self.assertEqual(first, second)
        self.assertEqual(first[0], expected_tasks)
        self.assertEqual(first[1], expected_blind)

    def test_selected_assets_resolve_and_source_unavailable_is_explicit(self):
        inventory = json.loads((PILOT / "asset_inventory.json").read_text(encoding="utf-8"))
        self.assertEqual(len(inventory["selected_tasks"]), 40)
        self.assertTrue(all(row["available"] for row in inventory["selected_tasks"]))
        self.assertTrue(all(
            entity["audio_available"] and entity["segment_resolved"]
            for row in inventory["selected_tasks"]
            for entity in row["entities"]
        ))
        self.assertEqual(len(inventory["source_batch_unavailable_tasks"]), 4)
        self.assertTrue(all("AUDIO_UNAVAILABLE" in reason for row in inventory["source_batch_unavailable_tasks"] for reason in row["reasons"]))

    def test_response_store_resume_and_duplicate_fail_closed(self):
        tasks, _, _ = _prepared()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "responses.jsonl"
            store = ResponseStore(
                path=path,
                pilot_id=PILOT_ID,
                tasks=tasks,
                annotator_id=DEFAULT_ANNOTATOR_ID,
                session_id=DEFAULT_SESSION_ID,
            )
            first = tasks[0]
            row = store.append(
                task_id=first["task_id"],
                answer="CANNOT_JUDGE",
                response_time_ms=1234,
                confidence_band="LOW",
                note="context insufficient",
            )
            self.assertEqual(row["answer"], "CANNOT_JUDGE")
            self.assertTrue(row["provenance"]["explicit_human_submission"])
            self.assertEqual(store.next_index, 1)
            resumed = ResponseStore(
                path=path,
                pilot_id=PILOT_ID,
                tasks=tasks,
                annotator_id=DEFAULT_ANNOTATOR_ID,
                session_id=DEFAULT_SESSION_ID,
            )
            self.assertEqual(resumed.next_index, 1)
            with self.assertRaisesRegex(ValueError, "immutable pilot task order"):
                resumed.append(
                    task_id=first["task_id"],
                    answer="APPROX_EQUAL",
                    response_time_ms=1,
                )
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            json.loads(lines[0])

    def test_incomplete_tail_and_identity_mismatch_fail_closed(self):
        tasks, _, _ = _prepared()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "responses.jsonl"
            path.write_text('{"partial":', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                ResponseStore(
                    path=path,
                    pilot_id=PILOT_ID,
                    tasks=tasks,
                    annotator_id=DEFAULT_ANNOTATOR_ID,
                    session_id=DEFAULT_SESSION_ID,
                )

    def test_forbidden_blind_key_is_rejected_recursively(self):
        with self.assertRaisesRegex(ValueError, "weak_evidence_snapshot"):
            validate_blind_payloads([{"task_id": "task-x", "nested": {"weak_evidence_snapshot": {}}}])

    def test_visualization_exposes_real_slider_motion_path_and_cs(self):
        tasks, blind, _ = _prepared()
        feature_rows = read_jsonl(ROOT / "training/datasets/feature_qa_v02/feature_qa_5k.jsonl")
        resolver = AssetResolver(feature_rows)
        found_slider = False
        for task, public in zip(tasks, blind, strict=True):
            presented = (
                (task["entity_a"], task["entity_b"])
                if task["presentation_order"] == "AB"
                else (task["entity_b"], task["entity_a"])
            )
            for internal, blind_entity in zip(presented, (public["entity_a"], public["entity_b"]), strict=True):
                bundle = resolver.visualization_bundle(
                    display_id=blind_entity["display_id"],
                    entity=internal,
                    blind_entity=blind_entity,
                )
                self.assertIn("beatmap_id", bundle)
                if bundle["beatmap_id"] is not None:
                    self.assertGreater(bundle["beatmap_id"], 0)
                self.assertIn("circle_size", bundle)
                self.assertGreater(bundle["circle_radius_px"], 0)
                self.assertIn("approach_rate", bundle)
                self.assertGreater(bundle["approach_preempt_ms"], 0)
                self.assertEqual(
                    bundle["approach_preempt_ms"],
                    approach_rate_preempt_ms(bundle["approach_rate"]),
                )
                for obj in bundle["objects"]:
                    if obj["type"] == "slider" and obj["end_ms"] > obj["start_ms"]:
                        self.assertGreaterEqual(len(obj["slider_path"]), 2)
                        self.assertGreaterEqual(obj["slider_spans"], 1)
                        found_slider = True
                        break
                if found_slider:
                    break
            if found_slider:
                break
        self.assertTrue(found_slider)

    def test_annotation_ui_normal_path_is_chinese(self):
        html = (ROOT / "tools/annotation_ui_v01.html").read_text(encoding="utf-8")
        runner = (ROOT / "tools/annotation_runner_v01.py").read_text(encoding="utf-8")
        for expected in (
            "osu! 谱面对比小测试", "每批 5 题", "整张图", "这小段",
            "个物件", "你有多确定（可选）", "样本 ", "看不出来",
            "“看不出来”也是有效回答。",
            "提交失败，请检查本地服务后重试。",
        ):
            self.assertIn(expected, html)
        for expected in (
            "哪一侧更需要快速或大幅度的光标移动？",
            "哪一侧的击打时间点更密集？",
            "哪一侧需要在滑条上持续跟随更长的移动距离？",
        ):
            self.assertIn(expected, runner)
        self.assertNotIn("ground truth", html)
        self.assertNotIn("PRE-ROLL", html)
        self.assertNotIn("POST-ROLL", html)
        self.assertNotIn("响应产物", html)
        self.assertNotIn("智能体校验", html)

    def test_annotation_ui_uses_actual_ar_and_despawns_hit_circles_at_hit_time(self):
        html = (ROOT / "tools/annotation_ui_v01.html").read_text(encoding="utf-8")
        self.assertIn("`AR ${visual.approach_rate}`", html)
        self.assertIn("`BID ${visual.beatmap_id}`", html)
        self.assertIn("BID 未提供", html)
        self.assertIn("Number(data.approach_preempt_ms)", html)
        self.assertIn("now >= o.start_ms-preempt && now < o.start_ms", html)
        self.assertIn("o.type==='slider' && now >= o.start_ms && now <= o.end_ms", html)
        self.assertNotIn("dt/1400", html)

    def test_repeat_slider_travel_is_explicitly_ping_ponged(self):
        html = (ROOT / "tools/annotation_ui_v01.html").read_text(encoding="utf-8")
        self.assertIn("function sliderTravelProgress", html)
        self.assertIn("spans % 2 === 0 ? 0 : 1", html)
        self.assertIn(
            "sliderTravelProgress(now,o.start_ms,o.end_ms,o.slider_spans)",
            html,
        )

    def test_annotation_html_is_never_cached(self):
        runner = (ROOT / "tools/annotation_runner_v01.py").read_text(encoding="utf-8")
        self.assertIn('cache_control="no-store, no-cache, must-revalidate"', runner)


if __name__ == "__main__":
    unittest.main()
