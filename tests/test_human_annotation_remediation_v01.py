from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from osu_skill_profiler.active_learning.contracts_v01 import ControlType, PresentationOrder
from osu_skill_profiler.active_learning.human_pilot_v01 import AssetResolver, ResponseStore, read_jsonl
from osu_skill_profiler.active_learning.human_pilot_v02 import (
    BASE_PROPOSITION_QUOTAS,
    PILOT_V02_ANNOTATOR_ID,
    PILOT_V02_ID,
    PILOT_V02_SESSION_ID,
    blind_v02,
    prepare_pilot_v02,
    select_v02_tasks,
    task_from_dict,
)
from osu_skill_profiler.active_learning.human_presentation_v02 import (
    HUMAN_PROPOSITIONS,
    EmptyDomainPolicy,
    HumanJudgeability,
    HumanPresentationEligibility,
    PresentationReason,
)
from osu_skill_profiler.active_learning.human_training_guard_v01 import assert_training_eligible


ROOT = Path(__file__).resolve().parents[1]
DRY = ROOT / "training/datasets/active_learning_v01/dry_run"
V01 = ROOT / "training/datasets/active_learning_v01/human_pilot_v01"
V02 = ROOT / "training/datasets/active_learning_v01/human_pilot_v02"
FEATURE = ROOT / "training/datasets/feature_qa_v02/feature_qa_5k.jsonl"
DISPOSITION = ROOT / "docs/archive/HUMAN_ANNOTATION_PILOT_SESSION_001_DISPOSITION.json"
SESSION001 = V01 / "responses/annotator_001/pilot_session_001.jsonl"


def _osu(*, objects: list[str], timing: str = "0,500,4,2,1,50,1,0", cs: float = 4.0) -> str:
    return "\n".join((
        "osu file format v14",
        "[General]", "AudioFilename: audio.mp3", "Mode: 0",
        "[Metadata]", "Title: test", "Artist: test", "Creator: test", "Version: test", "BeatmapID: 1", "BeatmapSetID: 1",
        "[Difficulty]", f"CircleSize:{cs}", "HPDrainRate:5", "OverallDifficulty:5", "ApproachRate:5", "SliderMultiplier:1.4", "SliderTickRate:1",
        "[TimingPoints]", timing,
        "[HitObjects]", *objects, "",
    ))


class _Resolved:
    def __init__(self, osu_path: Path, audio_path: Path | None):
        self.osu_path = osu_path
        self.audio_path = audio_path


class _Resolver:
    def __init__(self, resolved: _Resolved):
        self.resolved = resolved

    def resolve_map(self, checksum: str):
        return self.resolved


def _entity(scope: str = "MAP", *, start: float = 0.0, end: float = 5000.0) -> dict:
    ref = {"scope": scope, "map_checksum": "sha256:" + "1" * 64}
    if scope == "SEGMENT":
        ref.update({"segment_index": 0, "segment_start_ms": start, "segment_end_ms": end})
    return {
        "anonymous_display_id": "entity-test000000",
        "entity": ref,
        "sampling_groups": {"set_group_key": "set-test", "mapper_group_key": "mapper-test"},
        "neutral_metadata": {},
    }


