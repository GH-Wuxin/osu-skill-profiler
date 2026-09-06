from __future__ import annotations

import json
import hashlib
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from map_demand_v01 import contract as C  # noqa: E402
from map_demand_v01 import model_v096  # noqa: E402
from map_demand_v01.bid_review_ui_v01 import (  # noqa: E402
    BidMapIndex,
    BidReviewError,
    BidReviewWorkbench,
    REVIEW_SCHEMA_VERSION,
)


def calibration_payload() -> dict:
    names = {
        signal
        for axis in C.AXIS_ORDER
        for signal in C.AXIS_META[axis]["signals"]
    }
    names.add("reading_preempt_median_ms")
    return {
        "calibration_id": "bid-review-test-calibration",
        "distributions": {name: [0.0, 1.0, 1000.0] for name in names},
    }


class BidReviewWorkbenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.songs = self.root / "Songs"
        folder = self.songs / "1 fixture"
        folder.mkdir(parents=True)
        self.map_path = folder / "fixture.osu"
        shutil.copy2(ROOT / "tests" / "fixtures" / "minimal.osu", self.map_path)
        self.manifest = self.root / "manifest.jsonl"
        self.manifest.write_text(
            json.dumps(
                {
                    "beatmap_id": 123456,
                    "beatmapset_id": 1,
                    "artist": "Fixture Artist",
                    "title": "Fixture Title",
                    "version": "Fixture Diff",
                    "creator": "Fixture Mapper",
                    "relative_path": "1 fixture/fixture.osu",
                    "metadata": {"difficulty": {"AR": 5, "OD": 5, "CS": 4}},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.calibration = self.root / "calibration.json"
        self.calibration.write_text(
            json.dumps(calibration_payload()), encoding="utf-8"
        )
        self.responses = self.root / "responses.jsonl"
        self.cache = self.root / "cache"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def workbench(self, analysis_workers: int = 0) -> BidReviewWorkbench:
        return BidReviewWorkbench(
            manifest_path=self.manifest,
            songs_root=self.songs,
            calibration_path=self.calibration,
            responses_path=self.responses,
            reviewer_id="tester",
            cache_root=self.cache,
            algorithm="v096",
            analysis_workers=analysis_workers,
        )

    def test_process_workers_preserve_results_and_review_identity(self):
        serial = self.workbench()
        parallel = self.workbench(analysis_workers=2)
        mods = [[], ["HD"], ["HR"]]
        expected = [serial.analyze_bid(123456, mod) for mod in mods]
        try:
            with ThreadPoolExecutor(max_workers=3) as callers:
                futures = [callers.submit(parallel.analyze_bid, 123456, mod) for mod in mods]
                actual = [future.result(timeout=30) for future in futures]
            self.assertEqual(actual, expected)
            self.assertEqual(parallel.state()["analysis_workers"], 2)
            saved = parallel.save_response({
                "analysis_id": actual[0]["analysis_id"],
                "ratings": {"aim_control": {"qualifier": "APPROXIMATE", "value": 3.0}},
            })
            self.assertEqual(saved["status"], "SAVED")
        finally:
            parallel.close()

    def test_bid_index_resolves_only_manifest_paths(self):
        index = BidMapIndex(manifest_path=self.manifest, songs_root=self.songs)
        self.assertEqual(index.lookup(123456)["path_abs"], str(self.map_path.resolve()))
        with self.assertRaises(BidReviewError) as ctx:
            index.lookup(999999)
        self.assertEqual(ctx.exception.code, "BID_NOT_FOUND")

    def test_bid_index_accepts_production_manifest_container(self):
        record = {
            "beatmap_id": 123456,
            "relative_path": "1 fixture/fixture.osu",
        }
        self.manifest.write_text(
            '{"schema_version":"0.1.0","samples":[\n'
            + json.dumps(record)
            + ",\n"
            + json.dumps({"beatmap_id": None, "relative_path": "ignored.osu"})
            + "\n]}\n",
            encoding="utf-8",
        )
        index = BidMapIndex(manifest_path=self.manifest, songs_root=self.songs)
        self.assertEqual(index.lookup(123456)["path_abs"], str(self.map_path.resolve()))

    def test_imported_osu_is_validated_cached_and_hot_indexed(self):
        workbench = self.workbench()
        imported = (ROOT / "tests" / "fixtures" / "minimal.osu").read_text(
            encoding="utf-8"
        ).replace("BeatmapID:1000001", "BeatmapID:999999")
        result = workbench.import_osu(999999, imported)
        self.assertEqual(result["status"], "IMPORTED")
        self.assertTrue((self.cache / "999999.osu").is_file())
        analysis = workbench.analyze_bid(999999)
        self.assertEqual(analysis["beatmap"]["beatmap_id"], 999999)
        self.assertEqual(analysis["beatmap"]["title"], "Synthetic Minimal")
        self.assertGreater(analysis["analysis_context"]["bpm_max"], 0)
        self.assertGreater(analysis["analysis_context"]["duration_ms"], 0)
        restarted = self.workbench()
        restarted_analysis = restarted.analyze_bid(999999)
        self.assertEqual(restarted_analysis["beatmap"]["beatmap_id"], 999999)
        self.assertEqual(restarted_analysis["beatmap"]["title"], "Synthetic Minimal")
        self.assertEqual(
            restarted_analysis["analysis_context"]["bpm_max"],
            analysis["analysis_context"]["bpm_max"],
        )
        self.assertEqual(
            restarted_analysis["analysis_context"]["duration_ms"],
            analysis["analysis_context"]["duration_ms"],
        )
        with self.assertRaises(BidReviewError) as mismatch:
            workbench.import_osu(999998, imported)
        self.assertEqual(mismatch.exception.code, "BID_MISMATCH")

    def test_manifest_path_escape_is_rejected(self):
        self.manifest.write_text(
            json.dumps({"beatmap_id": 1, "relative_path": "../escape.osu"}) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            BidMapIndex(manifest_path=self.manifest, songs_root=self.songs)

    def test_legacy_import_requires_checksum_preserves_bytes_and_survives_restart(self):
        workbench = self.workbench()
        original = (ROOT / "tests" / "fixtures" / "minimal.osu").read_text(encoding="utf-8")
        legacy = "\ufeff" + original.replace("BeatmapID:1000001", "// legacy file has no ID").replace("\n", "\r\n")
        checksum = hashlib.md5(legacy.encode("utf-8")).hexdigest()
        with self.assertRaises(BidReviewError) as missing:
            workbench.import_osu(999999, legacy)
        self.assertEqual(missing.exception.code, "BID_MISMATCH")
        for invalid_checksum in ["0" * 32, {}, ""]:
            with self.assertRaises(BidReviewError) as mismatch:
                workbench.import_osu(999999, legacy, invalid_checksum)
            self.assertEqual(mismatch.exception.code, "CHECKSUM_MISMATCH")
        workbench.import_osu(999999, legacy, checksum)
        self.assertEqual((self.cache / "999999.osu").read_bytes(), legacy.encode("utf-8"))
        self.assertEqual(self.workbench().index.lookup(999999)["beatmap_id"], 999999)
        # Even a matching digest cannot override a conflicting declared ID.
        with self.assertRaises(BidReviewError) as conflicting:
            workbench.import_osu(999999, original, hashlib.md5(original.encode("utf-8")).hexdigest())
        self.assertEqual(conflicting.exception.code, "BID_MISMATCH")
        (self.cache / "999999.osu").write_bytes(legacy.encode("utf-8") + b"\n// tampered")
        with self.assertRaises(BidReviewError) as tampered:
            self.workbench().index.lookup(999999)
        self.assertEqual(tampered.exception.code, "BID_NOT_FOUND")

    def test_identical_duplicate_bid_paths_are_collapsed(self):
        duplicate_folder = self.songs / "2 duplicate fixture"
        duplicate_folder.mkdir()
        duplicate_path = duplicate_folder / "fixture-copy.osu"
        shutil.copy2(self.map_path, duplicate_path)
        records = [
            {
                "beatmap_id": 123456,
                "relative_path": "1 fixture/fixture.osu",
                "sha256": "sha256:identical",
            },
            {
                "beatmap_id": 123456,
                "relative_path": "2 duplicate fixture/fixture-copy.osu",
                "sha256": "sha256:identical",
            },
        ]
        self.manifest.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )
        result = BidMapIndex(
            manifest_path=self.manifest, songs_root=self.songs
        ).lookup(123456)
        self.assertEqual(len(result["duplicate_local_paths"]), 2)
        self.assertIn(result["path_abs"], result["duplicate_local_paths"])

    def test_different_files_with_same_bid_remain_ambiguous(self):
        other_folder = self.songs / "2 different fixture"
        other_folder.mkdir()
        other_path = other_folder / "different.osu"
        other_path.write_text("osu file format v14\n", encoding="utf-8")
        records = [
            {
                "beatmap_id": 123456,
                "relative_path": "1 fixture/fixture.osu",
                "sha256": "sha256:first",
            },
            {
                "beatmap_id": 123456,
                "relative_path": "2 different fixture/different.osu",
                "sha256": "sha256:second",
            },
        ]
        self.manifest.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )
        index = BidMapIndex(manifest_path=self.manifest, songs_root=self.songs)
        with self.assertRaises(BidReviewError) as ambiguous:
            index.lookup(123456)
        self.assertEqual(ambiguous.exception.code, "BID_AMBIGUOUS")

    def test_analyze_and_append_partial_human_review(self):
        workbench = self.workbench()
        result = workbench.analyze_bid(123456)
        self.assertEqual(result["beatmap"]["beatmap_id"], 123456)
        self.assertEqual(result["identity"]["effective_mods"], [])
        self.assertEqual(result["analysis_context"]["clock_rate"], 1.0)
        self.assertEqual(set(result["axes"]), set(model_v096.AXIS_ORDER))
        self.assertEqual(result["identity"]["map_demand_version"], "0.9.6")
        self.assertEqual(result["experimental_type"]["stage"], "EXPERIMENTAL")
        self.assertIn(result["experimental_type"]["status"], {"PROPOSED", "ABSTAINED"})
        self.assertEqual(
            result["experimental_type"]["classifier_version"],
            result["experimental_type"]["summary"]["classifier_version"],
        )
        self.assertGreaterEqual(len(result["experimental_type"]["sections"]), 1)
        self.assertEqual(result["axes"]["stamina"]["unit"], "bounded_0_10")
        self.assertEqual(result["axes"]["endurance"]["unit"], "bounded_0_10")
        self.assertEqual(result["axes"]["reading"]["unit"], "star_equivalent")
        saved = workbench.save_response(
            {
                "analysis_id": result["analysis_id"],
                "ratings": {
                    "reading": {"qualifier": "AT_LEAST", "value": 6.8},
                    "finger_control": {"qualifier": "SKIP", "value": None},
                },
                "confidence": "HIGH",
                "notes": "fixture review",
            }
        )
        self.assertEqual(saved["status"], "SAVED")
        lines = self.responses.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        response = json.loads(lines[0])
        self.assertEqual(response["schema_version"], REVIEW_SCHEMA_VERSION)
        self.assertEqual(response["ratings"]["reading"]["value"], 6.8)
        self.assertEqual(response["ratings"]["jump_aim"]["qualifier"], "SKIP")
        self.assertEqual(response["ratings"]["endurance"]["qualifier"], "SKIP")
        self.assertTrue(
            response["algorithm_identity"]["calibration_id"].startswith(
                "mdoverlay_v096:"
            )
        )
        self.assertEqual(
            response["algorithm_identity"]["algorithm_id"],
            "MAP_DEMAND_ATOMIC_V096",
        )
        self.assertEqual(
            response["algorithm_identity"]["map_demand_version"], "0.9.6"
        )
        self.assertEqual(response["mod_context"]["requested_mods"], [])

    def test_modded_analysis_is_transformed_and_bound_to_response(self):
        workbench = self.workbench()
        result = workbench.analyze_bid(123456, requested_mods="HDHRDT")
        self.assertEqual(result["mod_context"]["requested_mods"], ["HD", "HR", "DT"])
        self.assertEqual(result["identity"]["effective_mods"], ["HD", "HR", "DT"])
        self.assertEqual(result["identity"]["clock_rate"], 1.5)
        self.assertEqual(result["analysis_context"]["clock_rate"], 1.5)
        effective = result["analysis_context"]["effective_difficulty"]
        raw = result["analysis_context"]["difficulty"]
        self.assertGreater(effective["ApproachRate"], raw["ApproachRate"])
        self.assertGreater(effective["OverallDifficulty"], raw["OverallDifficulty"])
        self.assertEqual(effective["CircleSize"], raw["CircleSize"])
        self.assertEqual(effective["HPDrainRate"], raw["HPDrainRate"])
        saved = workbench.save_response(
            {
                "analysis_id": result["analysis_id"],
                "ratings": {
                    "reading": {"qualifier": "APPROXIMATE", "value": 7.0}
                },
            }
        )
        self.assertEqual(saved["status"], "SAVED")
        response = json.loads(self.responses.read_text(encoding="utf-8"))
        self.assertEqual(response["mod_context"]["requested_mods"], ["HD", "HR", "DT"])
        self.assertEqual(response["algorithm_identity"]["clock_rate"], 1.5)

    def test_conflicting_and_deferred_mods_fail_closed(self):
        workbench = self.workbench()
        with self.assertRaises(BidReviewError) as conflict:
            workbench.analyze_bid(123456, requested_mods="EZHR")
        self.assertEqual(conflict.exception.code, "INVALID_MODS")
        with self.assertRaises(BidReviewError) as deferred:
            workbench.analyze_bid(123456, requested_mods="FL")
        self.assertEqual(deferred.exception.code, "UNSUPPORTED_MODS")

    def test_unknown_analysis_and_empty_review_fail_closed(self):
        workbench = self.workbench()
        with self.assertRaises(BidReviewError) as missing:
            workbench.save_response({"analysis_id": "nope", "ratings": {}})
        self.assertEqual(missing.exception.code, "ANALYSIS_NOT_FOUND")
        result = workbench.analyze_bid(123456)
        with self.assertRaises(BidReviewError) as empty:
            workbench.save_response(
                {"analysis_id": result["analysis_id"], "ratings": {}}
            )
        self.assertEqual(empty.exception.code, "EMPTY_REVIEW")

    def test_corrected_response_supersedes_old_record(self):
        workbench = self.workbench()
        hd = workbench.analyze_bid(123456, requested_mods="HD")
        wrong = workbench.save_response(
            {
                "analysis_id": hd["analysis_id"],
                "ratings": {
                    "flow_aim": {"qualifier": "APPROXIMATE", "value": 6.0}
                },
            }
        )
        corrected = workbench.save_response(
            {
                "analysis_id": hd["analysis_id"],
                "ratings": {
                    "flow_aim": {"qualifier": "APPROXIMATE", "value": 6.5}
                },
                "supersedes_response_id": wrong["response_id"],
            }
        )
        self.assertEqual(corrected["active_responses"], 1)
        state = workbench.state()
        self.assertEqual(state["algorithm_id"], "MAP_DEMAND_ATOMIC_V096")
        self.assertEqual(state["map_demand_version"], "0.9.6")
        self.assertEqual(state["saved_responses"], 2)
        self.assertEqual(state["active_responses"], 1)
        self.assertEqual(state["superseded_responses"], 1)
        payloads = [
            json.loads(line)
            for line in self.responses.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            payloads[1]["supersedes_response_id"], wrong["response_id"]
        )
        with self.assertRaises(BidReviewError) as duplicate:
            workbench.save_response(
                {
                    "analysis_id": hd["analysis_id"],
                    "ratings": {
                        "flow_aim": {
                            "qualifier": "APPROXIMATE",
                            "value": 6.6,
                        }
                    },
                    "supersedes_response_id": wrong["response_id"],
                }
            )
        self.assertEqual(duplicate.exception.code, "RESPONSE_ALREADY_SUPERSEDED")


if __name__ == "__main__":
    unittest.main()
