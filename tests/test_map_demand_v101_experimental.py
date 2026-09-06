from __future__ import annotations

import copy
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from map_demand_v01 import cli, release  # noqa: E402
from map_demand_v01 import flow_execution_v02 as flow  # noqa: E402
from map_demand_v01 import model_v100 as stable  # noqa: E402
from map_demand_v01 import model_v101_experimental as experiment  # noqa: E402
from map_demand_v01.bid_review_ui_v01 import BidReviewWorkbench  # noqa: E402
from tests.test_map_demand_v01 import mini_calibration  # noqa: E402
from tests.test_map_demand_v010_beta7 import synthetic_map_text  # noqa: E402
from tests.test_map_demand_v010_beta8 import analyze, checksum, extract  # noqa: E402


class Experimental101IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="flow101-integration-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "fixture.osu"
        self.path.write_text(synthetic_map_text(), encoding="utf-8")
        self.calibration_dir = self.root / "calibration"
        self.calibration_dir.mkdir()
        calibration = mini_calibration()
        calibration["distributions"]["reading_preempt_median_ms"] = [
            0.0, 1.0, 1000.0,
        ]
        (self.calibration_dir / "calibration.json").write_text(
            json.dumps(calibration), encoding="utf-8"
        )

    def analyze_components(self, components, metadata):
        return experiment.analyze_components(
            checksum=checksum(self.path),
            requested_mods=metadata["mod_context"]["effective_mods"],
            components=components,
            calibration=mini_calibration(),
            applied_mod_context=metadata["mod_transform_context"],
        )

    def test_opt_in_registration_preserves_default_and_persisted_selection(self):
        selector = self.root / "runtime-selection.json"
        with mock.patch.object(release, "RUNTIME_SELECTION_PATH", selector), mock.patch.dict(
            os.environ, {"SKILL_PROFILER_ALGORITHM": ""}
        ):
            self.assertEqual(release.DEFAULT_ALGORITHM, "v100")
            self.assertEqual(release.default_algorithm(), "v100")
            self.assertIs(release.runtime_model(), stable)
            self.assertIs(release.runtime_model("v101-experimental"), experiment)
            self.assertFalse(selector.exists())
            selector.write_text('{"algorithm":"v010-beta9.2"}', encoding="utf-8")
            before = selector.read_bytes()
            self.assertIs(release.runtime_model("v101-experimental"), experiment)
            self.assertEqual(release.default_algorithm(), "v010-beta9.2")
            self.assertEqual(selector.read_bytes(), before)

    def test_seven_axis_payloads_are_frozen_across_supported_mods(self):
        self.assertEqual(experiment.CHANGED_FROM_PREVIOUS, frozenset({"flow_aim", "aim_control"}))
        for mods in ((), ("HD",), ("HR",), ("HD", "HR"), ("EZ",), ("DT",), ("HT",)):
            with self.subTest(mods=mods):
                before, _old_components, _ = analyze(stable, self.path, mods)
                after, _components, _ = analyze(experiment, self.path, mods)
                self.assertEqual(after["status"], "OK")
                self.assertEqual(set(after["axes"]), set(before["axes"]))
                for axis in stable.AXIS_ORDER:
                    if axis not in {"flow_aim", "aim_control"}:
                        self.assertEqual(after["axes"][axis], before["axes"][axis], axis)
                self.assertNotEqual(after["axes"]["flow_aim"], before["axes"]["flow_aim"])
                self.assertNotEqual(after["axes"]["aim_control"], before["axes"]["aim_control"])
                self.assertEqual(after["identity"]["map_demand_version"], "1.0.1-experimental.11")
                self.assertEqual(after["identity"]["algorithm_id"], "MAP_DEMAND_V101_EXPERIMENTAL")
                self.assertEqual(after["release"]["stage"], "EXPERIMENTAL")
                self.assertEqual(after["release"]["basis"], "1.0.0")
                json.dumps(after, allow_nan=False)

    def test_extraction_and_analysis_do_not_mutate_their_inputs(self):
        rows, features, metadata = experiment.extract_from_path(str(self.path), ("HD", "HR"))
        before_rows, before_features, before_metadata = copy.deepcopy((rows, features, metadata))
        components, _ = experiment.extract_components(
            rows, features, metadata["difficulty"],
            clock_rate=metadata["mod_transform_context"]["clock_rate"],
            effective_mods=metadata["mod_context"]["effective_mods"],
            source_local_signal_version=metadata["local_signal_version"],
        )
        self.assertEqual((rows, features, metadata), (before_rows, before_features, before_metadata))
        before_components = copy.deepcopy(components)
        self.analyze_components(components, metadata)
        self.assertEqual(components, before_components)

    def test_low_level_flow_accepts_a_single_pass_iterable(self):
        rows, _features, metadata = experiment.extract_from_path(str(self.path), ())

        class SinglePass:
            def __init__(self, items):
                self.items = items
                self.used = False

            def __iter__(self):
                if self.used:
                    raise AssertionError("Flow tried to consume the same iterable twice")
                self.used = True
                return iter(self.items)

        options = {"circle_size": metadata["difficulty"]["CircleSize"]}
        expected = flow.extract_flow_measure(rows, (), **options)
        actual = flow.extract_flow_measure(SinglePass(rows), (), **options)
        self.assertEqual(actual, expected)

    def test_old_components_and_mismatched_provenance_are_rejected(self):
        _rows, metadata, old_components, _ = extract(stable, self.path)
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.analyze_components(old_components, metadata)
        _rows, metadata, components, _ = extract(experiment, self.path)
        for key, value, message in (
            ("v101_source_local_signal_version", "0.3.0", "provenance"),
            ("v101_flow_schema_version", "legacy", "schema"),
            ("v101_flow_measure", None, "measure"),
            ("v101_control_schema_version", "legacy", "schema"),
            ("v101_control_measure", None, "measure"),
        ):
            with self.subTest(key=key):
                malformed = copy.deepcopy(components)
                malformed[key] = value
                with self.assertRaisesRegex(ValueError, message):
                    self.analyze_components(malformed, metadata)

    def test_cli_explicitly_selects_experiment(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = cli.main([
                "analyze", "--map", str(self.path), "--calibration-dir",
                str(self.calibration_dir), "--algorithm", "v101-experimental",
                "--mods", "HD", "HR",
            ])
        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["identity"]["algorithm_id"], experiment.ALGORITHM_ID)
        self.assertEqual(payload["release"]["stage"], "EXPERIMENTAL")

    def test_workbench_parser_and_state_expose_explicit_experimental_identity(self):
        with mock.patch.object(cli, "cmd_bid_review_ui", return_value=0) as start:
            self.assertEqual(cli.main([
                "bid-review-ui", "--algorithm", "v101-experimental", "--port", "8768",
                "--no-open", "--responses", str(self.root / "responses.jsonl"),
            ]), 0)
        args = start.call_args.args[0]
        self.assertEqual(args.algorithm, "v101-experimental")
        self.assertEqual(args.port, 8768)
        self.assertTrue(args.no_open)
        manifest = self.root / "manifest.jsonl"
        manifest.write_text(json.dumps({
            "beatmap_id": 123456,
            "beatmapset_id": 1,
            "relative_path": "fixture.osu",
        }) + "\n", encoding="utf-8")
        workbench = BidReviewWorkbench(
            manifest_path=manifest, songs_root=self.root,
            calibration_path=self.calibration_dir / "calibration.json",
            responses_path=self.root / "responses.jsonl", reviewer_id="test-only",
            cache_root=self.root / "cache", algorithm="v101-experimental",
        )
        state = workbench.state()
        self.assertEqual(state["map_demand_version"], experiment.MAP_DEMAND_VERSION)
        self.assertEqual(state["algorithm_id"], experiment.ALGORITHM_ID)
        self.assertEqual(state["release"]["stage"], "EXPERIMENTAL")
        result = workbench.analyze_bid(123456)
        control = result["axes"]["aim_control"]
        self.assertEqual(control["public_value_semantics"], "EXPERIMENTAL_ESTABLISHED_LOCAL_CONTROL_EXECUTION")
        self.assertEqual(control["mechanism_coverage"]["status"], "COMPLETE_DEFINED_MECHANISMS")
        self.assertEqual(control["evidence_quality"], "FULL")
        self.assertEqual(control["winning_direction_coverage"], 1.0)
        self.assertGreater(control["stars"], 0)
        self.assertLessEqual(control["peak_window"]["end_ms"] - control["peak_window"]["start_ms"], 3000)


if __name__ == "__main__":
    unittest.main()