class PresentationEligibilityTests(unittest.TestCase):
    def _gate(self, text: str, *, audio: bool = True, duration_ms: float | None = 60_000.0):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        osu = root / "test.osu"
        osu.write_text(text, encoding="utf-8")
        audio_path = root / "audio.mp3" if audio else None
        if audio_path is not None:
            audio_path.write_bytes(b"not decoded because duration probe is injected")
        gate = HumanPresentationEligibility(_Resolver(_Resolved(osu, audio_path)), duration_probe=lambda _: duration_ms)
        return temp, gate

    def test_no_slider_empty_domain_and_zero_are_not_conflated(self):
        temp, gate = self._gate(_osu(objects=["256,192,1000,1,0,0:0:0:0:", "300,192,2000,1,0,0:0:0:0:"]))
        try:
            result = gate.evaluate_entity(_entity("SEGMENT"), "ws01.provisional.slider_tracking_travel_high")
            self.assertFalse(result["eligible"])
            self.assertIn(PresentationReason.EMPTY_PROPOSITION_DOMAIN.value, result["reasons"])
            self.assertEqual(
                HUMAN_PROPOSITIONS["ws01.provisional.slider_tracking_travel_high"].empty_domain_policy,
                EmptyDomainPolicy.PAIR_INELIGIBLE,
            )
        finally:
            temp.cleanup()

    def test_one_empty_side_and_both_empty_fail_pair(self):
        empty_temp, empty_gate = self._gate(_osu(objects=["256,192,0,1,0,0:0:0:0:", "256,192,5000,1,0,0:0:0:0:"]))
        slider_temp, slider_gate = self._gate(_osu(objects=["256,192,0,2,0,B|356:192,1,100", "256,192,5000,1,0,0:0:0:0:"]))
        try:
            empty = empty_gate.evaluate_entity(_entity("SEGMENT"), "ws01.provisional.slider_tracking_travel_high")
            slider = slider_gate.evaluate_entity(_entity("SEGMENT"), "ws01.provisional.slider_tracking_travel_high")
            self.assertFalse(empty["eligible"])
            self.assertTrue(slider["eligible"])
            self.assertFalse(empty["eligible"] and slider["eligible"])
            self.assertFalse(empty["eligible"] and empty["eligible"])
        finally:
            empty_temp.cleanup()
            slider_temp.cleanup()

    def test_aspire_like_timeline_is_rejected_by_properties(self):
        text = _osu(
            timing="0,1e-298,4,2,1,50,1,0",
            objects=["256,192,1000,2,0,L|356:192,1,1e300"],
        )
        temp, gate = self._gate(text, duration_ms=120_000.0)
        try:
            entity = _entity("MAP")
            entity["challenge_categories"] = ["pathological_challenge"]
            result = gate.evaluate_entity(entity, "ws01.provisional.dense_timing_pressure_high")
            self.assertFalse(result["eligible"])
            self.assertTrue(set(result["reasons"]) & {
                PresentationReason.BPM_PRESENTATION_UNSAFE.value,
                PresentationReason.TIMELINE_TOO_LONG.value,
                PresentationReason.SLIDER_TRAVERSAL_UNREPRESENTABLE.value,
            })
        finally:
            temp.cleanup()

    def test_playable_pathological_label_is_not_automatically_rejected(self):
        temp, gate = self._gate(_osu(objects=["256,192,1000,2,0,B|356:192,1,100"]))
        try:
            entity = _entity("MAP")
            entity["challenge_categories"] = ["pathological_challenge"]
            result = gate.evaluate_entity(entity, "ws01.provisional.dense_timing_pressure_high")
            self.assertTrue(result["eligible"], result)
        finally:
            temp.cleanup()

    def test_missing_audio_and_audio_window_uncovered(self):
        text = _osu(objects=["256,192,1000,1,0,0:0:0:0:", "256,192,5000,1,0,0:0:0:0:"])
        temp, gate = self._gate(text, audio=False)
        short_temp, short_gate = self._gate(text, duration_ms=1000.0)
        try:
            missing = gate.evaluate_entity(_entity("MAP"), "ws01.provisional.dense_timing_pressure_high")
            uncovered = short_gate.evaluate_entity(_entity("MAP"), "ws01.provisional.dense_timing_pressure_high")
            self.assertIn(PresentationReason.AUDIO_UNAVAILABLE.value, missing["reasons"])
            self.assertIn(PresentationReason.AUDIO_WINDOW_UNCOVERED.value, uncovered["reasons"])
        finally:
            temp.cleanup()
            short_temp.cleanup()

    def test_renderer_unavailable_and_nonjudgeable_proposition(self):
        temp, gate = self._gate(_osu(objects=["700,192,1000,1,0,0:0:0:0:"]))
        try:
            renderer = gate.evaluate_entity(_entity("MAP"), "ws01.provisional.dense_timing_pressure_high")
            excluded = gate.evaluate_entity(_entity("MAP"), "ws01.provisional.slider_control_load_high")
            self.assertIn(PresentationReason.OBJECT_OUTSIDE_RENDERER.value, renderer["reasons"])
            self.assertEqual(
                HUMAN_PROPOSITIONS["ws01.provisional.slider_control_load_high"].judgeability,
                HumanJudgeability.NOT_YET_HUMAN_JUDGEABLE,
            )
            self.assertIn(PresentationReason.PROPOSITION_NOT_HUMAN_JUDGEABLE.value, excluded["reasons"])
        finally:
            temp.cleanup()


