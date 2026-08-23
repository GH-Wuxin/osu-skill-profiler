from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from osu_skill_profiler.active_learning.collection_analysis_v01 import (
    analyze_capture,
    capture_collection,
    write_snapshot,
)
from osu_skill_profiler.active_learning.contracts_v01 import canonical_json, stable_id
from osu_skill_profiler.active_learning.human_pilot_v01 import read_jsonl
from osu_skill_profiler.active_learning.human_pilot_v02 import PILOT_V02_ID


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "training/datasets/active_learning_v01/human_pilot_v02"


@unittest.skipUnless(
    (PILOT / "pilot_tasks.jsonl").exists(),
    "requires local human-pilot dataset",
)
class CollectionAnalysisV01Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.collection = Path(self.temp.name) / "collection_test"
        self.responses = self.collection / "responses"
        self.tasks = read_jsonl(PILOT / "pilot_tasks.jsonl")
        self.task_ids = [str(row["task_id"]) for row in self.tasks]
        self.registry = {
            "schema_version": "0.5.0",
            "collection_id": "collection_test",
            "pilot_id": PILOT_V02_ID,
            "tasks_per_participant": 5,
            "player_presentation_version": "player-zh-cn-0.1.0",
            "task_pool": self.task_ids,
            "allocation_seed": "0" * 32,
            "participants": [],
        }

    def tearDown(self):
        self.temp.cleanup()

    def _participant(self, number: int, task_ids: list[str]) -> dict:
        annotator = f"annotator_{number:03d}"
        session = f"collection_test_{annotator}_session_001"
        entry = {
            "annotator_id": annotator,
            "session_id": session,
            "session_token_hash": hashlib.sha256(f"token-{number}".encode()).hexdigest(),
            "task_ids": task_ids,
            "response_path": f"responses/{annotator}/session_001.jsonl",
        }
        self.registry["participants"].append(entry)
        return entry

    def _row(self, entry: dict, task_id: str, answer: str, *, elapsed: int = 1000) -> dict:
        task = next(row for row in self.tasks if row["task_id"] == task_id)
        identity = {
            "pilot_id": PILOT_V02_ID,
            "annotator_id": entry["annotator_id"],
            "session_id": entry["session_id"],
            "task_id": task_id,
        }
        return {
            "schema_version": "0.1.0",
            "response_version": "0.1.0",
            "response_id": stable_id("response-", identity),
            "task_id": task_id,
            "task_version": task["task_version"],
            "batch_id": task["batch_id"],
            "annotator_id": entry["annotator_id"],
            "session_id": entry["session_id"],
            "answer": answer,
            "presentation_order": task["presentation_order"],
            "response_time_ms": elapsed,
            "confidence_band": "MEDIUM",
            "reason_codes": [],
            "provenance": {
                "pilot_id": PILOT_V02_ID,
                "explicit_human_submission": True,
                "optional_note": None,
            },
            "pilot_id": PILOT_V02_ID,
            "response_timestamp_utc": "2026-08-14T00:00:00.000Z",
        }

    def _write(self, rows_by_entry: list[tuple[dict, list[dict]]]) -> None:
        self.collection.mkdir(parents=True, exist_ok=True)
        (self.collection / "collection.json").write_text(
            json.dumps(self.registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        for entry, rows in rows_by_entry:
            path = self.collection / entry["response_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(canonical_json(row) + "\n" for row in rows),
                encoding="utf-8",
            )

    def test_stable_capture_preserves_partial_sessions_and_overlap(self):
        first = self._participant(1, self.task_ids[:5])
        second = self._participant(2, [self.task_ids[0], *self.task_ids[5:9]])
        first_rows = [
            self._row(first, task_id, "A_SLIGHTLY_HIGHER", elapsed=1000 + index)
            for index, task_id in enumerate(first["task_ids"])
        ]
        second_rows = [self._row(second, second["task_ids"][0], "B_SLIGHTLY_HIGHER")]
        self._write([(first, first_rows), (second, second_rows)])

        capture = capture_collection(pilot_dir=PILOT, collection_dir=self.collection)
        analysis = analyze_capture(capture)
        state = analysis["collection_state"]
        self.assertEqual(state["response_count"], 6)
        self.assertEqual(state["responded_participant_count"], 2)
        self.assertEqual(state["complete_five_response_sessions"], 1)
        self.assertEqual(state["partial_sessions"], 1)
        self.assertEqual(state["coverage_histogram"], {"0": 35, "1": 4, "2": 1})
        self.assertEqual(
            analysis["metrics"]["directional_inter_annotator_agreement"]["annotator_pairs"], 1,
        )
        self.assertFalse(analysis["interpretation_boundaries"]["training_eligible"])
        self.assertFalse(analysis["interpretation_boundaries"]["majority_vote_label_created"])

    def test_expandable_collection_accepts_unique_five_task_batches(self):
        self.registry["schema_version"] = "0.6.0"
        self.registry["task_batch_size"] = 5
        participant = self._participant(1, self.task_ids[:10])
        rows = [
            self._row(participant, task_id, "CANNOT_JUDGE")
            for task_id in participant["task_ids"][:6]
        ]
        self._write([(participant, rows)])

        capture = capture_collection(pilot_dir=PILOT, collection_dir=self.collection)
        self.assertEqual(capture.participants[0].assigned_task_ids, tuple(self.task_ids[:10]))
        self.assertEqual(len(capture.responses), 6)

    def test_snapshot_is_content_addressed_deterministic_and_has_no_tokens(self):
        first = self._participant(1, self.task_ids[:5])
        rows = [self._row(first, first["task_ids"][0], "CANNOT_JUDGE")]
        self._write([(first, rows)])
        capture = capture_collection(pilot_dir=PILOT, collection_dir=self.collection)
        out = Path(self.temp.name) / "analysis"
        first_path, first_analysis = write_snapshot(capture, output_root=out)
        second_path, second_analysis = write_snapshot(capture, output_root=out)
        self.assertEqual(first_path, second_path)
        self.assertEqual(first_analysis, second_analysis)
        for path in first_path.iterdir():
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("session_token_hash", text)
            self.assertNotIn(self.registry["participants"][0]["session_token_hash"], text)
        manifest = json.loads((first_path / "manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["training_eligible"])

    def test_unassigned_response_and_duplicate_response_id_fail_closed(self):
        first = self._participant(1, self.task_ids[:5])
        bad = self._row(first, self.task_ids[5], "APPROX_EQUAL")
        self._write([(first, [bad])])
        with self.assertRaisesRegex(ValueError, "assigned task order"):
            capture_collection(pilot_dir=PILOT, collection_dir=self.collection)

        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.collection = Path(self.temp.name) / "collection_test"
        self.responses = self.collection / "responses"
        self.registry["participants"] = []
        first = self._participant(1, self.task_ids[:5])
        second = self._participant(2, [self.task_ids[0], *self.task_ids[5:9]])
        row_a = self._row(first, self.task_ids[0], "APPROX_EQUAL")
        row_b = self._row(second, self.task_ids[0], "APPROX_EQUAL")
        row_b["response_id"] = row_a["response_id"]
        self._write([(first, [row_a]), (second, [row_b])])
        with self.assertRaisesRegex(ValueError, "deterministic session/task identity"):
            capture_collection(pilot_dir=PILOT, collection_dir=self.collection)

    def test_identity_and_provenance_mismatch_fail_closed(self):
        first = self._participant(1, self.task_ids[:5])
        row = self._row(first, self.task_ids[0], "APPROX_EQUAL")
        row["provenance"] = copy.deepcopy(row["provenance"])
        row["provenance"]["explicit_human_submission"] = False
        self._write([(first, [row])])
        with self.assertRaisesRegex(ValueError, "explicit human submission"):
            capture_collection(pilot_dir=PILOT, collection_dir=self.collection)

    def test_control_diagnostics_use_explicit_source_relation_not_row_order(self):
        control = next(
            row for row in self.tasks
            if row["control_type"] == "AB_INVERSION" and row.get("source_task_id")
        )
        source_id = str(control["source_task_id"])
        control_id = str(control["task_id"])
        filler = [task_id for task_id in self.task_ids if task_id not in (source_id, control_id)][:3]
        first = self._participant(1, [control_id, source_id, *filler])
        rows = [
            self._row(first, control_id, "A_SLIGHTLY_HIGHER"),
            self._row(first, source_id, "B_SLIGHTLY_HIGHER"),
        ]
        self._write([(first, rows)])
        capture = capture_collection(pilot_dir=PILOT, collection_dir=self.collection)
        controls = analyze_capture(capture)["control_relationship_diagnostics"]
        same = controls["same_annotator"]
        self.assertEqual(same["comparable_non_abstain_pairs"], 1)
        self.assertEqual(
            same["by_control_type"]["AB_INVERSION"]["comparable_non_abstain_pairs"], 1,
        )
        self.assertEqual(
            same["by_control_type"]["EXACT_REPEAT"]["comparable_non_abstain_pairs"], 0,
        )


@unittest.skipUnless(
    (PILOT / "pilot_tasks.jsonl").exists()
    and (ROOT / "docs/archive/HUMAN_ANNOTATION_COLLECTION_001_DISPOSITION_V01.json").exists(),
    "requires local human-annotation collection evidence",
)
class RealCollectionDispositionTests(unittest.TestCase):
    def test_interim_snapshot_disposition_binds_exact_evidence(self):
        disposition_path = ROOT / "docs/archive/HUMAN_ANNOTATION_COLLECTION_001_DISPOSITION_V01.json"
        disposition = json.loads(disposition_path.read_text(encoding="utf-8"))
        snapshot = (
            PILOT / "collections/collection_001/analysis" / disposition["snapshot_id"]
        )
        manifest_bytes = (snapshot / "manifest.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(manifest_bytes).hexdigest(),
            disposition["snapshot_manifest_sha256"],
        )
        manifest = json.loads(manifest_bytes)
        analysis = json.loads((snapshot / "analysis.json").read_text(encoding="utf-8"))
        responses = read_jsonl(snapshot / "responses.jsonl")
        for name, expected in manifest["files"].items():
            payload = (snapshot / name).read_bytes()
            self.assertEqual(len(payload), expected["size"])
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected["sha256"])
        self.assertEqual(manifest["snapshot_id"], disposition["snapshot_id"])
        self.assertEqual(len(responses), disposition["response_count"])
        self.assertEqual(
            analysis["collection_state"]["responded_participant_count"],
            disposition["responded_participant_count"],
        )
        self.assertFalse(disposition["training_eligible"])
        self.assertFalse(disposition["human_evidence_is_ground_truth"])
        self.assertNotIn("session_token_hash", (snapshot / "analysis.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