@unittest.skipUnless(
    (V02 / "pilot_tasks.jsonl").exists()
    and FEATURE.exists()
    and DISPOSITION.exists()
    and SESSION001.exists(),
    "requires local human-pilot and feature datasets",
)
class PilotV02Tests(unittest.TestCase):
    def setUp(self):
        self.tasks = read_jsonl(V02 / "pilot_tasks.jsonl")
        self.blind = read_jsonl(V02 / "blind_pilot.jsonl")
        self.manifest = json.loads((V02 / "pilot_manifest.json").read_text(encoding="utf-8"))

    def test_balancer_prevents_slider_domination_and_records_shortage(self):
        self.assertEqual(self.manifest["composition"]["by_proposition"], {
            "ws01.provisional.dense_timing_pressure_high": 14,
            "ws01.provisional.movement_demand_high": 10,
            "ws01.provisional.slider_tracking_travel_high": 16,
        })
        self.assertEqual(self.manifest["composition"]["base_proposition_quotas"], BASE_PROPOSITION_QUOTAS)
        self.assertLessEqual(max(self.manifest["composition"]["by_proposition"].values()), 16)

    def test_insufficient_candidates_for_proposition_fails_closed(self):
        source = read_jsonl(DRY / "batch.jsonl")
        eligibility = {row["task_id"]: {"eligible": row["proposition"]["key"] != "ws01.provisional.movement_demand_high"} for row in source}
        with self.assertRaisesRegex(ValueError, "insufficient"):
            select_v02_tasks(source, eligibility)

    def test_controls_duplicates_spacing_and_inversion(self):
        by_id = {row["task_id"]: row for row in self.tasks}
        indices = {row["task_id"]: index for index, row in enumerate(self.tasks)}
        paired = [row for row in self.tasks if row["control_type"] in ("EXACT_REPEAT", "AB_INVERSION")]
        self.assertEqual(sum(row["control_type"] == "EXACT_REPEAT" for row in paired), 4)
        self.assertEqual(sum(row["control_type"] == "AB_INVERSION" for row in paired), 4)
        for control in paired:
            source = by_id[control["source_task_id"]]
            self.assertGreaterEqual(indices[control["task_id"]] - indices[source["task_id"]], 8)
            self.assertEqual(control["entity_a"]["entity"], source["entity_a"]["entity"])
            self.assertEqual(control["entity_b"]["entity"], source["entity_b"]["entity"])
            if control["control_type"] == "EXACT_REPEAT":
                self.assertEqual(control["presentation_order"], source["presentation_order"])
            else:
                self.assertNotEqual(control["presentation_order"], source["presentation_order"])

    def test_blind_payload_and_cannot_judge_contract(self):
        text = json.dumps(self.blind, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "weak_evidence", "acquisition_score", "selection_reason", "expected",
            "control_type", "source_task_id", "challenge_categories",
        ):
            self.assertNotIn(forbidden, text.lower())
        self.assertTrue(all(row["cannot_judge_is_valid"] for row in self.blind))
        self.assertTrue(all("CANNOT_JUDGE" in row["answer_space"] for row in self.blind))
        self.assertTrue(all(row["proposition"]["attend_to"] for row in self.blind))

    def test_selected_tasks_pass_mechanical_eligibility(self):
        report = json.loads((V02 / "eligibility_report.json").read_text(encoding="utf-8"))
        self.assertEqual(len(report["selected_task_audits"]), 40)
        self.assertTrue(all(row["eligible"] for row in report["selected_task_audits"]))
        self.assertGreater(report["ineligible_source_tasks"], 0)

    def test_deterministic_replay_and_empty_formal_response_directory(self):
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = prepare_pilot_v02(
                source_batch_path=DRY / "batch.jsonl", feature_path=FEATURE,
                session001_response_path=SESSION001, session001_disposition_path=DISPOSITION,
                output_dir=Path(first_tmp),
            )
            second = prepare_pilot_v02(
                source_batch_path=DRY / "batch.jsonl", feature_path=FEATURE,
                session001_response_path=SESSION001, session001_disposition_path=DISPOSITION,
                output_dir=Path(second_tmp),
            )
            names = sorted(path.relative_to(first_tmp) for path in Path(first_tmp).rglob("*") if path.is_file())
            self.assertEqual(names, sorted(path.relative_to(second_tmp) for path in Path(second_tmp).rglob("*") if path.is_file()))
            for name in names:
                self.assertEqual((Path(first_tmp) / name).read_bytes(), (Path(second_tmp) / name).read_bytes(), name)
            self.assertEqual(first["manifest_file"]["sha256"], second["manifest_file"]["sha256"])
        response_dir = V02 / self.manifest["formal_response_directory"]
        self.assertEqual([path for path in response_dir.rglob("*") if path.is_file()], [])
        self.assertEqual(self.manifest["formal_response_count"], 0)

    def test_response_store_accepts_cannot_judge_for_v02(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ResponseStore(
                path=Path(tmp) / "responses.jsonl",
                pilot_id=PILOT_V02_ID,
                tasks=self.tasks,
                annotator_id=PILOT_V02_ANNOTATOR_ID,
                session_id=PILOT_V02_SESSION_ID,
            )
            row = store.append(task_id=self.tasks[0]["task_id"], answer="CANNOT_JUDGE", response_time_ms=1)
            self.assertEqual(row["answer"], "CANNOT_JUDGE")

    def test_session001_training_guard_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "not training eligible"):
            assert_training_eligible(SESSION001, DISPOSITION)
        with tempfile.TemporaryDirectory() as tmp:
            disposition = json.loads(DISPOSITION.read_text(encoding="utf-8"))
            disposition["training_eligible"] = True
            fake = Path(tmp) / "eligible.json"
            fake.write_text(json.dumps(disposition), encoding="utf-8")
            self.assertTrue(assert_training_eligible(SESSION001, fake)["training_eligible"])

    def test_accidental_duplicate_rejected_but_intentional_repeat_is_present(self):
        source = task_from_dict(self.tasks[0])
        duplicate = replace(source, task_id="task-accidental-duplicate")
        from osu_skill_profiler.active_learning.human_pilot_v02 import _validate_duplicates
        with self.assertRaisesRegex(ValueError, "accidental"):
            _validate_duplicates([source, duplicate])
        repeat = next(row for row in self.tasks if row["control_type"] == "EXACT_REPEAT")
        self.assertIn(repeat["source_task_id"], {row["task_id"] for row in self.tasks})


if __name__ == "__main__":
    unittest.main()
